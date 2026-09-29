"""Painted ground under each landmark: one lot prefab per place, sized to the real parcel.

The map's landmarks are mostly the wrong size for any prefab the game ships -- the three malls are
five to ten times bigger than the biggest stand-in, Davis-Monthan is kilometres across. Until real
buildings exist, the ground itself carries the information: a flat painted slab covering the real
parcel, so a lot reads as a lot instead of as bare desert.

Colour is not decoration. A landmark that is ONE building gets a colour from the ROYGBIV cycle, so
adjacent parcels stay visually separable. A landmark that is really a COMPOUND of many buildings --
a mall, an air base, a campus, a theme park -- gets black, marking it as a placeholder standing in
for something that still has to be built. At a glance the map says what is done and what is not.

Sizes come from the same source the footprint validator uses: the `real_size` override in
landmarks.toml, else the OSM bounding box. Slabs are one block tall and sit flush with the graded
terrain (YOffset -1).

Splat cannot do any of this. It offers five greyish terrain textures and no colour at all, and only
asphalt and gravel even change the voxel. Block paint is the only route to a coloured surface, and
it is a per-block field in the .tts, so a lot is just a plate of concrete with a paint id on it.

    python -m tucson.lots [--dest <dir>] [--max-side 800]
"""
import argparse, os

from . import footprint, landmarks, tts
from .config import load as load_cfg

# A landmark is "compound" when one prefab was never going to represent it -- these get the black
# placeholder slab rather than a colour from the cycle.
MEGA = {"dm_base", "trader_airport", "trader_tucson_mall", "trader_park_place", "trader_el_con",
        "old_tucson_theater"}

# The largest footprint side across all 1866 shipped prefabs is 246 blocks; the 99th percentile is
# 150. A parcel wider than that is outside anything the engine has ever been asked to load, so it
# goes to splat paint instead of a prefab. Splat has no size limit, costs nothing, and paints
# concrete purely visually -- splat3.B's biome entry ships commented out, so the voxel never
# changes. That is exactly right for a mall apron.
MAX_SIDE = 246

# Above this a parcel stops being a lot and becomes a SITE. Davis-Monthan's OSM polygon is 11.1 x
# 8.4 km and the airport's is 4.9 x 5.3 km; painting those solid put 45.8 million pixels -- 43% of
# the whole map -- under concrete, which is both wrong (a air base is mostly not pavement) and
# redundant, since both are already flattened as zones in world.toml.
SPLAT_MAX_SIDE = 1000

SLAB = "concreteShapes:plate"
SPLAT_CONCRETE = 3      # roads.grade channel code; assemble maps it to splat3.B


def plan(entries=None, cfg=None):
    """(slabs, splats, skipped).

    slabs  [(id, (w, d), colour)] small enough to be a prefab
    splats [(id, (w, d))]         too wide for any prefab the engine has loaded -> splat paint
    """
    cfg = cfg or load_cfg()
    entries = entries or landmarks.load()
    real = footprint.real_sizes(entries, cfg["box"])
    slabs, splats, skipped, i = [], [], [], 0
    for e in entries:
        eid = e["id"]
        r = real.get(eid)
        if not r:
            skipped.append((eid, "no footprint"))
            continue
        w, d = (max(1, int(round(v))) for v in r)
        if max(w, d) > SPLAT_MAX_SIDE:
            skipped.append((eid, f"{w}x{d} is a site, not a lot -- handled by zone flattening"))
            continue
        if max(w, d) > MAX_SIDE:
            splats.append((eid, (w, d)))
            continue
        if eid in MEGA:
            colour = "black"
        else:
            colour = tts.ROYGBIV[i % len(tts.ROYGBIV)]
            i += 1
        slabs.append((eid, (w, d), colour))
    return slabs, splats, skipped


def splat_mask(warp, n, entries=None, cfg=None):
    """Boolean image-space mask of every parcel too big to be a prefab. One block = one real metre
    for the built environment, so the parcel's metre size is its block size, centred on the OSM
    point."""
    import numpy as np
    cfg = cfg or load_cfg()
    entries = entries or landmarks.load()
    coords = landmarks.resolve(entries)          # resolve() defaults the box from world.toml
    _slabs, splats, _skipped = plan(entries, cfg)
    mask = np.zeros((n, n), bool)
    for eid, (w, d) in splats:
        lat, lon = coords[eid]
        col, row = int(warp.x(lon)), int(warp.z(lat))
        r0, r1 = max(0, row - d // 2), min(n, row + d - d // 2)
        c0, c1 = max(0, col - w // 2), min(n, col + w - w // 2)
        mask[r0:r1, c0:c1] = True
    return mask


def build(eid, size, colour, dest):
    w, d = size
    p = tts.Prefab((w, 1, d))
    paint = tts.PAINT[colour]
    for z in range(d):
        for x in range(w):
            p.set(x, 0, z, 1, paint=paint)
    xml = tts.prefab_xml((w, 1, d))          # YOffset -1: the single layer lands ON the ground
    return tts.save(dest, f"lot_{eid}", p, {0: "air", 1: SLAB}, xml)


def build_all(dest, entries=None, cfg=None):
    slabs, splats, skipped = plan(entries, cfg)
    made = [(eid, size, colour, build(eid, size, colour, dest)) for eid, size, colour in slabs]
    return made, splats, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.expandvars(r"%APPDATA%\7DaysToDie\LocalPrefabs"))
    ap.add_argument("--max-side", type=int, default=MAX_SIDE)
    a = ap.parse_args()
    globals()["MAX_SIDE"] = a.max_side
    os.makedirs(a.dest, exist_ok=True)
    made, splats, skipped = build_all(a.dest)
    print(f"{len(made)} slab lots -> {a.dest}\n")
    print(f"{'landmark':<22}{'size':>12}{'colour':>10}{'.tts':>12}")
    for eid, (w, d), colour, base in sorted(made, key=lambda r: -r[1][0] * r[1][1]):
        print(f"{eid:<22}{f'{w}x{d}':>12}{colour:>10}{os.path.getsize(base + '.tts'):>12,}")
    if splats:
        print(f"\n{len(splats)} wider than {MAX_SIDE}, the largest footprint the engine has ever "
              f"been shipped -> splat paint instead:")
        for eid, (w, d) in sorted(splats, key=lambda r: -max(r[1])):
            print(f"  {eid:<22} {w}x{d}")
    if skipped:
        print(f"\nskipped {len(skipped)} with no OSM footprint:")
        print("  " + ", ".join(eid for eid, _ in skipped))
        print("\nAdd real_size = [east_west_m, north_south_m] in landmarks.toml for these.")


if __name__ == "__main__":
    main()
