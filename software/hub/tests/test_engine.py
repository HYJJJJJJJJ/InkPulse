from inkpulse_hub.render.engine import render_frame, Frame
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


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
    f = render_frame(Config(), _state())
    assert isinstance(f, Frame)
    assert len(f.body) == 96000
    assert f.etag.startswith('"')
    assert f.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_same_input_same_etag():
    a = render_frame(Config(), _state())
    b = render_frame(Config(), _state())
    assert a.etag == b.etag


def test_missing_data_falls_back_not_crash():
    state = _state()
    state["usage"] = Usage()          # 空用量
    state["env"] = {"temp": None, "humidity": None}
    f = render_frame(Config(), state)  # 不应抛异常
    assert len(f.body) == 96000
