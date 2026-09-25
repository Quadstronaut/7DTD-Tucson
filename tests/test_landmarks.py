import numpy as np
from tucson import landmarks


def test_footprint_min_corner_world_coords():
    N = 1000
    # 10x6 prefab centered at image col 500, row 500 (world x 0, z = 1000-1-500-500 = -1)
    r0, r1, c0, c1, wx, wz = landmarks.footprint(500, 500, 10, 6, N)
    assert (c1 - c0, r1 - r0) == (10, 6)
    assert wx == c0 - 500
    # southern edge row r1-1 has world z = N-1-(r1-1) - N/2 == wz
    assert wz == (N - 1 - (r1 - 1)) - N // 2


def test_pad_is_flat_integer_and_feathered():
    blk = np.tile(np.linspace(40, 80, 200, dtype=np.float32), (200, 1))
    h = landmarks.flatten_pad(blk, 90, 110, 90, 110)
    assert h == int(h)
    assert np.ptp(blk[90:110, 90:110]) == 0 and blk[100, 100] == h
    assert np.abs(np.diff(blk[100, 60:140])).max() < 5          # no cliff at the pad edge
    assert blk[100, 0] == np.float32(40)                        # far terrain untouched


def test_place_emits_rotated_min_corner_and_y(monkeypatch):
    monkeypatch.setattr(landmarks, "prefab_meta", lambda n: (10, 20, 4, -3))
    class W:
        def x(self, lon): return 500.0
        def z(self, lat): return 500.0
    blk = np.full((1000, 1000), 50.0, np.float32)
    decs, warns = landmarks.place([{"id": "a", "prefab": "p", "rot": 1}], {"a": [0, 0]}, W(), blk)
    name, x, y, z, rot = decs[0]
    assert (name, rot, y) == ("p", 1, 50 - 3 + 1)
    assert x == 500 - 4 // 2 - 500                               # rot 1 swaps: width is now 4
    assert not warns


def test_too_tall_warns(monkeypatch):
    monkeypatch.setattr(landmarks, "prefab_meta", lambda n: (10, 60, 10, -1))
    class W:
        def x(self, lon): return 500.0
        def z(self, lat): return 500.0
    blk = np.full((1000, 1000), 230.0, np.float32)
    _, warns = landmarks.place([{"id": "t", "prefab": "p"}], {"t": [0, 0]}, W(), blk)
    assert any("top" in w for w in warns)
