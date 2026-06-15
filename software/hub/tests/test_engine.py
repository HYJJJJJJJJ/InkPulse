from inkpulse_hub.render.engine import render_frame, Frame
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _cfg():
    c = Config()
    c.layouts_store = ""      # 用内置布局, 不读用户真实文件, 保证确定性
    return c


def _state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0},
        "clock": "6/9 14:32",
    }


def test_render_produces_full_frame():
    f = render_frame(_cfg(), _state())
    assert isinstance(f, Frame)
    assert len(f.body) == 96000
    assert f.etag.startswith('"')
    assert f.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_same_input_same_etag():
    a = render_frame(_cfg(), _state())
    b = render_frame(_cfg(), _state())
    assert a.etag == b.etag


def test_missing_data_falls_back_not_crash():
    state = _state()
    state["usage"] = Usage()          # 空用量
    state["env"] = {"temp": None, "humidity": None}
    f = render_frame(_cfg(), state)  # 不应抛异常
    assert len(f.body) == 96000


def test_widget_exception_isolated(monkeypatch, tmp_path):
    from inkpulse_hub.render import engine, registry, layouts as L
    from inkpulse_hub.render.registry import WidgetSpec

    def boom(d, img, z, state, cfg, p):
        raise RuntimeError("boom")

    monkeypatch.setitem(registry.REGISTRY, "boom", WidgetSpec("boom", "炸", boom, {"cols": 1, "rows": 1}))
    lp = str(tmp_path / "layouts.json")
    L.save_layout(lp, "炸测", [{"widget": "boom", "col": 0, "row": 0,
                              "colspan": 8, "rowspan": 6, "params": {}}])
    cfg = _cfg()
    cfg.layouts_store = lp
    cfg.layout_name = "炸测"
    f = engine.render_frame(cfg, _state())
    assert len(f.body) == 96000        # 整帧仍出图, 不崩


from inkpulse_hub.render.profiles import PROFILES


def test_render_bw_426_produces_48000():
    f = render_frame(_cfg(), _state(), PROFILES["bw_426"])
    assert len(f.body) == 48000
    assert f.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_default_profile_unchanged():
    # 不传 profile = bwr_750 = 96000(零回归)
    assert len(render_frame(_cfg(), _state()).body) == 96000
