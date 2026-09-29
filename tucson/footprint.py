"""Footprint validator: does each landmark's PREFAB match the size of the REAL building?

Two independent scale axes, reported side by side:

  prefab vs real   -- a prefab block is 1 real metre to the player, so a 60-block prefab
                      standing in for a 380 m mall is 6x too small. This is the axis the
                      validator gates on; it is fixable by picking a better prefab.
  map compression  -- the warp packs 45 km into 10240 blocks, so one block is 2.6-4.3 m of
                      ground depending where you are. Reported for context only; it is not
                      fixable by prefab choice (road widths carry that one).

Real footprints come from OSM: Overpass `out bb;` for `osm =` selectors, the Nominatim
`boundingbox` for `q =` entries, or an explicit `real_size = [w_m, d_m]` in landmarks.toml
which always wins. OSM bounds are axis-aligned, so a diagonal building over-reports --
that is why the pass band is generous rather than tight.
"""
import json, os, urllib.parse, urllib.request
import math

from . import landmarks, zones
from .config import ROOT, load as load_cfg
from .warp import KM_PER_DEG_LAT, KM_PER_DEG_LON_EQ, Warp

CACHE = os.path.join(ROOT, "cache", "osm", "footprints.json")
OK_LO, OK_HI = 0.7, 1.4        # prefab / real ratio band that needs no action


def _bbox_m(s, w, n, e):
    """Bounding box in degrees -> (width_m east-west, depth_m north-south)."""
    kx = KM_PER_DEG_LON_EQ * math.cos(math.radians((n + s) / 2))
    return (e - w) * kx * 1000.0, (n - s) * KM_PER_DEG_LAT * 1000.0


def _nominatim_bbox(q, box):
    vb = f'{box["west"]},{box["north"]},{box["east"]},{box["south"]}'
    u = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 1, "viewbox": vb, "bounded": 1})
    import time; time.sleep(1.1)                                   # Nominatim policy: <= 1 req/s
    req = urllib.request.Request(u, headers={"User-Agent": "7dtd-tucson/0.1"})
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if not r or "boundingbox" not in r[0]:
        return None
    s, n, w, e = map(float, r[0]["boundingbox"])
    return _bbox_m(s, w, n, e)


def real_sizes(entries, box, cache=CACHE):
    """id -> (w_m, d_m) or None when OSM only gives a point (nodes, places)."""
    got = json.load(open(cache)) if cache and os.path.exists(cache) else {}
    for e in entries:
        eid = e["id"]
        if "real_size" in e:                                       # hand override wins
            got[eid] = list(e["real_size"]); continue
        if eid in got:
            continue
        size = None
        if "osm" in e:
            d = zones.overpass(f"({e['osm']};);out bb;")
            for el in d.get("elements", []):
                b = el.get("bounds")
                if b:
                    size = list(_bbox_m(b["minlat"], b["minlon"], b["maxlat"], b["maxlon"]))
                    break
        elif "q" in e:
            b = _nominatim_bbox(e["q"], box)
            size = list(b) if b else None
        got[eid] = size
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(got, open(cache, "w"), indent=1)
    return got


def scale_at(warp, lat, lon):
    """Local metres of real ground per world block, (x, z), from the warp derivative."""
    x, z = float(warp.x(lon)), float(warp.z(lat))
    mx = abs(float(warp.lon(x + 0.5)) - float(warp.lon(x - 0.5))) * warp.kx * 1000.0
    mz = abs(float(warp.lat(z + 0.5)) - float(warp.lat(z - 0.5))) * KM_PER_DEG_LAT * 1000.0
    return mx, mz


def audit(entries=None, cfg=None):
    """One row per landmark: prefab size, real size, ratio, verdict."""
    cfg = cfg or load_cfg()
    entries = entries or landmarks.load()
    warp = Warp(cfg)
    coords = landmarks.resolve(entries, box=cfg["box"])
    real = real_sizes(entries, cfg["box"])
    rows = []
    for e in entries:
        eid = e["id"]
        sx, sy, sz, _ = landmarks.prefab_meta(e["prefab"])
        if e.get("rot", 0) % 2:                                    # rotation 1/3 swaps x<->z
            sx, sz = sz, sx
        lat, lon = coords[eid]
        mx, mz = scale_at(warp, lat, lon)
        r = real.get(eid)
        if r is None:
            rows.append(dict(id=eid, prefab=e["prefab"], px=sx, pz=sz, rw=None, rd=None,
                             rx=None, rz=None, verdict="no-footprint", mx=mx, mz=mz))
            continue
        rw, rd = r
        rx, rz = sx / max(rw, 1e-6), sz / max(rd, 1e-6)
        worst = max(rx, rz) if max(rx, rz) > 1 / min(rx, rz) else min(rx, rz)
        verdict = "ok" if OK_LO <= rx <= OK_HI and OK_LO <= rz <= OK_HI else (
            "TOO BIG" if worst > 1 else "TOO SMALL")
        rows.append(dict(id=eid, prefab=e["prefab"], px=sx, pz=sz, rw=rw, rd=rd,
                         rx=rx, rz=rz, verdict=verdict, mx=mx, mz=mz))
    return rows


def render(rows):
    h = f"{'landmark':<22}{'prefab':<26}{'prefab':>9}{'real (m)':>13}{'ratio':>13}{'m/blk':>11}  verdict"
    out = [h, "-" * len(h)]
    for r in rows:
        pf = f"{r['px']}x{r['pz']}"
        rs = "-" if r["rw"] is None else f"{r['rw']:.0f}x{r['rd']:.0f}"
        ra = "-" if r["rx"] is None else f"{r['rx']:.2f}/{r['rz']:.2f}"
        out.append(f"{r['id']:<22}{r['prefab']:<26}{pf:>9}{rs:>13}{ra:>13}"
                   f"{r['mx']:>5.1f}/{r['mz']:<5.1f}  {r['verdict']}")
    bad = [r for r in rows if r["verdict"] not in ("ok", "no-footprint")]
    out.append("")
    out.append(f"{len(rows)} landmarks, {len(bad)} outside the {OK_LO}-{OK_HI} band, "
               f"{sum(r['verdict'] == 'no-footprint' for r in rows)} with no OSM footprint")
    return "\n".join(out)


if __name__ == "__main__":
    print(render(audit()))
