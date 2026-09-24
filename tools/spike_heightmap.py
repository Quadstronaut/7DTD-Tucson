"""SPIKE (throwaway): real Tucson DEM -> importer-mod inputs, uniform scale, terrain only.

Answers: does V3 + CustomHeightMapImporter load a real-DEM 10240 map with correct
orientation, sane heights, and a playable peak?

Source: AWS Terrain Tiles (keyless, public). Terrarium PNG encoding:
    elevation_m = R*256 + G + B/256 - 32768
Output (in ./out/spike/):
    heightmap.png        16-bit gray, 10240^2, top row = north   (mod: height = value/257)
    biomes_source.png    RGB, 10240^2, vanilla biome colors      (mod: +-10 tolerance)
    preview.png          small hillshade-ish preview for eyeballing
"""
import io, math, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "terrarium")
OUT = os.path.join(ROOT, "out", "spike")
N = 10240          # world size (blocks); must equal the in-game RWG size exactly
Z = 13             # tile zoom: ~16 m/px at 32N; enough for a spike

# Square box (km) centered on landmark span; west edge = Old Tucson.
WEST, SOUTH, NORTH = -111.14, 32.10, 32.46
KM_Y = (NORTH - SOUTH) * 110.574                       # N-S extent in km
EAST = WEST + KM_Y / (111.320 * math.cos(math.radians((NORTH + SOUTH) / 2)))  # square in km

# Elevation (m) -> block height. Keep peak below 255 with headroom for POIs/trees.
ELE_LO, ELE_HI = 650.0, 2800.0
BLK_LO, BLK_HI = 35.0, 215.0

# Biome bands (m). Spike-grade; real vegetation zoning comes later.
BIOMES = [(1350, (255, 228, 119)),   # desert  #FFE477
          (2500, (0, 64, 0)),        # forest  #004000
          (1e9, (255, 255, 255))]    # snow    #FFFFFF


def tile_xy(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def fetch(tx, ty):
    p = os.path.join(CACHE, f"{Z}_{tx}_{ty}.png")
    if not os.path.exists(p):
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{tx}/{ty}.png"
        data = urllib.request.urlopen(url, timeout=60).read()
        with open(p, "wb") as f:
            f.write(data)
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def main():
    os.makedirs(CACHE, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    x0, y0 = tile_xy(NORTH, WEST, Z); x1, y1 = tile_xy(SOUTH, EAST, Z)
    txs = range(int(x0), int(x1) + 1); tys = range(int(y0), int(y1) + 1)
    print(f"box W{WEST} E{EAST:.4f} S{SOUTH} N{NORTH}  {KM_Y:.1f} km square  -> {KM_Y*1000/N:.2f} m/block")
    print(f"tiles {len(txs)}x{len(tys)}")
    with ThreadPoolExecutor(8) as ex:
        tiles = {(tx, ty): t for (tx, ty), t in zip(
            [(a, b) for b in tys for a in txs],
            ex.map(lambda k: fetch(*k), [(a, b) for b in tys for a in txs]))}
    mosaic = np.vstack([np.hstack([tiles[(tx, ty)] for tx in txs]) for ty in tys])
    # Crop mosaic to the exact box in fractional tile coords (256 px per tile).
    px = lambda v, base: (v - base) * 256
    l, t = px(x0, txs[0]), px(y0, tys[0]); r, b = px(x1, txs[0]), px(y1, tys[0])
    img = Image.fromarray(mosaic.astype(np.float32), mode="F")
    # Web-Mercator rows are not linear in latitude, but over 0.36 deg the error is ~0.1%: fine for a spike.
    ele = np.asarray(img.transform((N, N), Image.EXTENT, (l, t, r, b), Image.BILINEAR), dtype=np.float32)
    print(f"elevation m: min {ele.min():.0f}  max {ele.max():.0f}")

    blk = BLK_LO + (np.clip(ele, ELE_LO, ELE_HI) - ELE_LO) * (BLK_HI - BLK_LO) / (ELE_HI - ELE_LO)
    val = np.clip(np.round(blk * 257), 0, 65535).astype(np.uint16)
    Image.fromarray(val, mode="I;16").save(os.path.join(OUT, "heightmap.png"))   # row 0 = north (image top)
    print(f"blocks: min {blk.min():.1f}  max {blk.max():.1f}")

    rgb = np.zeros((N, N, 3), np.uint8); prev = np.full(ele.shape, True)
    lo = -1e9
    for hi, col in BIOMES:
        m = (ele >= lo) & (ele < hi); rgb[m] = col; lo = hi
    Image.fromarray(rgb, "RGB").save(os.path.join(OUT, "biomes_source.png"))

    small = Image.fromarray(((blk - blk.min()) / (np.ptp(blk) + 1e-9) * 255).astype(np.uint8)).resize((1024, 1024))
    small.save(os.path.join(OUT, "preview.png"))
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
