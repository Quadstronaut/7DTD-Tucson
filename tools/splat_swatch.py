"""Build a throwaway flat world that answers two questions in one in-game visit.

1. WHICH TERRAIN TEXTURE does each splat3/splat4 RGBA channel select, and does a partial value
   blend or index? A grid of painted squares, one per (channel, value) case plus the channel
   combinations RWG itself emits. Walk the grid, screenshot it, read the key printed below.

2. HOW WIDE SHOULD A ROAD BE? Bare strips at the candidate widths, laid side by side, with the
   player standing next to them at 1 block = 1 metre. A 7-block strip and a 26-block strip look
   nothing alike next to a truck, and no amount of arithmetic settles it like standing there.

Everything is flat and featureless on purpose -- nothing here is Tucson, and nothing here should
ever be loaded as the real map.

    python tools/splat_swatch.py [--name "Splat Swatch"]

Writes %APPDATA%/7DaysToDie/GeneratedWorlds/<name> plus out/swatch_key.png (the same grid, drawn
with labels, so a screenshot can be matched square by square).
"""
import argparse, os, sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tucson.assemble import GW, SHELL_DIR, copy_shell, write_dtm, write_spawnpoints  # noqa: E402
from tucson.config import ROOT, load  # noqa: E402

GROUND = 40.0           # flat block height everywhere; well clear of the 255 ceiling
SWATCH = 32             # blocks per painted square
GAP = 16                # bare ground between squares, so edges are unambiguous
COLS = 6
DESERT = (0xFF, 0xE4, 0x77)

# (label, splat3 RGBA, splat4 RGBA). Singles first, then the combinations RWG actually emits --
# measured in "Cesetalu Mountains": splat3 R 1.49%, G 0.80%, A 2.30% (~= R + G), splat4 B 2.63%
# at value 30. That pattern says A is probably a coverage/blend mask rather than a texture, and
# splat4 B carries something at a low constant value. These cases are built to prove or kill that.
CASES = []
for _ch, _i in (("s3R", 0), ("s3G", 1), ("s3B", 2), ("s3A", 3)):
    for _v in (255, 128, 30):
        _a = [0, 0, 0, 0]; _a[_i] = _v
        CASES.append((f"{_ch}={_v}", tuple(_a), (0, 0, 0, 0)))
for _ch, _i in (("s4R", 0), ("s4G", 1), ("s4B", 2), ("s4A", 3)):
    for _v in (255, 128, 30):
        _a = [0, 0, 0, 0]; _a[_i] = _v
        CASES.append((f"{_ch}={_v}", (0, 0, 0, 0), tuple(_a)))
CASES += [
    ("s3 R+A 255", (255, 0, 0, 255), (0, 0, 0, 0)),        # what write_splat3 emits for asphalt
    ("s3 G+A 255", (0, 255, 0, 255), (0, 0, 0, 0)),        # ...and for gravel
    ("s3 B+A 255", (0, 0, 255, 255), (0, 0, 0, 0)),
    ("s3A255 s4B30", (0, 0, 0, 255), (0, 0, 30, 0)),       # the exact Cesetalu combination
    ("s3A255 s4B255", (0, 0, 0, 255), (0, 0, 255, 0)),
    ("s3 RGB+A 255", (255, 255, 255, 255), (0, 0, 0, 0)),  # all three at once: blend or last-wins?
]

# Bare strips for judging road width by eye, at 1 block = 1 real metre. Painted with whatever the
# grid proves is asphalt; until then they use the current asphalt convention (splat3 R + A).
STRIPS = [
    ("tertiary now", 5), ("secondary now", 7), ("primary now", 8),
    ("link real", 8), ("tertiary real", 14), ("motorway real", 20),
    ("secondary real", 22), ("trunk real", 24), ("primary real", 26), ("runway real", 50),
]
STRIP_LEN = 240
STRIP_GAP = 24


def grid_origin(n, rows):
    """Top-left block of the swatch grid, centred on the map."""
    w = COLS * SWATCH + (COLS - 1) * GAP
    h = rows * SWATCH + (rows - 1) * GAP
    return n // 2 - w // 2, n // 2 - h // 2 - 200        # grid sits north of the strips


def paint(s3, s4, r0, c0, h, w, c3, c4):
    if any(c3):
        s3[r0:r0 + h, c0:c0 + w] = c3
    if any(c4):
        s4[r0:r0 + h, c0:c0 + w] = c4


def build(name, shell=SHELL_DIR):
    cfg = load(); n = int(cfg["size"])
    dst = os.path.join(GW, name)
    copy_shell(shell, dst)

    blk = np.full((n, n), GROUND, np.float32)
    s3 = np.zeros((n, n, 4), np.uint8)
    s4 = np.zeros((n, n, 4), np.uint8)

    rows = (len(CASES) + COLS - 1) // COLS
    ox, oy = grid_origin(n, rows)
    placed = []
    for i, (label, c3, c4) in enumerate(CASES):
        r = oy + (i // COLS) * (SWATCH + GAP)
        c = ox + (i % COLS) * (SWATCH + GAP)
        paint(s3, s4, r, c, SWATCH, SWATCH, c3, c4)
        placed.append((label, r, c))

    # Width strips, laid out running north-south so you can walk along them.
    sy = oy + rows * (SWATCH + GAP) + 80
    sx = n // 2 - sum(w + STRIP_GAP for _, w in STRIPS) // 2
    strips = []
    for label, w in STRIPS:
        paint(s3, s4, sy, sx, STRIP_LEN, w, (255, 0, 0, 255), (0, 0, 0, 0))
        strips.append((label, w, sy, sx))
        sx += w + STRIP_GAP

    write_dtm(os.path.join(dst, "dtm.raw"), blk)
    Image.fromarray(s3, "RGBA").save(os.path.join(dst, "splat3.png"))
    Image.fromarray(s4, "RGBA").save(os.path.join(dst, "splat4.png"))

    small = np.zeros((n // 8, n // 8, 4), np.uint8)
    small[..., 0], small[..., 1], small[..., 2], small[..., 3] = DESERT + (255,)
    Image.fromarray(small, "RGBA").save(os.path.join(dst, "biomes.png"))

    open(os.path.join(dst, "prefabs.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<prefabs>\n</prefabs>\n')

    # Spawn just north of the grid, looking south down it. World coords are centred on the map.
    spawn_r, spawn_c = oy - 60, ox + (COLS * (SWATCH + GAP)) // 2
    write_spawnpoints(os.path.join(dst, "spawnpoints.xml"),
                      [(spawn_c - n // 2, GROUND + 1, (n - 1 - spawn_r) - n // 2, 180)])

    key_path = os.path.join(ROOT, "out", "swatch_key.png")
    write_key(key_path, placed, strips, ox, oy, rows)
    return dst, placed, strips, key_path


def write_key(path, placed, strips, ox, oy, rows):
    """The same layout, drawn with labels, for matching against an in-game screenshot."""
    scale = 3
    sx0 = min(s[3] for s in strips)
    span = max(s[3] + s[1] for s in strips) - sx0            # strips are wider than the grid
    w = max(COLS * (SWATCH + GAP), span + 4) * scale
    h = (rows * (SWATCH + GAP) + 140 + STRIP_LEN) * scale
    im = Image.new("RGB", (w, h), (232, 206, 168)); d = ImageDraw.Draw(im)
    for label, r, c in placed:
        x, y = (c - ox) * scale, (r - oy) * scale
        d.rectangle([x, y, x + SWATCH * scale, y + SWATCH * scale], fill=(90, 90, 96))
        d.text((x + 3, y + 3), label, fill=(255, 255, 255))
    for label, sw, sy, sx in strips:
        x = (sx - sx0) * scale
        y = (sy - oy) * scale
        d.rectangle([x, y, x + sw * scale, y + STRIP_LEN * scale], fill=(60, 60, 64))
        d.text((x, y - 12), f"{label} ({sw})", fill=(20, 20, 20))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Splat Swatch")
    ap.add_argument("--shell", default=SHELL_DIR)
    a = ap.parse_args()
    dst, placed, strips, key = build(a.name, a.shell)
    print(f"wrote {dst}")
    print(f"key   {key}")
    print(f"\n{len(placed)} swatches, {COLS} per row, read left-to-right then top-to-bottom, "
          f"each {SWATCH}x{SWATCH} blocks:")
    for i in range(0, len(placed), COLS):
        print("  " + "  ".join(f"{lab:<15}" for lab, _, _ in placed[i:i + COLS]))
    print(f"\n{len(strips)} width strips, {STRIP_LEN} blocks long, west to east:")
    print("  " + "  ".join(f"{lab} ({w})" for lab, w, _, _ in strips))
    print("\nSpawn drops you north of the grid facing south. Nothing here is Tucson -- delete the "
          "world when you are done.")
