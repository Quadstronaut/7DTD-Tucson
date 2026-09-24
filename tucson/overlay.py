"""Debug view: hillshade of out/world/heightmap.png with zone outlines + landmark dots.

python -m tucson.overlay   ->  out/world/zones_overlay.png (1024 px)
"""
import numpy as np
from PIL import Image, ImageDraw
from . import zones
from .config import ROOT, load
from .warp import Warp

Image.MAX_IMAGE_PIXELS = None
COLORS = {"dm_afb": "red", "tus_airport": "orange", "ua_campus": "cyan",
          "old_tucson": "yellow", "downtown": "magenta", "skate_country": "lime"}
DOTS = [("Lemmon", 32.4424, -110.789), ("Skate", 32.2064, -110.8222), ("CityHall", 32.2226, -110.9748)]


def main(S=1024):
    cfg = load(); w = Warp(cfg); f = S / cfg["size"]
    h = np.asarray(Image.open(f"{ROOT}/out/world/heightmap.png").resize((S, S)), dtype=np.float32) / 257
    gy, gx = np.gradient(h)
    img = Image.fromarray(np.clip(128 + (gx - gy) * 60, 0, 255).astype(np.uint8)).convert("RGB")
    d = ImageDraw.Draw(img)
    for n, rings in zones.polygons(cfg).items():
        for ring in zones.stitch(rings):
            pts = [(float(w.x(lo)) * f, float(w.z(la)) * f) for la, lo in ring]
            d.line(pts + [pts[0]], fill=COLORS.get(n, "white"), width=2)
    for name, la, lo in DOTS:
        x, y = float(w.x(lo)) * f, float(w.z(la)) * f
        d.ellipse([x - 4, y - 4, x + 4, y + 4], outline="white"); d.text((x + 6, y - 6), name, fill="white")
    img.save(f"{ROOT}/out/world/zones_overlay.png")


if __name__ == "__main__":
    main()
