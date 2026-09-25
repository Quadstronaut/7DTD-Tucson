"""End-to-end: assemble.build on a tiny world must write every landmark into prefabs.xml.
Guards the regression where the build silently wrote an empty <prefabs>."""
import numpy as np, os
from tucson import assemble, landmarks, roads, terrain, zones


def test_build_writes_landmarks(tmp_path, monkeypatch):
    N = 256
    shell = tmp_path / "shell"; shell.mkdir()
    for f in assemble.SHELL_FILES:
        (shell / f).write_bytes(b"x")
    cfg = assemble.load()
    small = {**cfg, "size": N, "warp": {k: [[a, b * N / cfg["size"]] for a, b in v] for k, v in cfg["warp"].items()}}
    monkeypatch.setattr(assemble, "load", lambda: small)
    monkeypatch.setattr(assemble, "GW", str(tmp_path))
    monkeypatch.setattr(terrain, "elevation_grid", lambda warp, n: np.full((n, n), 800, np.float32))
    monkeypatch.setattr(zones, "polygons", lambda cfg: {})
    ways = [{"id": 1, "cls": "motorway", "bridge": False, "pts": [(32.2, -111.1), (32.2, -110.7)]}]
    monkeypatch.setattr(roads, "fetch_ways", lambda cfg: ways)
    monkeypatch.setattr(roads, "fetch_extra", lambda cfg: [])
    places = [{"id": "a", "prefab": "p", "at": [32.3, -110.9]}, {"id": "b", "prefab": "p", "at": [32.15, -111.0]}]
    monkeypatch.setattr(landmarks, "load", lambda: places)
    monkeypatch.setattr(landmarks, "prefab_meta", lambda n: (10, 10, 10, -1))
    monkeypatch.setattr(landmarks, "resolve", lambda e: {p["id"]: p["at"] for p in e})
    monkeypatch.setattr(assemble, "spawn_along_motorway", lambda w, b, n=12, margin=400: [(0, 40.0, 0, 90)])
    assemble.build(str(shell), "T")
    s = open(os.path.join(tmp_path, "T", "prefabs.xml"), encoding="utf-8").read()
    assert s.count("<decoration") == 2
