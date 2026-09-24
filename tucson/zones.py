# tucson/zones.py
"""Landmark polygons from OSM (cached) -> boolean masks in warped world space."""
import json, os, time, urllib.error, urllib.parse, urllib.request
import numpy as np
from PIL import Image, ImageDraw
from .config import ROOT

ENDPOINT = "https://overpass-api.de/api/interpreter"
RETRIES = 4
CACHE = os.path.join(ROOT, "cache", "osm")


def overpass(query):
    body = urllib.parse.urlencode({"data": f"[out:json][timeout:60];{query}"}).encode()
    for i in range(RETRIES):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, headers={"User-Agent": "7dtd-tucson/0.1"})
            return json.load(urllib.request.urlopen(req, timeout=90))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            time.sleep(15 * (i + 1))
    raise RuntimeError(f"overpass failed after {RETRIES} tries: {query[:80]}")


def rect_rings(r):
    s, w, n, e = r
    return [[(s, w), (s, e), (n, e), (n, w)]]


def fetch_rings(name, selector, cache_dir=CACHE):
    """Outer rings [(lat,lon),...] of the selected way/relation. Cached per zone name."""
    path = cache_dir and os.path.join(cache_dir, f"{name}.json")
    if path and os.path.exists(path):
        return json.load(open(path))
    d = overpass(f"({selector};);out geom;")
    rings = []
    for el in d["elements"]:
        if el["type"] == "way" and "geometry" in el:
            rings.append([(p["lat"], p["lon"]) for p in el["geometry"]])
        for m in el.get("members", []):
            if m.get("role") in ("outer", "") and "geometry" in m:
                rings.append([(p["lat"], p["lon"]) for p in m["geometry"]])
    if not rings:
        raise RuntimeError(f"zone {name}: no polygon from OSM")
    if path:
        os.makedirs(cache_dir, exist_ok=True); json.dump(rings, open(path, "w"))
    return rings


def polygons(cfg):
    return {z["name"]: (rect_rings(z["rect"]) if "rect" in z else fetch_rings(z["name"], z["osm"]))
            for z in cfg["zones"]}


def stitch(segments):
    """Join open way segments (relation outer members) end-to-end into closed rings.
    Segments may be reversed; closed segments pass through unchanged."""
    segs = [list(map(tuple, s)) for s in segments]
    rings = [s for s in segs if len(s) > 2 and s[0] == s[-1]]
    open_ = [s for s in segs if not (len(s) > 2 and s[0] == s[-1])]
    while open_:
        cur = open_.pop(0)
        grown = True
        while cur[0] != cur[-1] and grown:
            grown = False
            for i, s in enumerate(open_):
                if s[0] == cur[-1]:   cur = cur + s[1:]
                elif s[-1] == cur[-1]: cur = cur + s[::-1][1:]
                elif s[-1] == cur[0]: cur = s + cur[1:]
                elif s[0] == cur[0]:  cur = s[::-1] + cur[1:]
                else: continue
                open_.pop(i); grown = True; break
        if cur[0] != cur[-1]:
            cur = cur + [cur[0]]                           # unmatched chain: close it (best effort)
        rings.append(cur)
    return rings


def mask(rings, warp, N):
    """Rasterize rings (lat,lon) into an N×N bool mask, row 0 = north. Relation outer
    members may be split into several ways; each ring is filled independently."""
    img = Image.new("1", (N, N), 0); d = ImageDraw.Draw(img)
    for ring in stitch(rings):
        lat = np.array([p[0] for p in ring]); lon = np.array([p[1] for p in ring])
        pts = list(zip(warp.x(lon).tolist(), warp.z(lat).tolist()))
        if len(pts) >= 3:
            d.polygon(pts, fill=1)
    return np.asarray(img, dtype=bool)
