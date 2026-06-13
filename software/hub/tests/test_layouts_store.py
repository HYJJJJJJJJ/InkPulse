import json
import pytest
from inkpulse_hub.render import layouts as L


def test_defaults_have_six_builtins_when_no_file():
    store = L.load_store("")          # 空路径 -> 内置默认
    assert store["grid"] == {"cols": 8, "rows": 6}
    assert {"dash", "photo", "usage", "todo", "clock", "split"} <= set(store["layouts"])
    for lay in store["layouts"].values():
        assert lay.get("builtin") is True
        assert isinstance(lay["placements"], list) and lay["placements"]


def test_get_layout_falls_back_to_dash_for_unknown(tmp_path):
    p = str(tmp_path / "layouts.json")
    lay = L.get_layout(p, "no-such-layout")
    assert lay["grid"]["cols"] == 8
    assert lay["placements"] == L.get_layout(p, "dash")["placements"]


def test_save_then_get_roundtrip(tmp_path):
    p = str(tmp_path / "layouts.json")
    placements = [{"widget": "qrcode", "col": 0, "row": 0,
                   "colspan": 2, "rowspan": 3, "params": {"content": "hi"}}]
    L.save_layout(p, "我的", placements)
    got = L.get_layout(p, "我的")
    assert got["placements"][0]["widget"] == "qrcode"
    assert got["placements"][0]["params"]["content"] == "hi"
    # builtin 仍在(文件与内置合并)
    assert "dash" in L.load_store(p)["layouts"]


def test_save_does_not_persist_all_builtins(tmp_path):
    p = str(tmp_path / "layouts.json")
    L.save_layout(p, "我的", [{"widget": "todos", "col": 0, "row": 0,
                              "colspan": 8, "rowspan": 6, "params": {}}])
    raw = json.loads(open(p, encoding="utf-8").read())
    assert set(raw["layouts"]) == {"我的"}     # 文件只存用户布局, 不灌入 6 个内置


def test_delete_user_layout(tmp_path):
    p = str(tmp_path / "layouts.json")
    L.save_layout(p, "我的", [{"widget": "todos", "col": 0, "row": 0,
                              "colspan": 8, "rowspan": 6, "params": {}}])
    L.delete_layout(p, "我的")
    assert "我的" not in L.load_store(p)["layouts"]


def test_delete_builtin_rejected(tmp_path):
    p = str(tmp_path / "layouts.json")
    with pytest.raises(ValueError):
        L.delete_layout(p, "dash")


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "layouts.json"
    p.write_text("{ not json", encoding="utf-8")
    assert "dash" in L.load_store(str(p))["layouts"]


def test_clamp_out_of_grid_placement(tmp_path):
    p = str(tmp_path / "layouts.json")
    L.save_layout(p, "越界", [{"widget": "todos", "col": 6, "row": 0,
                              "colspan": 9, "rowspan": 1, "params": {}}])
    z = L.get_layout(p, "越界")["placements"][0]
    assert z["col"] + z["colspan"] <= 8       # 被 clamp 进网格
