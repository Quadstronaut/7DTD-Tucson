import numpy as np
from tucson import terrain
from tucson.config import load

CFG = load()

def test_flatten_inside_constant_and_edge_blends():
    ele = np.tile(np.linspace(700, 800, 200, dtype=np.float32), (200, 1))   # ramp W->E
    m = np.zeros((200, 200), bool); m[60:140, 60:140] = True
    out = terrain.flatten(ele, m, feather=20)
    inside = out[m]
    assert np.ptp(inside) < 1e-3                                  # flat
    assert abs(inside[0] - np.median(ele[m])) < 1e-3
    step = np.abs(np.diff(out, axis=1)).max()
    assert step < 5 * np.abs(np.diff(ele, axis=1)).max() + 1e-3   # no cliff at the edge
    assert np.allclose(out[:, :30], ele[:, :30])                  # far away untouched

def test_to_blocks_curve_and_clamp():
    b = terrain.to_blocks(np.array([0, 650, 1000, 2800, 9000], np.float32), CFG)
    assert b.tolist() == [35.0, 35.0, 48.0, 235.0, 235.0]

def test_mountains_get_most_of_the_range():
    b = terrain.to_blocks(np.array([650, 1000, 2791], np.float32), CFG)     # valley, basin edge, Lemmon
    assert (b[2] - b[1]) > 8 * (b[1] - b[0])

def test_bad_curve_rejected():
    import pytest
    with pytest.raises(ValueError):
        terrain.to_blocks(np.array([700.0]), {**CFG, "height": {"curve": [[650, 35], [600, 40]]}})


def test_biome_colors():
    rgb = terrain.biome_rgb(np.array([[800, 1800, 2700]], np.float32), CFG)
    assert rgb[0].tolist() == [[255, 228, 119], [0, 64, 0], [255, 255, 255]]

def test_small_build_north_up(tmp_path):
    out = terrain.build(size=512, out_dir=str(tmp_path), zones_on=False)
    r, c = np.unravel_index(np.argmax(out), out.shape)
    assert r < 512 * 0.25 and c > 512 * 0.6                       # Lemmon: top-right
