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

# Three different folders, for three different consumers. This tripped us up once already: the
# prefabs went to the user-data Mods folder, did not appear in the in-game prefab browser, and the
# obvious conclusion -- "wrong folder" -- was wrong. The browser reads LocalPrefabs, which is not a
# Mods path at all. So install everywhere rather than argue about it.
#
#   LocalPrefabs           what the in-game World Editor / prefab browser lists
#   <userdata>\Mods\...    modlet path the community and Nexus install instructions use
#   <game>\Mods\...        where the shipped 0_TFP_Harmony mod lives
#
# A prefab referenced by name from a hand-written world prefabs.xml may also need registering in
# rwgmixer.xml; that is still being verified and does not affect the editor browser.
GAME = r"G:\SteamLibrary\steamapps\common\7 Days To Die"
USERDATA = os.path.expandvars(r"%APPDATA%\7DaysToDie")
TARGETS = [
    ("LocalPrefabs", os.path.join(USERDATA, "LocalPrefabs"), None),
    ("userdata mod", os.path.join(USERDATA, "Mods", "TucsonPrefabs", "Prefabs"),
     os.path.join(USERDATA, "Mods", "TucsonPrefabs", "ModInfo.xml")),
    ("game mod", os.path.join(GAME, "Mods", "TucsonPrefabs", "Prefabs"),
     os.path.join(GAME, "Mods", "TucsonPrefabs", "ModInfo.xml")),
]
DEST = TARGETS[0][1]

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
    xml = tts.prefab_xml((n, n, n))                    # YOffset defaults to -1; see prefab_xml
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
    # YOffset -1 puts the slab's single layer ON the ground: y = terrain + YOffset + 1.
    xml = tts.prefab_xml((w, 1, d))
    return tts.save(dest, name, p, names, xml)


def build_all(dest, lot_size):
    made = [smoke_cube(dest)]
    s = (lot_size, lot_size)
    for c in tts.ROYGBIV:
        made.append(lot(dest, f"tucson_lot_{c}", s, c))
    made.append(lot(dest, "tucson_lot_mega_black", (lot_size * 2, lot_size * 2), "black"))
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", help="install to just this folder instead of all three")
    ap.add_argument("--lot-size", type=int, default=32)
    a = ap.parse_args()

    targets = [("custom", a.dest, None)] if a.dest else TARGETS
    for label, dest, modinfo in targets:
        os.makedirs(dest, exist_ok=True)
        if modinfo and not os.path.exists(modinfo):
            os.makedirs(os.path.dirname(modinfo), exist_ok=True)
            open(modinfo, "w", encoding="utf-8").write(MODINFO)
        made = build_all(dest, a.lot_size)
        print(f"{label:<14} {dest}")
    for b in made:
        print(f"  {os.path.basename(b):<26} {os.path.getsize(b + '.tts'):>8} bytes")
    print(f"\n{len(tts.ROYGBIV)} lot colours (the game ships no indigo concrete) + one black mega lot.")
    print("Smoke test: open tucson_smoke_cube in the World Editor prefab browser -- it reads "
          "LocalPrefabs, not either Mods folder. If it loads, Python-authored prefabs work and "
          "street tiles / the overpass / Skate Country are all scripted from here.")


if __name__ == "__main__":
    main()
