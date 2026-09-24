# tucson/dem.py
"""AWS Terrain Tiles (terrarium, keyless). elevation_m = R*256 + G + B/256 - 32768."""
import math, os, urllib.request
from functools import lru_cache
import numpy as np
from PIL import Image
from .config import ROOT

CACHE = os.path.join(ROOT, "cache", "terrarium")
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def _tile_xy(lat, lon, z):
    n = 2 ** z
    x = (np.asarray(lon) + 180) / 360 * n
    y = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n
    return x, y


@lru_cache(maxsize=2048)
def _tile(z, tx, ty):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{z}_{tx}_{ty}.png")
    if not os.path.exists(p):
        data = urllib.request.urlopen(URL.format(z=z, x=tx, y=ty), timeout=60).read()
        with open(p, "wb") as f:
            f.write(data)
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def sample(lat, lon, zoom=14):
    """Bilinear elevation (m) at arrays of lat/lon (same shape)."""
    fx, fy = _tile_xy(lat, lon, zoom)
    px, py = fx * 256 - 0.5, fy * 256 - 0.5              # global pixel coords (pixel centers)
    x0, y0 = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
    ax, ay = px - x0, py - y0
    def g(X, Y):
        out = np.empty(X.shape, np.float32)
        tx, ty = X // 256, Y // 256
        for key in set(zip(tx.ravel().tolist(), ty.ravel().tolist())):
            m = (tx == key[0]) & (ty == key[1])
            out[m] = _tile(zoom, *key)[Y[m] % 256, X[m] % 256]
        return out
    return ((g(x0, y0) * (1 - ax) + g(x0 + 1, y0) * ax) * (1 - ay)
            + (g(x0, y0 + 1) * (1 - ax) + g(x0 + 1, y0 + 1) * ax) * ay)
