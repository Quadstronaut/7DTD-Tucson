# tucson/warp.py
"""Separable piecewise-linear lat/lon -> world-pixel warp.

x grows west->east; z is the IMAGE ROW, growing north->south (PNG top = north).
Control points are [real_km, block] measured from box west / box south, so
landmark bands can get more blocks per km than filler.
"""
import math
import numpy as np

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQ = 111.320


class Warp:
    def __init__(self, cfg):
        b = cfg["box"]; self.N = int(cfg["size"]); self.box = b
        self.kx = KM_PER_DEG_LON_EQ * math.cos(math.radians((b["north"] + b["south"]) / 2))
        self.xk, self.xb = self._check(cfg["warp"]["x"], (b["east"] - b["west"]) * self.kx)
        self.zk, self.zb = self._check(cfg["warp"]["z"], (b["north"] - b["south"]) * KM_PER_DEG_LAT)

    def _check(self, pts, span_km):
        k = np.array([p[0] for p in pts], float); v = np.array([p[1] for p in pts], float)
        if len(k) < 2 or np.any(np.diff(k) <= 0) or np.any(np.diff(v) <= 0):
            raise ValueError("warp control points must be strictly increasing")
        if k[0] != 0 or v[0] != 0 or v[-1] != self.N or abs(k[-1] - span_km) > 0.05:
            raise ValueError(f"warp must span [0,0]..[{span_km:.2f},{self.N}]")
        k[-1] = span_km                                   # absorb rounding in the toml
        return k, v

    def x(self, lon):
        km = (np.asarray(lon, float) - self.box["west"]) * self.kx
        return np.interp(km, self.xk, self.xb)            # np.interp clamps outside range

    def z(self, lat):
        km = (np.asarray(lat, float) - self.box["south"]) * KM_PER_DEG_LAT
        return self.N - np.interp(km, self.zk, self.zb)   # flip: row 0 = north

    def lon(self, x):
        return self.box["west"] + np.interp(np.asarray(x, float), self.xb, self.xk) / self.kx

    def lat(self, z):
        return self.box["south"] + np.interp(self.N - np.asarray(z, float), self.zb, self.zk) / KM_PER_DEG_LAT
