# web 各处应跟随真机上报的 panel(智能切屏): 设备拉 /frame?panel=bw_426 后,
# 预览/布局编辑/真机帧回退/状态全部按 4.2 寸 profile 走, 且持久化跨重启。
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config, load_runtime


def _cfg(tmp_path):
    return Config(claude_logs=str(tmp_path / "l"),
                  photos_dir=str(tmp_path / "p"),
                  todos_store=str(tmp_path / "todos.json"),
                  layouts_store=str(tmp_path / "layouts.json"),
                  runtime_store=str(tmp_path / "runtime.json"))


def test_default_panel_is_750_before_any_pull(tmp_path):
    c = TestClient(create_app(_cfg(tmp_path)))
    assert c.get("/api/layouts").json()["grid"] == {"cols": 8, "rows": 6}
    assert c.get("/api/device/status").json()["panel"] is None


def test_device_panel_drives_layout_grid(tmp_path):
    app = create_app(_cfg(tmp_path))
    c = TestClient(app)
    c.get("/frame", params={"panel": "bw_426"})
    # 布局编辑器网格应跟随真机 -> 4x8 竖版
    assert c.get("/api/layouts").json()["grid"] == {"cols": 4, "rows": 8}
    # 状态暴露当前 panel
    assert c.get("/api/device/status").json()["panel"] == "bw_426"
    assert app.state.cfg.active_panel == "bw_426"


def test_active_panel_persisted_to_runtime(tmp_path):
    cfg = _cfg(tmp_path)
    c = TestClient(create_app(cfg))
    c.get("/frame", params={"panel": "bw_426"})
    # 新进程重载 runtime.json -> 仍记得配对的 panel
    fresh = _cfg(tmp_path)
    load_runtime(fresh, fresh.runtime_store)
    assert fresh.active_panel == "bw_426"


def test_layout_save_lands_in_active_profile(tmp_path):
    c = TestClient(create_app(_cfg(tmp_path)))
    c.get("/frame", params={"panel": "bw_426"})
    # 在 4x8 网格内存一个自定义布局(列<=4, 行<=8)
    r = c.put("/api/layouts/mine",
              json={"placements": [{"widget": "todos", "col": 0, "row": 0,
                                    "colspan": 4, "rowspan": 8}]})
    assert r.status_code == 200, r.text
    assert "mine" in c.get("/api/layouts").json()["layouts"]


def test_layout_save_rejects_750_geometry_on_426(tmp_path):
    c = TestClient(create_app(_cfg(tmp_path)))
    c.get("/frame", params={"panel": "bw_426"})
    # 7.5 寸的 8 列摆放在 4 列竖屏上越界 -> 400
    r = c.put("/api/layouts/bad",
              json={"placements": [{"widget": "todos", "col": 0, "row": 0,
                                    "colspan": 8, "rowspan": 1}]})
    assert r.status_code == 400


def test_unknown_panel_falls_back_to_default(tmp_path):
    c = TestClient(create_app(_cfg(tmp_path)))
    c.get("/frame", params={"panel": "nope_999"})
    # 未知 panel: profile 回退默认, 网格回 8x6, 但仍记录原始上报值
    assert c.get("/api/layouts").json()["grid"] == {"cols": 8, "rows": 6}
