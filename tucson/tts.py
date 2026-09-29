"""Read and write 7DTD .tts prefab files from Python.

The format is a flat, uncompressed struct dump -- no checksum, no palette, no RLE -- so a prefab
can be generated outright instead of hand-built in the World Editor. That is what makes scripted
street tiles, a highway overpass module and painted city lots possible at all.

Layout (little-endian throughout, N = x*y*z). Save version 19, the current one for V3.2.0 b10:

    char[4]      'tts\\0'
    uint32       version
    int16        size x, y, z            (y is height)
    uint32[N]    block rawData           (BlockValueV3, see pack_block)
    int8[N]      density                 (127 = air, -128 = solid terrain)
    uint16[N]    damage
    bitstream    texture presence, then int64 per set bit  (6 paint ids, one per face)
    bitstream    water presence,   then uint16 per set bit
    int16        tile-entity count, then per entry: int16 payload_len, uint8 type, payload
    int16        trigger count,     then per entry: int16 payload_len, int32 x/y/z, payload

A bitstream is `int32 byte_count` followed by that many bytes, byte_count = ceil(N/8), bit i of
byte i//8 set when index i has a value. Values then follow in index order, one per set bit.

    index = x + y*size_x + z*size_x*size_y

Block ids are NOT the game's ids. They are per-prefab and arbitrary, resolved by NAME at load from
the sidecar `<name>.blocks.nim`, which is mandatory -- a missing one is a hard load failure. So we
assign our own dense ids and ship a name table, and the prefab stays portable across game versions
because only the names have to be right. Id 0 is always `air` and is skipped by the reader.

Only PARENT blocks are stored. The game calls RemoveAllChildAndOldBlocks() before saving and
AddAllChildBlocks() after loading, so emitting child blocks (bit 30) corrupts the prefab.
"""
import os
import struct

import numpy as np

MAGIC = b"tts\0"
VERSION = 19
DENSITY_AIR = 127          # sbyte.MaxValue, MarchingCubes.DensityAir
DENSITY_TERRAIN = -128     # MarchingCubes.DensityTerrain

# Paint ids from Data/Config/painting.xml. The lot palette the map uses: six concrete colours
# (there is no indigo concrete in the game) plus black granite for the compound "mega lots" that
# stand in for a mall or a base rather than a single building.
PAINT = {
    "red": 156, "orange": 155, "yellow": 152, "green": 160, "blue": 153, "purple": 159,
    "white": 151, "grey": 161, "dark_grey": 162, "black": 169,
    "concrete": 2, "gravel": 5,
}
ROYGBIV = ["red", "orange", "yellow", "green", "blue", "purple"]


def pack_block(type_id, rotation=0, meta=0, meta2=0, meta3=0):
    """BlockValueV3 rawData: type 0-14, rotation 15-19, meta 20-23, meta2 24-27, meta3 28-29.
    Bit 30 is ischild and bit 31 hasDecal; both stay clear -- the game regenerates child blocks."""
    if not 0 <= type_id <= 0x7FFF:
        raise ValueError(f"block type {type_id} out of range")
    if not 0 <= rotation <= 31:
        raise ValueError(f"rotation {rotation} out of range")
    return (type_id & 0x7FFF) | (rotation << 15) | (meta << 20) | (meta2 << 24) | (meta3 << 28)


def unpack_block(raw):
    return dict(type=raw & 0x7FFF, rotation=(raw >> 15) & 0x1F, meta=(raw >> 20) & 0xF,
                meta2=(raw >> 24) & 0xF, meta3=(raw >> 28) & 0x3,
                ischild=bool(raw >> 30 & 1), hasDecal=bool(raw >> 31 & 1))


def pack_faces(paint_id=None, faces=None):
    """The texture value is six paint ids, one per face, packed one byte each into an int64."""
    f = list(faces) if faces else [paint_id or 0] * 6
    if len(f) != 6:
        raise ValueError("faces must be 6 paint ids")
    v = 0
    for i, p in enumerate(f):
        if not 0 <= p <= 255:
            raise ValueError(f"paint id {p} out of range")
        v |= (p & 0xFF) << (8 * i)
    return v


class Reader:
    def __init__(self, data):
        self.d, self.o = data, 0

    def take(self, n):
        b = self.d[self.o:self.o + n]
        if len(b) != n:
            raise EOFError(f"wanted {n} bytes at {self.o}, got {len(b)}")
        self.o += n
        return b

    def u(self, fmt):
        return struct.unpack_from(fmt, self.d, self.o)[0], self.take(struct.calcsize(fmt))[0:0]

    def i16(self):
        v = struct.unpack_from("<h", self.d, self.o)[0]; self.o += 2; return v

    def u16(self):
        v = struct.unpack_from("<H", self.d, self.o)[0]; self.o += 2; return v

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4; return v

    def u8(self):
        v = self.d[self.o]; self.o += 1; return v

    def arr(self, dtype, n):
        dt = np.dtype(dtype)
        a = np.frombuffer(self.d, dt, n, self.o).copy()
        self.o += n * dt.itemsize
        return a

    def sparse(self, n, dtype):
        """bitstream + one value per set bit -> {index: value}."""
        nbytes = self.i32()
        bits = np.unpackbits(np.frombuffer(self.take(nbytes), np.uint8), bitorder="little")[:n]
        idx = np.flatnonzero(bits)
        vals = self.arr(dtype, len(idx))
        return dict(zip(idx.tolist(), vals.tolist())), nbytes


class Prefab:
    """One .tts. `blocks`, `density` and `damage` are flat arrays of length x*y*z."""

    def __init__(self, size, blocks=None, density=None, damage=None, textures=None, water=None,
                 tile_entities=None, triggers=None, version=VERSION, tex_bytes=None,
                 water_bytes=None):
        self.size = tuple(int(v) for v in size)
        n = self.count
        self.blocks = np.zeros(n, "<u4") if blocks is None else blocks
        self.density = np.full(n, DENSITY_AIR, "<i1") if density is None else density
        self.damage = np.zeros(n, "<u2") if damage is None else damage
        self.textures = textures or {}
        self.water = water or {}
        self.tile_entities = tile_entities or []
        self.triggers = triggers or []
        self.version = version
        # The writer emits ceil(N/8); shipped files sometimes pad, so a round-trip keeps the
        # original byte counts to stay byte-exact.
        self.tex_bytes = tex_bytes
        self.water_bytes = water_bytes

    @property
    def count(self):
        return self.size[0] * self.size[1] * self.size[2]

    def index(self, x, y, z):
        sx, sy, _ = self.size
        return x + y * sx + z * sx * sy

    def set(self, x, y, z, type_id, rotation=0, density=DENSITY_TERRAIN, paint=None, faces=None):
        i = self.index(x, y, z)
        self.blocks[i] = pack_block(type_id, rotation)
        self.density[i] = density
        if paint is not None or faces is not None:
            self.textures[i] = pack_faces(PAINT.get(paint, paint) if isinstance(paint, str) else paint,
                                          faces)
        return i

    def fill(self, type_id, y, paint=None):
        """Fill a whole horizontal layer -- the common case for a lot slab or a road deck."""
        sx, _, sz = self.size
        for z in range(sz):
            for x in range(sx):
                self.set(x, y, z, type_id, paint=paint)


def read(path):
    d = open(path, "rb").read()
    r = Reader(d)
    if r.take(4) != MAGIC:
        raise ValueError(f"{path}: not a .tts")
    ver = r.u32()
    size = (r.i16(), r.i16(), r.i16())
    n = size[0] * size[1] * size[2]
    blocks = r.arr("<u4", n)
    density = r.arr("<i1", n) if ver > 4 else None
    damage = r.arr("<u2", n) if ver > 8 else None
    textures, tex_bytes = r.sparse(n, "<i8") if ver >= 10 else ({}, None)
    water, water_bytes = r.sparse(n, "<u2") if ver >= 17 else ({}, None)
    tes = []
    if ver > 12:
        for _ in range(r.i16()):
            ln = r.i16(); tes.append((r.u8(), r.take(ln)))
    trg = []
    if ver > 15:
        for _ in range(r.i16()):
            ln = r.i16(); trg.append(((r.i32(), r.i32(), r.i32()), r.take(ln)))
    return Prefab(size, blocks, density, damage, textures, water, tes, trg, ver,
                  tex_bytes, water_bytes)


def _sparse_bytes(d, n, fmt, nbytes=None):
    nbytes = nbytes if nbytes is not None else (n + 7) // 8
    bits = np.zeros(nbytes * 8, np.uint8)
    for i in sorted(d):
        bits[i] = 1
    out = [struct.pack("<i", nbytes), np.packbits(bits, bitorder="little").tobytes()]
    out += [struct.pack(fmt, d[i]) for i in sorted(d)]
    return b"".join(out)


def write(path, p):
    """Mirrors the reader's version gates, so an older prefab round-trips byte-exact. We only ever
    AUTHOR version 19, where every section is present."""
    n, v = p.count, p.version
    parts = [MAGIC, struct.pack("<I", v), struct.pack("<hhh", *p.size),
             p.blocks.astype("<u4").tobytes()]
    if v > 4:
        parts.append(p.density.astype("<i1").tobytes())
    if v > 8:
        parts.append(p.damage.astype("<u2").tobytes())
    if v >= 10:
        parts.append(_sparse_bytes(p.textures, n, "<q", p.tex_bytes))
    if v >= 17:
        parts.append(_sparse_bytes(p.water, n, "<H", p.water_bytes))
    if v > 12:
        parts.append(struct.pack("<h", len(p.tile_entities)))
        for t, payload in p.tile_entities:
            parts += [struct.pack("<h", len(payload)), struct.pack("<B", t), payload]
    if v > 15:
        parts.append(struct.pack("<h", len(p.triggers)))
        for (x, y, z), payload in p.triggers:
            parts += [struct.pack("<h", len(payload)), struct.pack("<iii", x, y, z), payload]
    open(path, "wb").write(b"".join(parts))


# ---------------------------------------------------------------- .blocks.nim (mandatory sidecar)

def _write_7bit(n):
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80); n >>= 7
    out.append(n)
    return bytes(out)


def _read_7bit(r):
    n = shift = 0
    while True:
        b = r.u8()
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n
        shift += 7


def read_nim(path):
    """-> ([(id, name), ...], version). A list, not a dict: a handful of shipped tables repeat an
    id, and a dict would silently drop the duplicate and break a byte-exact round-trip."""
    r = Reader(open(path, "rb").read())
    ver = r.i32()
    return [(r.i32(), r.take(_read_7bit(r)).decode("utf-8")) for _ in range(r.i32())], ver


def nim_map(entries):
    return dict(entries)


def write_nim(path, mapping, version=1):
    """`mapping` is a dict (written in id order) or a list of (id, name) kept in the given order."""
    entries = sorted(mapping.items()) if isinstance(mapping, dict) else list(mapping)
    parts = [struct.pack("<i", version), struct.pack("<i", len(entries))]
    for i, name in entries:
        b = name.encode("utf-8")
        parts += [struct.pack("<i", i), _write_7bit(len(b)), b]
    open(path, "wb").write(b"".join(parts))


def save(dirpath, name, prefab, names, xml=None):
    """Write <name>.tts + <name>.blocks.nim, and <name>.xml when given. `names` maps our own
    block ids to game block names; id 0 must be 'air'."""
    if names.get(0) != "air":
        raise ValueError("block id 0 must map to 'air' -- the engine hardcodes it")
    os.makedirs(dirpath, exist_ok=True)
    base = os.path.join(dirpath, name)
    write(base + ".tts", prefab)
    write_nim(base + ".blocks.nim", names)
    if xml:
        open(base + ".xml", "w", encoding="utf-8").write(xml)
    return base


# The seven properties every single one of the 1105 shipped POI .xml files carries, besides
# PrefabSize and RotationToFaceNorth. Surveyed, not guessed.
_UNIVERSAL = [("CopyAirBlocks", "False"), ("ExcludeDistantPOIMesh", "False"),
              ("ExcludePOICulling", "False"), ("DistantPOIYOffset", "0"),
              ("DifficultyTier", "0"), ("ShowQuestClearCount", "0"), ("TraderArea", "False")]


def prefab_xml(size, y_offset=-1, tags="navonly", zoning="NavOnly", rotation_to_face_north=0,
               extra=()):
    """A prefab .xml carrying every property the shipped prefabs universally carry.

    y_offset defaults to -1, not 0. Placement is y = terrain + YOffset + 1, and NO shipped prefab
    uses a YOffset of 0 or above -- the range across all 1105 is -55..-1, most commonly -1. At 0 a
    one-block slab would sit a block clear of the ground; at -1 its single layer lands on it.

    'navonly' and 'NavOnly' are real tokens from the shipped set, not invented ones. Legal Tags
    include commercial, downtown, industrial, residential, rural, oldwest, wilderness, part,
    streettile, gateway; legal Zoning includes Commercial, Downtown, Industrial, Residential,
    NoZone, NavOnly.
    """
    rows = [f'  <property name="PrefabSize" value="{size[0]},{size[1]},{size[2]}" />',
            f'  <property name="YOffset" value="{y_offset}" />',
            f'  <property name="RotationToFaceNorth" value="{rotation_to_face_north}" />',
            f'  <property name="Tags" value="{tags}" />',
            f'  <property name="Zoning" value="{zoning}" />']
    rows += [f'  <property name="{k}" value="{v}" />' for k, v in _UNIVERSAL]
    rows += [f'  <property name="{k}" value="{v}" />' for k, v in extra]
    return '<?xml version="1.0" encoding="UTF-8"?>\n<prefab>\n' + "\n".join(rows) + "\n</prefab>\n"
