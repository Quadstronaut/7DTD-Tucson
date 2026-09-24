from tucson import postedit

def _roundtrip(tmp_path, body):
    p = tmp_path / "prefabs.xml"; p.write_text(body, encoding="utf-8")
    postedit.add_decorations(str(tmp_path), [("a", 1, 2, 3, 0)])
    return p.read_text(encoding="utf-8")

def test_self_closing_empty_prefabs(tmp_path):
    out = _roundtrip(tmp_path, '<?xml version="1.0" encoding="UTF-8"?>\n<prefabs />')
    assert 'name="a" position="1,2,3"' in out and out.strip().endswith("</prefabs>")

def test_existing_prefabs(tmp_path):
    out = _roundtrip(tmp_path, '<prefabs>\n  <decoration type="model" name="b" position="0,0,0" rotation="0" />\n</prefabs>')
    assert out.count("<decoration") == 2
