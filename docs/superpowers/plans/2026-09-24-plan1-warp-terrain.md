# Plan 1 — Warp + Terrain + Post-Edit Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the real (warped, landmark-flattened) Tucson heightmap + biome map for the importer mod, and prove the game honors post-generation edits to `prefabs.xml` / `splat3.png`.

**Architecture:** Small `tucson` Python package. `warp.py` maps lat/lon → world pixel via separable piecewise-linear control points read from `data/world.toml` (single source of truth). `dem.py` fetches/caches AWS terrarium tiles and samples elevation at any lat/lon. `zones.py` fetches OSM landmark polygons (cached) and rasterizes them in warped space. `terrain.py` builds the warped elevation grid, flattens zones, writes `heightmap.png` + `biomes_source.png`. `postedit.py` edits a generated world for the in-game check.

**Tech Stack:** Python 3.14, numpy, Pillow, scipy (all installed), pytest, stdlib `tomllib`/`urllib`. No shapely (polygons rasterized with `PIL.ImageDraw`).

**Spec:** `docs/specs/2026-09-24-tucson-map-design.md` (§4, §5, §6, §13).

## Global Constraints

- World size **10240**; heightmap.png must be exactly 10240×10240, square, 16-bit gray, **top row = north**; mod height = value/257.
- dtm.raw row 0 = south; prefab position = (px − 5120, y, row_from_south − 5120); prefab Y = terrain + YOffset + 1.
- Biome colors exact: desert `#FFE477`, forest `#004000`, snow `#FFFFFF` (mod tolerance ±10; unknown → forest).
- Box: W −111.14, E −110.72, S 32.10, N 32.46. West wall = Old Tucson.
- Elevation → blocks: 650 m → 35, 2800 m → 215 (linear, clamped) — spike-verified range.
- Never guess game behavior; anything unverified is checked in-game (Task 5).
- Mod DLL needs game launched **without EAC**; remove mod from `<game>/Mods` after generating.
- Commit + push after each task (`master`, private repo `Quadstronaut/7DTD-Tucson`).

## Review Focus

1. Warp must be strictly monotonic and hit 0 / 10240 at the box edges — a non-monotonic control list would fold the map. (Test in Task 1.)
2. Lat/lon outside the box must clamp, not wrap or crash (OSM polygons spill past the box). (Test in Task 1.)
3. Flattened zone must be one height inside and blend smoothly at the edge (no cliff wall around DM AFB). (Test in Task 3.)
4. North-up orientation must survive the warp (Lemmon top-right). (Test in Task 3.)
5. Network flakiness (Overpass 429/504) must retry and cache, never silently produce an empty zone. (Test in Task 2.)

## File Structure

```
tucson/__init__.py        empty
tucson/config.py          load data/world.toml → dict
tucson/warp.py            Warp class: lon→x, lat→z(row from north), inverse
tucson/dem.py             terrarium tile cache + bilinear elevation sampler
tucson/zones.py           OSM polygon fetch/cache; rasterize to mask in warped space
tucson/terrain.py         build elevation grid, flatten zones, write PNGs (CLI: python -m tucson.terrain)
tucson/postedit.py        add test prefabs + asphalt stripe to a generated world (CLI)
data/world.toml           box, size, height map, warp control points, zones, biome bands
tests/test_warp.py, tests/test_zones.py, tests/test_terrain.py
```

---

### Task 1: Config + Warp

**Files:**
- Create: `data/world.toml`, `tucson/__init__.py`, `tucson/config.py`, `tucson/warp.py`
- Test: `tests/test_warp.py`

**Interfaces:**
- Produces: `config.load() -> dict`; `Warp(cfg)` with `.x(lon: float|ndarray) -> float|ndarray` (0..N, west→east), `.z(lat) -> …` (0..N, **north→south**, i.e. image row), `.lon(x)`, `.lat(z)` inverses; `N: int`.

- [ ] **Step 1: Write data/world.toml**

```toml
size = 10240

[box]
west = -111.14
east = -110.72
south = 32.10
north = 32.46

[height]            # elevation (m) -> block height, linear + clamp
ele_lo = 650.0
ele_hi = 2800.0
blk_lo = 35.0
blk_hi = 215.0

# Separable piecewise-linear warp. km measured from box west / box south.
# Pairs are [real_km, world_block]; must start at [0,0] and end at [span_km, size].
[warp]
x = [[0.0, 0], [3.0, 1200], [14.0, 3400], [19.5, 5600], [21.5, 6000], [31.5, 8500], [33.5, 9100], [39.53, 10240]]
z = [[0.0, 0], [3.0, 700], [10.0, 2700], [12.5, 3500], [16.0, 4900], [22.0, 6300], [36.0, 9000], [39.81, 10240]]

[biomes]            # upper bound (m) -> color; checked in order
bands = [[1350.0, "FFE477"], [2500.0, "004000"], [1e9, "FFFFFF"]]

# Zones flattened to their median elevation. osm = Overpass selector (polygon source);
# rect = [south, west, north, east] fallback / explicit area.
[[zones]]
name = "dm_afb"
osm = 'relation["name"="Davis-Monthan Air Force Base"]["landuse"="military"]'
[[zones]]
name = "tus_airport"
osm = 'relation["aeroway"="aerodrome"]["iata"="TUS"]'
[[zones]]
name = "ua_campus"
osm = 'relation["amenity"="university"]["name"="University of Arizona"]'
[[zones]]
name = "old_tucson"
osm = 'way["tourism"="theme_park"]["name"="Old Tucson"]'
[[zones]]
name = "downtown"
rect = [32.214, -110.980, 32.230, -110.962]
[[zones]]
name = "skate_country"
rect = [32.2045, -110.8245, 32.2082, -110.8200]
```

(x span: (−110.72 − −111.14) × 111.320 × cos(32.28°) = 39.53 km; z span: 0.36 × 110.574 = 39.81 km. Control points are the tunable scale budget: 2.5 m/block at downtown/UA and Old Tucson, ~4 at DM/Skate Country, ~5 in the mountains/filler.)

- [ ] **Step 2: Write the failing tests** — `tests/test_warp.py`

```python
import numpy as np, pytest
from tucson.config import load
from tucson.warp import Warp

CFG = load()
W = Warp(CFG)
B = CFG["box"]

def test_edges_hit_bounds():
    assert W.x(B["west"]) == pytest.approx(0, abs=1e-6)
    assert W.x(B["east"]) == pytest.approx(10240, abs=1e-3)
    assert W.z(B["north"]) == pytest.approx(0, abs=1e-3)      # row 0 = north
    assert W.z(B["south"]) == pytest.approx(10240, abs=1e-6)

def test_monotonic():
    lons = np.linspace(B["west"], B["east"], 1000)
    lats = np.linspace(B["south"], B["north"], 1000)
    assert np.all(np.diff(W.x(lons)) > 0)
    assert np.all(np.diff(W.z(lats)) < 0)                     # north-up: higher lat -> smaller row

def test_clamps_outside_box():
    assert W.x(B["west"] - 1) == 0 and W.x(B["east"] + 1) == 10240
    assert W.z(B["north"] + 1) == 0 and W.z(B["south"] - 1) == 10240

def test_inverse_roundtrip():
    lon, lat = -110.9565, 32.2289                              # UA
    assert W.lon(W.x(lon)) == pytest.approx(lon, abs=1e-6)
    assert W.lat(W.z(lat)) == pytest.approx(lat, abs=1e-6)

def test_landmarks_ordering():
    # Old Tucson west of downtown west of DM west of Lemmon; Lemmon north of everything.
    assert W.x(-111.1286) < W.x(-110.9748) < W.x(-110.8819) < W.x(-110.7890)
    assert W.z(32.4424) < W.z(32.2289) < W.z(32.1662) < W.z(32.1147)

def test_bad_control_points_rejected():
    bad = {**CFG, "warp": {"x": [[0, 0], [5, 100], [4, 200], [39.53, 10240]], "z": CFG["warp"]["z"]}}
    with pytest.raises(ValueError):
        Warp(bad)
```

- [ ] **Step 3: Run to verify fail** — `python -m pytest tests/test_warp.py -q` → FAIL (ModuleNotFoundError: tucson).

- [ ] **Step 4: Implement** — `tucson/__init__.py` (empty), `tucson/config.py`, `tucson/warp.py`

```python
# tucson/config.py
"""Single source of truth: data/world.toml."""
import os, tomllib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(path=None):
    with open(path or os.path.join(ROOT, "data", "world.toml"), "rb") as f:
        return tomllib.load(f)
```

```python
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
```

- [ ] **Step 5: Run tests** — `python -m pytest tests/test_warp.py -q` → 6 passed.
- [ ] **Step 6: Commit** — `git add data tucson tests && git commit -m "feat(warp): separable piecewise-linear lat/lon->world warp + world.toml" && git push`

---

### Task 2: DEM sampler + OSM zones

**Files:**
- Create: `tucson/dem.py`, `tucson/zones.py`
- Test: `tests/test_zones.py`

**Interfaces:**
- Consumes: `Warp.x/.z`, `config.load()`.
- Produces: `dem.sample(lat: ndarray, lon: ndarray, zoom=14) -> ndarray[m]`; `zones.polygons(cfg) -> dict[name, list[list[(lat,lon)]]]` (cached in `cache/osm/<name>.json`); `zones.mask(ring_list, warp, N) -> ndarray[bool] (N×N, row 0 north)`; `zones.overpass(query) -> dict` retries 429/504 then raises.

- [ ] **Step 1: Failing tests** — `tests/test_zones.py`

```python
import numpy as np, pytest
from tucson import zones
from tucson.config import load
from tucson.warp import Warp

CFG = load(); W = Warp(CFG)

def test_rect_zone_mask_is_filled_box():
    rings = zones.rect_rings([32.2045, -110.8245, 32.2082, -110.8200])
    m = zones.mask(rings, W, 10240)
    assert m.sum() > 0
    ys, xs = np.nonzero(m)
    assert xs.min() == pytest.approx(W.x(-110.8245), abs=2)
    assert ys.min() == pytest.approx(W.z(32.2082), abs=2)      # north edge = smallest row

def test_overpass_retries_then_raises(monkeypatch):
    calls = []
    def boom(*a, **k):
        calls.append(1); raise zones.urllib.error.HTTPError("u", 504, "timeout", None, None)
    monkeypatch.setattr(zones.urllib.request, "urlopen", boom)
    monkeypatch.setattr(zones.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        zones.overpass("node(1);out;")
    assert len(calls) == zones.RETRIES

def test_empty_osm_result_is_error(monkeypatch):
    monkeypatch.setattr(zones, "overpass", lambda q: {"elements": []})
    with pytest.raises(RuntimeError, match="no polygon"):
        zones.fetch_rings("x", 'way["name"="nope"]', cache_dir=None)
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_zones.py -q` → FAIL (no module).

- [ ] **Step 3: Implement**

```python
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
```

```python
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


def mask(rings, warp, N):
    """Rasterize rings (lat,lon) into an N×N bool mask, row 0 = north. Relation outer
    members may be split into several ways; each ring is filled independently."""
    img = Image.new("1", (N, N), 0); d = ImageDraw.Draw(img)
    for ring in rings:
        lat = np.array([p[0] for p in ring]); lon = np.array([p[1] for p in ring])
        pts = list(zip(warp.x(lon).tolist(), warp.z(lat).tolist()))
        if len(pts) >= 3:
            d.polygon(pts, fill=1)
    return np.asarray(img, dtype=bool)
```

Note: split relation members (open ways) fill as their own chords — acceptable for flattening (verified visually in Task 3's preview); if a zone looks wrong, replace its `osm` with an explicit `rect` in world.toml.

- [ ] **Step 4: Run** — `python -m pytest tests/test_zones.py -q` → 3 passed.
- [ ] **Step 5: Commit** — `git add tucson tests && git commit -m "feat(zones,dem): cached OSM landmark polygons and terrarium DEM sampler" && git push`

---

### Task 3: Terrain build (heightmap.png + biomes_source.png)

**Files:**
- Create: `tucson/terrain.py`
- Test: `tests/test_terrain.py`

**Interfaces:**
- Consumes: `Warp`, `dem.sample`, `zones.polygons/mask`, `config.load`.
- Produces: `flatten(ele, m, feather=24) -> ndarray`; `to_blocks(ele, cfg) -> ndarray`; `biome_rgb(ele, cfg) -> uint8[N,N,3]`; CLI `python -m tucson.terrain [--size N]` writes `out/world/heightmap.png`, `out/world/biomes_source.png`, `out/world/preview.png`.

- [ ] **Step 1: Failing tests** — `tests/test_terrain.py`

```python
import numpy as np
from tucson import terrain
from tucson.config import load

CFG = load()

def test_flatten_inside_constant_and_edge_blends():
    ele = np.tile(np.linspace(700, 800, 200, dtype=np.float32), (200, 1))   # ramp W->E
    m = np.zeros((200, 200), bool); m[60:140, 60:140] = True
    out = terrain.flatten(ele, m, feather=20)
    inside = out[m]
    assert np.ptp(inside) < 1e-3                                  # flat
    assert abs(inside[0] - np.median(ele[m])) < 1e-3
    step = np.abs(np.diff(out, axis=1)).max()
    assert step < 5 * np.abs(np.diff(ele, axis=1)).max() + 1e-3   # no cliff at the edge
    assert np.allclose(out[:, :30], ele[:, :30])                  # far away untouched

def test_to_blocks_range_and_clamp():
    b = terrain.to_blocks(np.array([0, 650, 2800, 9000], np.float32), CFG)
    assert b.tolist() == [35.0, 35.0, 215.0, 215.0]

def test_biome_colors():
    rgb = terrain.biome_rgb(np.array([[800, 1800, 2700]], np.float32), CFG)
    assert rgb[0].tolist() == [[255, 228, 119], [0, 64, 0], [255, 255, 255]]

def test_small_build_north_up(tmp_path):
    out = terrain.build(size=512, out_dir=str(tmp_path), zones_on=False)
    r, c = np.unravel_index(np.argmax(out), out.shape)
    assert r < 512 * 0.25 and c > 512 * 0.6                       # Lemmon: top-right
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_terrain.py -q` → FAIL.

- [ ] **Step 3: Implement** — `tucson/terrain.py`

```python
"""Warped real-DEM terrain -> importer-mod inputs.

python -m tucson.terrain            # full 10240 build into out/world/
"""
import argparse, os
import numpy as np
from PIL import Image
from scipy import ndimage
from . import dem, zones
from .config import ROOT, load
from .warp import Warp

Image.MAX_IMAGE_PIXELS = None


def flatten(ele, m, feather=24):
    """Set masked area to its median; blend linearly over `feather` px outside it."""
    if not m.any():
        return ele
    target = float(np.median(ele[m]))
    dist = ndimage.distance_transform_edt(~m)                     # 0 inside, grows outward
    w = np.clip(1 - dist / feather, 0, 1).astype(np.float32)      # 1 inside -> 0 at feather
    return ele * (1 - w) + target * w


def to_blocks(ele, cfg):
    h = cfg["height"]
    e = np.clip(ele, h["ele_lo"], h["ele_hi"])
    return h["blk_lo"] + (e - h["ele_lo"]) * (h["blk_hi"] - h["blk_lo"]) / (h["ele_hi"] - h["ele_lo"])


def biome_rgb(ele, cfg):
    rgb = np.zeros(ele.shape + (3,), np.uint8); lo = -np.inf
    for hi, hexcol in cfg["biomes"]["bands"]:
        m = (ele >= lo) & (ele < hi)
        rgb[m] = [int(hexcol[i:i + 2], 16) for i in (0, 2, 4)]; lo = hi
    return rgb


def elevation_grid(warp, size, rows_per_chunk=512):
    """Sample the DEM at every output pixel center (inverse warp). Chunked for memory."""
    scale = warp.N / size
    xs = (np.arange(size) + 0.5) * scale
    lon = warp.lon(xs)
    out = np.empty((size, size), np.float32)
    for r0 in range(0, size, rows_per_chunk):
        rows = np.arange(r0, min(size, r0 + rows_per_chunk))
        lat = warp.lat((rows + 0.5) * scale)
        LA, LO = np.meshgrid(lat, lon, indexing="ij")
        out[rows] = dem.sample(LA, LO)
    return out


def build(size=None, out_dir=None, zones_on=True):
    cfg = load(); size = size or cfg["size"]; warp = Warp(cfg)
    out_dir = out_dir or os.path.join(ROOT, "out", "world"); os.makedirs(out_dir, exist_ok=True)
    ele = elevation_grid(warp, size)
    if zones_on:
        small = Warp({**cfg, "size": size, "warp": {
            "x": [[k, v * size / cfg["size"]] for k, v in cfg["warp"]["x"]],
            "z": [[k, v * size / cfg["size"]] for k, v in cfg["warp"]["z"]]}})
        for name, rings in zones.polygons(cfg).items():
            m = zones.mask(rings, small, size)
            print(f"zone {name}: {m.sum()} px")
            ele = flatten(ele, m, feather=max(4, int(24 * size / cfg["size"])))
    blk = to_blocks(ele, cfg)
    Image.fromarray(np.round(blk * 257).astype(np.uint16)).save(os.path.join(out_dir, "heightmap.png"))
    Image.fromarray(biome_rgb(ele, cfg), "RGB").save(os.path.join(out_dir, "biomes_source.png"))
    prev = ((blk - blk.min()) / (np.ptp(blk) + 1e-9) * 255).astype(np.uint8)
    Image.fromarray(prev).resize((1024, 1024)).save(os.path.join(out_dir, "preview.png"))
    print(f"wrote {out_dir}: blocks {blk.min():.1f}..{blk.max():.1f}")
    return blk


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--size", type=int); ap.add_argument("--no-zones", action="store_true")
    a = ap.parse_args(); build(size=a.size, zones_on=not a.no_zones)
```

- [ ] **Step 4: Run** — `python -m pytest -q` → all pass.
- [ ] **Step 5: Full build** — `python -m tucson.terrain` → prints each zone's pixel count (all > 0) and blocks ≈ 35..215. Open `out/world/preview.png`: Catalinas top-right, Tucson Mtns west, flat rectangles/polygons visible at DM, downtown, UA, airport, Skate Country, Old Tucson.
- [ ] **Step 6: Commit** — `git add tucson tests && git commit -m "feat(terrain): warped DEM heightmap + biomes with flattened landmark zones" && git push`

---

### Task 4: Regenerate world (user, in game)

- [ ] **Step 1:** Copy `vendor/CustomHeightMapImporter` → `<game>/Mods/CustomHeightMapImporter`, then copy `out/world/heightmap.png` + `biomes_source.png` into it.
- [ ] **Step 2 (user):** Launch **without EAC** → New Game → generate RWG 10240 with **Towns = None, Wilderness = None**. Save world; report its name.
- [ ] **Step 3:** Verify: log shows `[HeightMapImporter] Heightmap applied successfully`; `dtm.raw` vs heightmap |diff| < 1 block; `prefabs.xml` has no/near-no decorations (record exactly what RWG still places, e.g. traders).
- [ ] **Step 4:** Move mod back to `vendor/` (game Mods clean). Record results in spec §13 and commit.

---

### Task 5: Post-edit check

**Files:**
- Create: `tucson/postedit.py`

**Interfaces:**
- Consumes: `Warp`, world folder path.
- Produces: `add_decorations(world_dir, items: list[tuple[name,x,y,z,rot]])`, `paint_splat3(world_dir, row_slice, col_slice, channel="R")`, `world_y(world_dir, x, z) -> float` (dtm height at world x/z).

- [ ] **Step 1: Implement** — `tucson/postedit.py`

```python
"""Edit a generated world before its first load (in-game check of Plan 1, Task 5).

python -m tucson.postedit "<world name>"
Backs up prefabs.xml / splat3.png to *.orig once.
"""
import os, shutil, sys
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
GW = os.path.expandvars(r"%APPDATA%\7DaysToDie\GeneratedWorlds")


def _backup(p):
    if not os.path.exists(p + ".orig"):
        shutil.copy2(p, p + ".orig")


def world_y(world_dir, x, z, N=10240):
    d = np.memmap(os.path.join(world_dir, "dtm.raw"), dtype="<u2", mode="r", shape=(N, N))
    return d[z + N // 2, x + N // 2] / 256.0                 # row 0 = south


def add_decorations(world_dir, items):
    p = os.path.join(world_dir, "prefabs.xml"); _backup(p)
    s = open(p, encoding="utf-8-sig").read()
    lines = "".join(f'  <decoration type="model" name="{n}" position="{x},{y},{z}" rotation="{r}" />\n'
                    for n, x, y, z, r in items)
    s = s.replace("</prefabs>", lines + "</prefabs>")
    open(p, "w", encoding="utf-8").write(s)


def paint_splat3(world_dir, rows, cols, channel="R"):
    """rows/cols are IMAGE indices of splat3.png. Orientation of splat3 is verified in-game by this check."""
    p = os.path.join(world_dir, "splat3.png"); _backup(p)
    a = np.array(Image.open(p).convert("RGBA"))
    a[rows, cols] = [255, 0, 0, 255] if channel == "R" else [0, 255, 0, 255]
    Image.fromarray(a, "RGBA").save(p)


if __name__ == "__main__":
    w = os.path.join(GW, sys.argv[1])
    # Spawn-independent, easy to find: three POIs in a row east of world center + a stripe.
    items = []
    for i, (name, yoff) in enumerate([("remnant_sports_center_01", 0), ("skyscraper_01", -1), ("football_stadium", 0)]):
        x, z = 200 * i, 0
        items.append((name, x, int(round(world_y(w, x, z))) + yoff + 1, z, 0))
    add_decorations(w, items)
    # Asphalt stripe: 8 px tall, 600 px wide, image rows near center. Records which way splat3 rows run.
    paint_splat3(w, slice(5120 - 300, 5120 - 292), slice(5120, 5720))
    print("edited", w, items)
```

(YOffset values used above must be read from each prefab's XML before running — `remnant_sports_center_01`, `skyscraper_01` (−1, verified), `football_stadium`. Update the tuple list with the real values.)

- [ ] **Step 2:** Read the three YOffsets from `Data/Prefabs/POIs/<name>.xml` and set them in the list; run `python -m tucson.postedit "<world>"`.
- [ ] **Step 3 (user):** Start a new game on that world; teleport/walk to world center (x 0..400, z 0). Report: are the three POIs there, sitting on the ground? Is there an asphalt stripe, and where (north or south of center, ~300 blocks)?
- [ ] **Step 4:** Record in spec: post-edits honored? splat3 row orientation (row 0 = north or south). Commit.

Plan 2 (roads), Plan 3 (landmarks), Plan 4 (neighborhoods) are written after Task 5's answers — they depend on them.
