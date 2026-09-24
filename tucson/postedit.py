"""Edit a generated world before its first load (in-game check of Plan 1, Task 5).

python -m tucson.postedit "<world name>"
Backs up prefabs.xml / splat3.png to *.orig once.
"""
import os, re, shutil, sys
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
    s = re.sub(r"<prefabs\s*/>", "<prefabs>\n</prefabs>", s)       # empty world writes a self-closing tag
    if "</prefabs>" not in s:
        raise ValueError(f"{p}: no <prefabs> root")
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
    for i, (name, yoff) in enumerate([("remnant_sports_center_01", -9), ("skyscraper_01", -1), ("football_stadium", -15)]):  # YOffsets read from prefab XML
        x, z = 200 * i, 0
        items.append((name, x, int(round(world_y(w, x, z))) + yoff + 1, z, 0))
    add_decorations(w, items)
    # Asphalt stripe: 8 px tall, 600 px wide, image rows near center. Records which way splat3 rows run.
    paint_splat3(w, slice(5120 - 300, 5120 - 292), slice(5120, 5720))
    print("edited", w, items)
