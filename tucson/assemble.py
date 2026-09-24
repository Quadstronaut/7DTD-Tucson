"""Build GeneratedWorlds/<name> from an empty never-loaded RWG shell + our terrain/roads.

python -m tucson.assemble --shell "Tisuviro County" --name Tucson_AZ [--allow-loaded]
"""
import argparse, os, shutil
import numpy as np
from PIL import Image
from . import roads, terrain, zones
from .config import load
from .warp import Warp

GW = os.path.expandvars(r"%APPDATA%\7DaysToDie\GeneratedWorlds")
SHELL_FILES = ["main.ttw", "map_info.xml", "biomes.png", "splat4.png", "radiation.png"]
DERIVED = ("_processed", "_half", "checksums.txt")


def copy_shell(src, dst, allow_loaded=False):
    loaded = [f for f in os.listdir(src) if any(k in f for k in DERIVED)]
    if loaded and not allow_loaded:
        raise RuntimeError(f"shell {src} has been loaded ({loaded[:3]}); pass allow_loaded=True to use it anyway")
    os.makedirs(dst, exist_ok=True)
    for f in SHELL_FILES:
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))


def write_dtm(path, blk):
    np.round(blk[::-1] * 256).clip(0, 65535).astype("<u2").tofile(path)   # flip: dtm row 0 = south


def write_splat3(path, ch):
    a = np.zeros(ch.shape + (4,), np.uint8)
    a[ch == 1] = [255, 0, 0, 255]; a[ch == 2] = [0, 255, 0, 255]
    Image.fromarray(a, "RGBA").save(path)


def write_spawnpoints(path, pts):
    """pts: list of (x, y, z, yaw_deg) in world coords."""
    body = "".join(f'    <spawnpoint position="{x},{y:.2f},{z}" rotation="0,{yaw},0"/>\n' for x, y, z, yaw in pts)
    open(path, "w", encoding="utf-8").write(f"<spawnpoints>\n{body}</spawnpoints>\n")


def spawn_along_motorway(wways, blk, n=12):
    """n spawn points on motorway centerlines, evenly spread; yaw along the road."""
    N = blk.shape[0]; cands = []
    for w in wways:
        if w["cls"] != "motorway":
            continue
        p = roads.densify(w["xy"], 50)
        for a, b in zip(p[:-1], p[1:]):
            yaw = int(np.degrees(np.arctan2(b[0] - a[0], -(b[1] - a[1]))) % 360)   # 0 = north
            cands.append((int(a[0]), int(a[1]), yaw))
    pick = [cands[i] for i in np.linspace(0, len(cands) - 1, n).astype(int)]
    return [(x - N // 2, float(blk[r, x]) + 1, (N - 1 - r) - N // 2, yaw) for x, r, yaw in pick]


def build(shell, name, allow_loaded=False):
    cfg = load(); warp = Warp(cfg); N = cfg["size"]
    dst = os.path.join(GW, name)
    copy_shell(os.path.join(GW, shell), dst, allow_loaded)
    ele = terrain.elevation_grid(warp, N)
    for zname, rings in zones.polygons(cfg).items():
        ele = terrain.flatten(ele, zones.mask(rings, warp, N))
    blk = terrain.to_blocks(ele, cfg).astype(np.float32)
    wways = roads.to_world(roads.fetch_ways(cfg), warp)
    blk, road, ch = roads.grade(blk, wways, cfg)
    write_dtm(os.path.join(dst, "dtm.raw"), blk)
    write_splat3(os.path.join(dst, "splat3.png"), ch)
    open(os.path.join(dst, "prefabs.xml"), "w", encoding="utf-8").write('<?xml version="1.0" encoding="UTF-8"?>\n<prefabs>\n</prefabs>\n')
    write_spawnpoints(os.path.join(dst, "spawnpoints.xml"), spawn_along_motorway(wways, blk))
    print(f"wrote {dst}: {len(wways)} road pieces, {road.sum()} road px")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--shell", required=True); ap.add_argument("--name", default="Tucson_AZ")
    ap.add_argument("--allow-loaded", action="store_true"); a = ap.parse_args()
    build(a.shell, a.name, a.allow_loaded)
