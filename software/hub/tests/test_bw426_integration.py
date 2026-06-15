from inkpulse_hub.render.engine import render_frame
from inkpulse_hub.render import layouts as L
from inkpulse_hub.render.profiles import PROFILES
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0, "rssi": -55},
        "clock": "2026-06-15 14:32 周一",
        "lunar": {"text": "农历五月初一", "festival": ""},
        "now": 1718000000.0,
    }


def test_all_bw426_layouts_render_48000_and_no_red():
    import io
    from PIL import Image
    names = {"dash", "photo", "clock", "usage", "split", "todo"}
    assert names <= set(L.load_store("", "bw_426")["layouts"])
    for name in names:
        cfg = Config(); cfg.layouts_store = ""; cfg.layout_name = name
        f = render_frame(cfg, _state(), PROFILES["bw_426"])
        assert len(f.body) == 48000, f"{name} 帧大小错"
        im = Image.open(io.BytesIO(f.png_bytes)).convert("RGB")
        assert all(px != (255, 0, 0) for px in im.getdata()), f"{name} BW 下不应有红"
