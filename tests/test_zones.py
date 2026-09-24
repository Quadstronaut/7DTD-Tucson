import numpy as np, pytest
from tucson import zones
from tucson.config import load
from tucson.warp import Warp

CFG = load(); W = Warp(CFG)

def test_rect_zone_mask_is_filled_box():
    rings = zones.rect_rings([32.2045, -110.8245, 32.2082, -110.8200])
    m = zones.mask(rings, W, 10240)
    assert m.sum() > 0
    ys, xs = np.nonzero(m)
    assert xs.min() == pytest.approx(W.x(-110.8245), abs=2)
    assert ys.min() == pytest.approx(W.z(32.2082), abs=2)      # north edge = smallest row

def test_overpass_retries_then_raises(monkeypatch):
    calls = []
    def boom(*a, **k):
        calls.append(1); raise zones.urllib.error.HTTPError("u", 504, "timeout", None, None)
    monkeypatch.setattr(zones.urllib.request, "urlopen", boom)
    monkeypatch.setattr(zones.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        zones.overpass("node(1);out;")
    assert len(calls) == zones.RETRIES

def test_empty_osm_result_is_error(monkeypatch):
    monkeypatch.setattr(zones, "overpass", lambda q: {"elements": []})
    with pytest.raises(RuntimeError, match="no polygon"):
        zones.fetch_rings("x", 'way["name"="nope"]', cache_dir=None)


def test_stitch_joins_open_segments_into_closed_ring():
    a = [(0, 0), (0, 1)]; b = [(1, 1), (0, 1)]            # b reversed relative to a
    c = [(1, 1), (1, 0)]; d = [(1, 0), (0, 0)]
    rings = zones.stitch([a, c, b, d])
    assert len(rings) == 1
    r = rings[0]
    assert r[0] == r[-1] and len(set(r)) == 4

def test_stitch_keeps_closed_rings():
    sq = [(0, 0), (0, 1), (1, 1), (0, 0)]
    assert zones.stitch([sq]) == [sq]
