import numpy as np, os, pytest
from PIL import Image
from tucson import assemble

def test_copy_shell_refuses_loaded(tmp_path):
    src = tmp_path / "s"; src.mkdir()
    for f in assemble.SHELL_FILES: (src / f).write_bytes(b"x")
    (src / "dtm_processed.raw").write_bytes(b"x")
    with pytest.raises(RuntimeError):
        assemble.copy_shell(str(src), str(tmp_path / "d"))
    assemble.copy_shell(str(src), str(tmp_path / "d"), allow_loaded=True)
    assert sorted(os.listdir(tmp_path / "d")) == sorted(assemble.SHELL_FILES)

def test_dtm_is_south_origin(tmp_path):
    blk = np.zeros((4, 4), np.float32); blk[0, :] = 100          # row 0 = north in our grids
    p = tmp_path / "dtm.raw"; assemble.write_dtm(str(p), blk)
    d = np.fromfile(p, "<u2").reshape(4, 4)
    assert (d[-1] == 25600).all() and (d[0] == 0).all()           # north lands in the LAST dtm row

def test_splat3_values(tmp_path):
    ch = np.array([[0, 1], [2, 0]], np.uint8); p = tmp_path / "s.png"
    assemble.write_splat3(str(p), ch)
    a = np.asarray(Image.open(p))
    assert a[0, 1].tolist() == [255, 0, 0, 255] and a[1, 0].tolist() == [0, 255, 0, 255] and a[0, 0].tolist() == [0, 0, 0, 0]


def test_spawns_keep_off_edge():
    blk = np.zeros((2000, 2000), np.float32)
    ways = [{"cls": "motorway", "xy": np.array([[5.0, 1000.0], [1995.0, 1000.0]])}]
    pts = assemble.spawn_along_motorway(ways, blk, n=5, margin=400)
    xs = [p[0] + 1000 for p in pts]
    assert min(xs) >= 400 and max(xs) < 1600
