from fastapi.testclient import TestClient
from inkpulse_hub.config import Config
from inkpulse_hub.server import create_app


def _client(tmp_path):
    cfg = Config()
    cfg.runtime_store = str(tmp_path / "runtime.json")
    cfg.layouts_store = str(tmp_path / "layouts.json")
    cfg.photos_dir = str(tmp_path / "photos")
    return cfg, TestClient(create_app(cfg))


def test_get_layouts_returns_grid_builtins_and_widget_catalog(tmp_path):
    cfg, c = _client(tmp_path)
    body = c.get("/api/layouts").json()
    assert body["grid"] == {"cols": 8, "rows": 6}
    assert "dash" in body["layouts"]
    names = {w["name"] for w in body["widgets"]}
    assert {"header", "countdown", "qrcode"} <= names
    cd = next(w for w in body["widgets"] if w["name"] == "countdown")
    assert cd["default_span"]["cols"] >= 1 and isinstance(cd["params"], list)


def test_put_creates_user_layout(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/我的", json={"placements": [
        {"widget": "qrcode", "col": 0, "row": 0, "colspan": 2, "rowspan": 3,
         "params": {"content": "hi"}}]})
    assert r.status_code == 200
    assert "我的" in c.get("/api/layouts").json()["layouts"]


def test_put_rejects_unknown_widget(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/x", json={"placements": [
        {"widget": "nope", "col": 0, "row": 0, "colspan": 1, "rowspan": 1}]})
    assert r.status_code == 400


def test_put_rejects_out_of_grid(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/x", json={"placements": [
        {"widget": "todos", "col": 6, "row": 0, "colspan": 9, "rowspan": 1}]})
    assert r.status_code == 400


def test_delete_user_ok_builtin_rejected(tmp_path):
    cfg, c = _client(tmp_path)
    c.put("/api/layouts/我的", json={"placements": [
        {"widget": "todos", "col": 0, "row": 0, "colspan": 8, "rowspan": 6}]})
    assert c.delete("/api/layouts/我的").status_code == 200
    assert c.delete("/api/layouts/dash").status_code == 400   # 内置不可删


def test_put_rejects_overwriting_builtin(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/dash", json={"placements": [
        {"widget": "todos", "col": 0, "row": 0, "colspan": 8, "rowspan": 6}]})
    assert r.status_code == 400


def test_catalog_exposes_phase2_widgets_with_select(tmp_path):
    cfg, c = _client(tmp_path)
    widgets = {w["name"]: w for w in c.get("/api/layouts").json()["widgets"]}
    assert {"usage_trend", "project_dist"} <= set(widgets)
    metric = next(p for p in widgets["usage_trend"]["params"] if p["key"] == "metric")
    assert metric["type"] == "select"
    assert {"tokens", "cost"} <= {o["value"] for o in metric["options"]}
