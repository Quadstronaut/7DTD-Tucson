"""Real OSM roads -> graded terrain + splat3 asphalt mask."""
import json, os
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw
from . import zones
from .config import ROOT

CACHE = os.path.join(ROOT, "cache", "osm", "roads.json")


def classes(cfg):
    return [k for k, v in cfg["roads"].items() if isinstance(v, list)]


def fetch_ways(cfg):
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    b = cfg["box"]; cls = "|".join(classes(cfg))
    d = zones.overpass(f'way["highway"~"^({cls})$"]({b["south"]},{b["west"]},{b["north"]},{b["east"]});out geom tags;')
    ways = [{"id": e["id"], "cls": e["tags"]["highway"], "bridge": e["tags"].get("bridge", "no") != "no",
             "pts": [(p["lat"], p["lon"]) for p in e["geometry"]]}
            for e in d["elements"] if e["type"] == "way" and "geometry" in e]
    if not ways:
        raise RuntimeError("no roads returned from OSM")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True); json.dump(ways, open(CACHE, "w"))
    return ways


def _clip(a, b, lo, hi):
    """Liang-Barsky: clip segment a->b to the axis-aligned box [lo, hi]; None if outside."""
    t0, t1, d = 0.0, 1.0, b - a
    for k in range(2):
        for p, q in ((-d[k], a[k] - lo[k]), (d[k], hi[k] - a[k])):
            if p == 0:
                if q < 0:
                    return None
                continue
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return None
    return a + t0 * d, a + t1 * d


def _pieces(p, lo, hi):
    """Clip a polyline to the box; return the continuous inside pieces as point lists."""
    pieces, cur = [], []
    for a, c in zip(p[:-1], p[1:]):
        seg = _clip(a, c, lo, hi)
        if seg is None:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = []
            continue
        s0, s1 = seg
        if cur and np.allclose(cur[-1], s0):
            cur.append(s1)
        else:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = [s0, s1]
    if len(cur) >= 2:
        pieces.append(cur)
    return pieces


def to_world(ways, warp):
    """Clip each way to the box segment-wise (edge-crossing roads keep their inside part),
    then warp each piece to (x, row-from-north)."""
    b = warp.box; lo = np.array([b["south"], b["west"]]); hi = np.array([b["north"], b["east"]])
    out = []
    for w in ways:
        for piece in _pieces(np.array(w["pts"], float), lo, hi):
            q = np.array(piece)
            xy = np.stack([warp.x(q[:, 1]), warp.z(q[:, 0])], 1)
            out.append({**w, "xy": np.clip(xy, 0, warp.N - 1)})
    return out


def densify(xy, step=1.0):
    seg = np.diff(xy, axis=0); L = np.hypot(*seg.T)
    pts = [xy[:1]]
    for a, s, l in zip(xy[:-1], seg, L):
        n = max(1, int(np.ceil(l / step)))
        pts.append(a + s * (np.arange(1, n + 1)[:, None] / n))
    return np.vstack(pts)


def grade(blk, wways, cfg):
    """Return (graded terrain, road mask, splat channel map). Road cross-sections are flat:
    every road pixel takes the smoothed profile height of its nearest centerline pixel."""
    N0, N1 = blk.shape; rc = cfg["roads"]
    center_h = np.full(blk.shape, np.nan, np.float32)
    center_w = np.zeros(blk.shape, np.float32)
    center_c = np.zeros(blk.shape, np.uint8)
    # widest first so narrower roads (links) draw on top at junctions but never shrink a motorway
    for w in sorted(wways, key=lambda w: -rc[w["cls"]][0]):
        width, ch = rc[w["cls"]]
        p = densify(w["xy"], 0.5)
        ix = np.clip(np.round(p[:, 0]).astype(int), 0, N1 - 1); iy = np.clip(np.round(p[:, 1]).astype(int), 0, N0 - 1)
        prof = ndimage.gaussian_filter1d(blk[iy, ix].astype(np.float64), rc["profile_sigma"] * 2, mode="nearest")
        # where a centerline pixel is already set (junction), average -> continuity between roads
        cur = center_h[iy, ix]
        center_h[iy, ix] = np.where(np.isnan(cur), prof, (cur + prof) / 2)
        center_w[iy, ix] = np.maximum(center_w[iy, ix], width)
        center_c[iy, ix] = 1 if ch == "R" else 2
    is_c = ~np.isnan(center_h)
    if not is_c.any():
        return blk, np.zeros(blk.shape, bool), np.zeros(blk.shape, np.uint8)
    dist, (ny, nx) = ndimage.distance_transform_edt(~is_c, return_indices=True)
    half = center_w[ny, nx] / 2
    road = dist <= half
    target = center_h[ny, nx]
    t = np.clip((dist - half) / rc["feather"], 0, 1)                 # 0 on road -> 1 at feather edge
    w = np.where(road, 1.0, 1 - t)
    out = (blk * (1 - w) + np.nan_to_num(target) * w).astype(np.float32)
    ch = np.where(road, center_c[ny, nx], 0).astype(np.uint8)
    return out, road, ch
