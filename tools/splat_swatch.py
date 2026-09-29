"""Build a throwaway flat world for two in-game reads: terrain paint, and road width.

WHAT THE FIRST VERSION GOT WRONG -- read this before touching the CASES table.

v1 painted every splat3/splat4 channel at 255/128/30 to discover what each one did. splat4.B is
not a texture: it is WATER SURFACE HEIGHT IN BLOCKS. Painting it 255 and 128 over ground at y=40
created 32x32 water columns 215 and 88 blocks tall, which rendered as floating water and fog voids
and eventually stopped the world loading at all. The channel map is now known from the decompiled
engine, so nothing here needs to probe blindly again, and splat4.B is refused outright below.

    splat3.R = terrAsphalt      splat4.R = texture id 200, still unidentified
    splat3.G = terrGravel       splat4.G = terrDirt
    splat3.B = terrConcrete     splat4.B = WATER HEIGHT -- never paint
    splat3.A = terrSand/Desert  splat4.A = unused

Channel values are MicroSplat blend weights, so partials are legal and visible. Separately, the
block under the paint only flips at a hard threshold: splat3 R>127 becomes terrAsphalt, else G>127
becomes terrGravel, else B>127 hits a biomes.xml entry that ships commented out, so concrete and
sand are paint only and never change the voxel. That is the whole basis for painting city lots:
visually distinct ground with no block cost. The 126/130 pairs below straddle that threshold so it
can be seen rather than trusted.

WHAT THE GRID STILL ANSWERS
- what each texture actually looks like underfoot, and whether partial weights read as distinct
- what texture id 200 (splat4.R) is -- the one channel the engine dig could not name
- whether stacking channels blends or one wins

WHAT THE STRIPS ANSWER
- how wide a road should be, judged by standing next to one at 1 block = 1 real metre

    python tools/splat_swatch.py [--name "Splat Swatch"] [--size 10240]

--size 10240 reuses the shell verbatim and is the proven path. Smaller sizes rewrite map_info.xml
and rescale radiation.png; that is untested against the engine, so fall back to 10240 if a smaller
world refuses to load. Writes out/swatch_key.png to match against screenshots.
"""
import argparse, os, re, shutil, sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tucson.assemble import GW, SHELL_DIR, write_dtm, write_spawnpoints  # noqa: E402
from tucson.config import ROOT  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

GROUND = 40.0
SWATCH = 32
GAP = 16
COLS = 6
DESERT = (0xFF, 0xE4, 0x77)
SHELL_SIZE = 10240          # the shell's own world size, and its radiation.png scale divisor
RAD_DIV = 32                # shell radiation.png is 320 px for a 10240 world

# (label, splat3 RGBA, splat4 RGBA). splat4.B stays 0 in every case -- see the module docstring.
CASES = [
    ("bare control",   (0, 0, 0, 0),         (0, 0, 0, 0)),
    # asphalt, and the block-flip threshold either side of 127
    ("asphalt 255",    (255, 0, 0, 0),       (0, 0, 0, 0)),
    ("asphalt 192",    (192, 0, 0, 0),       (0, 0, 0, 0)),
    ("asphalt 130",    (130, 0, 0, 0),       (0, 0, 0, 0)),
    ("asphalt 126",    (126, 0, 0, 0),       (0, 0, 0, 0)),
    ("asphalt 64",     (64, 0, 0, 0),        (0, 0, 0, 0)),
    # gravel
    ("gravel 255",     (0, 255, 0, 0),       (0, 0, 0, 0)),
    ("gravel 130",     (0, 130, 0, 0),       (0, 0, 0, 0)),
    ("gravel 126",     (0, 126, 0, 0),       (0, 0, 0, 0)),
    # concrete -- paint only, the block never changes
    ("concrete 255",   (0, 0, 255, 0),       (0, 0, 0, 0)),
    ("concrete 130",   (0, 0, 130, 0),       (0, 0, 0, 0)),
    ("concrete 64",    (0, 0, 64, 0),        (0, 0, 0, 0)),
    # sand / desert
    ("sand 255",       (0, 0, 0, 255),       (0, 0, 0, 0)),
    ("sand 128",       (0, 0, 0, 128),       (0, 0, 0, 0)),
    # splat4: dirt, and the unidentified texture id 200
    ("dirt 255",       (0, 0, 0, 0),         (0, 255, 0, 0)),
    ("dirt 128",       (0, 0, 0, 0),         (0, 128, 0, 0)),
    ("tex200 255",     (0, 0, 0, 0),         (255, 0, 0, 0)),
    ("tex200 128",     (0, 0, 0, 0),         (128, 0, 0, 0)),
    # stacking: blend, or does one win?
    ("asph+grav 255",  (255, 255, 0, 0),     (0, 0, 0, 0)),
    ("asph+conc 255",  (255, 0, 255, 0),     (0, 0, 0, 0)),
    ("conc+sand 255",  (0, 0, 255, 255),     (0, 0, 0, 0)),
    ("R G B 255",      (255, 255, 255, 0),   (0, 0, 0, 0)),
    ("R G B A 255",    (255, 255, 255, 255), (0, 0, 0, 0)),
    ("conc128+dirt128", (0, 0, 128, 0),      (0, 128, 0, 0)),
]

# Road widths to judge by eye. First three are what the map ships today; the rest are the
# real-metre candidates. A US lane is 3.66 m, so 2 lanes = 8, 4 lanes + turn = 19, 6 + turn = 26.
STRIPS = [
    ("tertiary now", 5), ("secondary now", 7), ("primary now", 8),
    ("link", 8), ("tertiary", 14), ("motorway/carriageway", 20),
    ("secondary", 22), ("trunk", 24), ("primary", 26), ("runway", 50),
]
STRIP_LEN = 240
STRIP_GAP = 24

ASPHALT3 = (255, 0, 0, 0)          # strips are painted asphalt: splat3.R above the 127 threshold


def layout(n):
    rows = (len(CASES) + COLS - 1) // COLS
    gw = COLS * SWATCH + (COLS - 1) * GAP
    gh = rows * SWATCH + (rows - 1) * GAP
    ox, oy = n // 2 - gw // 2, n // 2 - gh // 2 - 200
    placed = [(lab, oy + (i // COLS) * (SWATCH + GAP), ox + (i % COLS) * (SWATCH + GAP), c3, c4)
              for i, (lab, c3, c4) in enumerate(CASES)]
    sy = oy + gh + 80
    sx = n // 2 - sum(w + STRIP_GAP for _, w in STRIPS) // 2
    strips = []
    for lab, w in STRIPS:
        strips.append((lab, w, sy, sx)); sx += w + STRIP_GAP
    return rows, ox, oy, placed, strips


def shell_for(size, dst, shell=SHELL_DIR):
    """Copy the engine files, rescaling the ones that are world-size dependent."""
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(os.path.join(shell, "main.ttw"), os.path.join(dst, "main.ttw"))
    rad = Image.open(os.path.join(shell, "radiation.png"))
    if size != SHELL_SIZE:
        rad = rad.resize((size // RAD_DIV, size // RAD_DIV), Image.NEAREST)
    rad.save(os.path.join(dst, "radiation.png"))
    info = open(os.path.join(shell, "map_info.xml"), encoding="utf-8-sig").read()
    info = re.sub(r'(name="HeightMapSize" value=")[^"]*"', rf'\g<1>{size},{size}"', info)
    open(os.path.join(dst, "map_info.xml"), "w", encoding="utf-8").write(info)


def build(name, size, shell=SHELL_DIR):
    dst = os.path.join(GW, name)
    if os.path.isdir(dst):
        raise SystemExit(f"{dst} exists -- delete it first, a reused folder keeps stale derived files")
    shell_for(size, dst, shell)

    n = size
    rows, ox, oy, placed, strips = layout(n)
    blk = np.full((n, n), GROUND, np.float32)
    s3 = np.zeros((n, n, 4), np.uint8)
    s4 = np.zeros((n, n, 4), np.uint8)

    def paint(r0, c0, h, w, c3, c4):
        if c4[2]:
            raise ValueError(f"splat4.B is water height, never a texture -- refusing to paint {c4}")
        if any(c3):
            s3[r0:r0 + h, c0:c0 + w] = c3
        if any(c4):
            s4[r0:r0 + h, c0:c0 + w] = c4

    for _lab, r, c, c3, c4 in placed:
        paint(r, c, SWATCH, SWATCH, c3, c4)
    for _lab, w, sy, sx in strips:
        paint(sy, sx, STRIP_LEN, w, ASPHALT3, (0, 0, 0, 0))

    write_dtm(os.path.join(dst, "dtm.raw"), blk)
    Image.fromarray(s3, "RGBA").save(os.path.join(dst, "splat3.png"))
    Image.fromarray(s4, "RGBA").save(os.path.join(dst, "splat4.png"))

    small = np.zeros((n // 8, n // 8, 4), np.uint8)
    small[..., 0], small[..., 1], small[..., 2], small[..., 3] = DESERT + (255,)
    Image.fromarray(small, "RGBA").save(os.path.join(dst, "biomes.png"))

    open(os.path.join(dst, "prefabs.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<prefabs>\n</prefabs>\n')

    spawn_r, spawn_c = oy - 60, ox + (COLS * (SWATCH + GAP)) // 2
    write_spawnpoints(os.path.join(dst, "spawnpoints.xml"),
                      [(spawn_c - n // 2, GROUND + 1, (n - 1 - spawn_r) - n // 2, 180)])

    key = os.path.join(ROOT, "out", "swatch_key.png")
    write_key(key, placed, strips, ox, oy, rows)
    return dst, placed, strips, key


def write_key(path, placed, strips, ox, oy, rows):
    """The same layout with labels, for matching against an in-game screenshot."""
    scale = 3
    sx0 = min(s[3] for s in strips)
    span = max(s[3] + s[1] for s in strips) - sx0
    w = max(COLS * (SWATCH + GAP), span + 4) * scale
    h = (rows * (SWATCH + GAP) + 140 + STRIP_LEN) * scale
    im = Image.new("RGB", (w, h), (232, 206, 168)); d = ImageDraw.Draw(im)
    for lab, r, c, _c3, _c4 in placed:
        x, y = (c - ox) * scale, (r - oy) * scale
        d.rectangle([x, y, x + SWATCH * scale, y + SWATCH * scale], fill=(90, 90, 96))
        d.text((x + 3, y + 3), lab, fill=(255, 255, 255))
    for lab, sw, sy, sx in strips:
        x, y = (sx - sx0) * scale, (sy - oy) * scale
        d.rectangle([x, y, x + sw * scale, y + STRIP_LEN * scale], fill=(60, 60, 64))
        d.text((x, y - 12), f"{lab} ({sw})", fill=(20, 20, 20))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Splat Swatch")
    ap.add_argument("--size", type=int, default=SHELL_SIZE)
    ap.add_argument("--shell", default=SHELL_DIR)
    a = ap.parse_args()
    dst, placed, strips, key = build(a.name, a.size, a.shell)
    print(f"wrote {dst}  (size {a.size})")
    print(f"key   {key}")
    print(f"\n{len(placed)} swatches, {COLS} per row, left-to-right then top-to-bottom, "
          f"{SWATCH}x{SWATCH} blocks each:")
    for i in range(0, len(placed), COLS):
        print("  " + "  ".join(f"{p[0]:<17}" for p in placed[i:i + COLS]))
    print(f"\n{len(strips)} strips, {STRIP_LEN} blocks long, west to east:")
    print("  " + "  ".join(f"{lab} ({w})" for lab, w, _, _ in strips))
    print("\nNo water anywhere -- splat4.B is left at 0 by construction. Delete the world when done.")
