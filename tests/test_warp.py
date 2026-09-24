import numpy as np, pytest
from tucson.config import load
from tucson.warp import Warp

CFG = load()
W = Warp(CFG)
B = CFG["box"]

def test_edges_hit_bounds():
    assert W.x(B["west"]) == pytest.approx(0, abs=1e-6)
    assert W.x(B["east"]) == pytest.approx(10240, abs=1e-3)
    assert W.z(B["north"]) == pytest.approx(0, abs=1e-3)      # row 0 = north
    assert W.z(B["south"]) == pytest.approx(10240, abs=1e-6)

def test_monotonic():
    lons = np.linspace(B["west"], B["east"], 1000)
    lats = np.linspace(B["south"], B["north"], 1000)
    assert np.all(np.diff(W.x(lons)) > 0)
    assert np.all(np.diff(W.z(lats)) < 0)                     # north-up: higher lat -> smaller row

def test_clamps_outside_box():
    assert W.x(B["west"] - 1) == 0 and W.x(B["east"] + 1) == 10240
    assert W.z(B["north"] + 1) == 0 and W.z(B["south"] - 1) == 10240

def test_inverse_roundtrip():
    lon, lat = -110.9565, 32.2289                              # UA
    assert W.lon(W.x(lon)) == pytest.approx(lon, abs=1e-6)
    assert W.lat(W.z(lat)) == pytest.approx(lat, abs=1e-6)

def test_landmarks_ordering():
    # Old Tucson west of downtown west of DM west of Lemmon; Lemmon north of everything.
    assert W.x(-111.1286) < W.x(-110.9748) < W.x(-110.8819) < W.x(-110.7890)
    assert W.z(32.4424) < W.z(32.2289) < W.z(32.1662) < W.z(32.1147)

def test_bad_control_points_rejected():
    bad = {**CFG, "warp": {"x": [[0, 0], [5, 100], [4, 200], [39.53, 10240]], "z": CFG["warp"]["z"]}}
    with pytest.raises(ValueError):
        Warp(bad)
