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
    """Piecewise-linear [elevation_m, block] curve from config; np.interp clamps at both ends."""
    c = np.array(cfg["height"]["curve"], float)
    if np.any(np.diff(c[:, 0]) <= 0) or np.any(np.diff(c[:, 1]) <= 0):
        raise ValueError("height curve must be strictly increasing")
    return np.interp(ele, c[:, 0], c[:, 1]).astype(np.float32)


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
