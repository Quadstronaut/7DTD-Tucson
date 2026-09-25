"""Hand-placed landmark POIs: resolve coordinates (OSM, cached), flatten a pad under each
footprint, and emit prefabs.xml decorations with the verified placement rules:

- decoration position = footprint MIN corner (west, south); rotation 1/3 swaps size x<->z
  (verified on 1939/1941 RWG placements in a vanilla world)
- y = ground + YOffset + 1 (verified in game, Plan 1)
"""
import glob, json, os, re, time, tomllib, urllib.parse, urllib.request
import numpy as np
from scipy import ndimage
from . import zones
from .config import ROOT

PREFABS = r"G:\SteamLibrary\steamapps\common\7 Days To Die\Data\Prefabs"
CACHE = os.path.join(ROOT, "cache", "osm", "landmarks.json")
MAX_TOP = 250          # keep every roof under the 255 world ceiling with margin (ceiling unverified)
PAD_MARGIN = 3         # blocks of flat apron around the footprint
PAD_FEATHER = 10


def load(path=None):
    with open(path or os.path.join(ROOT, "data", "landmarks.toml"), "rb") as f:
        return tomllib.load(f)["place"]


_index = None
def prefab_meta(name):
    """(size_x, size_y, size_z, yoffset) from the game's prefab XML."""
    global _index
    if _index is None:
        _index = {os.path.basename(f)[:-4]: f for f in glob.glob(PREFABS + r"\**\*.xml", recursive=True)}
    t = open(_index[name], errors="ignore").read()
    sx, sy, sz = map(int, re.search(r'"PrefabSize" value="(\d+),\s*(\d+),\s*(\d+)"', t).groups())
    yo = int(re.search(r'"YOffset" value="(-?\d+)"', t).group(1))
    return sx, sy, sz, yo


def nominatim(q, box):
    vb = f'{box["west"]},{box["north"]},{box["east"]},{box["south"]}'
    u = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 1, "viewbox": vb, "bounded": 1})
    time.sleep(1.1)                                                   # Nominatim usage policy: <= 1 req/s
    r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "7dtd-tucson/0.1"}), timeout=30))
    if not r:
        raise RuntimeError(f"nominatim: nothing for {q!r} inside the map box")
    return [float(r[0]["lat"]), float(r[0]["lon"])]


def inside(latlon, box):
    return box["south"] <= latlon[0] <= box["north"] and box["west"] <= latlon[1] <= box["east"]


def resolve(entries, cache=CACHE, box=None):
    """id -> (lat, lon). `at` literal, `q` Nominatim (bounded), `osm` Overpass center; cached per id.
    Anything outside the map box is an error (catches same-name places elsewhere)."""
    from .config import load as _load
    box = box or _load()["box"]
    got = json.load(open(cache)) if cache and os.path.exists(cache) else {}
    for e in entries:
        if "at" in e:
            got[e["id"]] = list(e["at"])
        elif e["id"] in got and inside(got[e["id"]], box):
            continue
        elif "q" in e:
            got[e["id"]] = nominatim(e["q"], box)
        else:
            d = zones.overpass(f"({e['osm']};);out center;")
            els = d.get("elements", [])
            if not els:
                raise RuntimeError(f"landmark {e['id']}: OSM selector matched nothing: {e['osm']}")
            el = els[0]; c = el.get("center", el)
            got[e["id"]] = [c["lat"], c["lon"]]
        if not inside(got[e["id"]], box):
            raise RuntimeError(f"landmark {e['id']} resolved outside the map: {got[e['id']]}")
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True); json.dump(got, open(cache, "w"), indent=1)
    return got


def footprint(col, row, sx, sz, N):
    """Image-space footprint (row 0 = north) for a prefab CENTERED at (col,row), plus its world
    min corner. Returns (r0, r1, c0, c1, wx, wz) with rows/cols half-open."""
    c0 = int(round(col)) - sx // 2
    r1 = int(round(row)) + sz // 2 + 1          # southern edge row (exclusive bound)
    r0 = r1 - sz
    wx = c0 - N // 2
    wz = (N - r1) - N // 2                       # world z of the southern (min) edge
    return r0, r1, c0, c0 + sx, wx, wz


def flatten_pad(blk, r0, r1, c0, c1):
    """Flatten footprint+margin to its median (integer), feather outward. In place. Returns height."""
    N0, N1 = blk.shape; m = PAD_MARGIN; f = PAD_FEATHER
    a0, a1 = max(0, r0 - m - f), min(N0, r1 + m + f); b0, b1 = max(0, c0 - m - f), min(N1, c1 + m + f)
    win = blk[a0:a1, b0:b1]
    core = np.zeros(win.shape, bool)
    core[max(0, r0 - m - a0):r1 + m - a0, max(0, c0 - m - b0):c1 + m - b0] = True
    h = float(np.round(np.median(blk[r0:r1, c0:c1])))
    dist = ndimage.distance_transform_edt(~core)
    w = np.clip(1 - dist / f, 0, 1)
    blk[a0:a1, b0:b1] = win * (1 - w) + h * w
    return h


def place(entries, coords, warp, blk, road=None):
    """Flatten pads in `blk` (modified in place) and return (decorations, warnings).
    decorations: list of (prefab, x, y, z, rot)."""
    N = blk.shape[0]; decs, warns, rects = [], [], []
    for e in entries:
        sx, sy, sz, yo = prefab_meta(e["prefab"])
        rot = int(e.get("rot", 0))
        if rot % 2:
            sx, sz = sz, sx
        lat, lon = coords[e["id"]]
        col, row = float(warp.x(lon)), float(warp.z(lat))
        dx, dn = e.get("offset", [0, 0])
        col += dx; row -= dn
        r0, r1, c0, c1, wx, wz = footprint(col, row, sx, sz, N)
        if r0 < 0 or c0 < 0 or r1 > N or c1 > N:
            warns.append(f"{e['id']}: off map, skipped"); continue
        for oid, (a0, a1, b0, b1) in rects:
            if r0 < a1 and a0 < r1 and c0 < b1 and b0 < c1:
                warns.append(f"{e['id']}: overlaps {oid}")
        rects.append((e["id"], (r0, r1, c0, c1)))
        h = flatten_pad(blk, r0, r1, c0, c1)
        y = int(h) + yo + 1
        if y + sy > MAX_TOP:
            warns.append(f"{e['id']}: top {y + sy} > {MAX_TOP}")
        if road is not None and road[r0:r1, c0:c1].any():
            warns.append(f"{e['id']}: footprint overlaps {int(road[r0:r1, c0:c1].sum())} road px")
        decs.append((e["prefab"], wx, y, wz, rot))
    return decs, warns
