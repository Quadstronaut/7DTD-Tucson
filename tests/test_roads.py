import numpy as np
from scipy import ndimage
from tucson import roads
from tucson.config import load
from tucson.warp import Warp

CFG = load(); W = Warp(CFG)

def test_classes_match_config():
    assert set(roads.classes(CFG)) >= {"motorway", "primary", "secondary"}

def test_to_world_clips_outside_box():
    ways = [{"id": 1, "cls": "primary", "bridge": False,
             "pts": [(32.2, -111.5), (32.2, -110.9)]}]            # starts far west of box
    out = roads.to_world(ways, W)
    xy = out[0]["xy"]
    assert xy[:, 0].min() >= 0 and xy[:, 0].max() < W.N
    assert len(xy) >= 2


def _flat_ways(blk_shape, rows, cls="motorway"):
    return [{"id": i, "cls": cls, "bridge": False,
             "xy": np.array([[10.0, r], [blk_shape[1] - 10.0, r]])} for i, r in enumerate(rows)]

def test_parallel_carriageways_flat_across():
    blk = np.tile(np.linspace(40, 60, 300, dtype=np.float32)[:, None], (1, 300))   # slope N->S
    out, mask, ch = roads.grade(blk, _flat_ways(blk.shape, [140, 152]), CFG)
    across = out[135:158, 150]
    assert mask[140, 150] and mask[152, 150] and (ch[mask] == 1).all()
    assert np.ptp(across[mask[135:158, 150]]) < 2.5                             # no ridge between them

def test_no_cliffs_on_road():
    rng = np.random.default_rng(0)
    blk = ndimage.gaussian_filter(rng.normal(60, 15, (400, 400)), 20).astype(np.float32)
    ways = [{"id": 1, "cls": "primary", "bridge": False, "xy": np.array([[20, 200.], [380, 200.]])},
            {"id": 2, "cls": "secondary", "bridge": False, "xy": np.array([[200, 20.], [200, 380.]])}]
    out, mask, _ = roads.grade(blk, ways, CFG)
    dx = np.abs(np.diff(out, axis=1))[mask[:, 1:] & mask[:, :-1]]
    dy = np.abs(np.diff(out, axis=0))[mask[1:, :] & mask[:-1, :]]
    assert max(dx.max(), dy.max()) <= 2.0

def test_flat_zone_stays_flat():
    blk = np.full((300, 300), 50.0, np.float32)
    out, mask, _ = roads.grade(blk, _flat_ways(blk.shape, [150], "primary"), CFG)
    assert np.abs(out - 50).max() < 1e-3
