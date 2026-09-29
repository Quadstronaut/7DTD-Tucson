"""Generate Python-authored prefabs and install them as a modlet the game can see.

Two things at once:

SMOKE TEST -- `tucson_smoke_cube`, a 5x5x5 block of plain concrete. Nothing about it is clever;
its only job is to prove that a .tts written by tucson/tts.py actually loads. The round-trip test
proves we can reproduce the engine's own bytes, which is necessary but not sufficient -- until the
game opens one of ours, "we can write prefabs" is a claim, not a fact. Load it in the World
Editor's prefab browser, or drop a decoration into a world's prefabs.xml.

LOT SLABS -- one flat painted slab per colour. The map needs visually distinct ground for city
lots, and splat cannot do it: splat offers five greyish terrain textures and no colour at all.
Block paint does, and paint is a per-block field in the .tts texture section, so a lot becomes a
one-block-tall plate of concrete with a paint id on every face.

Colours are the six concrete paints the game ships (there is no indigo concrete, so ROYGBIV runs
six wide) plus black granite for "mega lots" -- the places that are a compound of many buildings
rather than one, like a mall or an air base, where no single prefab was ever going to fit.

    python tools/make_prefabs.py [--dest <dir>] [--lot-size 32]

Default dest is %APPDATA%/7DaysToDie/Mods/TucsonPrefabs/Prefabs, which the game searches without
touching the Steam install.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tucson import tts  # noqa: E402

MODS = os.path.expandvars(r"%APPDATA%\7DaysToDie\Mods\TucsonPrefabs")
DEST = os.path.join(MODS, "Prefabs")

MODINFO = """<?xml version="1.0" encoding="UTF-8"?>
<xml>
    <Name value="TucsonPrefabs" />
    <DisplayName value="Tucson Prefabs" />
    <Version value="0.1.0" />
    <Description value="Python-authored prefabs for the Pima County map: painted city lots and test geometry." />
    <Author value="Quadstronaut" />
</xml>
"""

SLAB = "concreteShapes:plate"     # what real parking pads use for raised concrete
CUBE = "concreteShapes:cube"


def smoke_cube(dest, n=5):
    """The smallest thing that answers 'does the game load our bytes'."""
    p = tts.Prefab((n, n, n))
    for y in range(n):
        for z in range(n):
            for x in range(n):
                p.set(x, y, z, 1)
    names = {0: "air", 1: CUBE}
    xml = tts.prefab_xml((n, n, n), y_offset=0, tags="navonly")
    return tts.save(dest, "tucson_smoke_cube", p, names, xml)


def lot(dest, name, size, colour):
    """A one-block-tall painted slab. Paint goes on all six faces so rotation never matters."""
    w, d = size
    p = tts.Prefab((w, 1, d))
    paint = tts.PAINT[colour]
    for z in range(d):
        for x in range(w):
            p.set(x, 0, z, 1, paint=paint)
    names = {0: "air", 1: SLAB}
    xml = tts.prefab_xml((w, 1, d), y_offset=0, tags="navonly")
    return tts.save(dest, name, p, names, xml)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=DEST)
    ap.add_argument("--lot-size", type=int, default=32)
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.dest), exist_ok=True)
    mi = os.path.join(os.path.dirname(a.dest), "ModInfo.xml")
    if not os.path.exists(mi):
        open(mi, "w", encoding="utf-8").write(MODINFO)

    made = [smoke_cube(a.dest)]
    s = (a.lot_size, a.lot_size)
    for c in tts.ROYGBIV:
        made.append(lot(a.dest, f"tucson_lot_{c}", s, c))
    made.append(lot(a.dest, "tucson_lot_mega_black", (a.lot_size * 2, a.lot_size * 2), "black"))

    print(f"mod at {os.path.dirname(a.dest)}")
    for b in made:
        t = b + ".tts"
        print(f"  {os.path.basename(b):<26} {os.path.getsize(t):>8} bytes")
    print(f"\n{len(tts.ROYGBIV)} lot colours (no indigo concrete in the game) + one black mega lot.")
    print("Smoke test: open tucson_smoke_cube in the World Editor prefab browser. If it loads, "
          "Python-authored prefabs work and street tiles / the overpass / Skate Country are all "
          "scripted from here.")


if __name__ == "__main__":
    main()
