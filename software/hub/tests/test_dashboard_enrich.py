import io
import datetime
from PIL import Image
from inkpulse_hub.state import HubState, lunar_info
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem
from inkpulse_hub.render.engine import render_frame


def _ts(y, mo, d, h=11, mi=23):
    return datetime.datetime(y, mo, d, h, mi).timestamp()


def test_clock_full_format():
    s = HubState(Config())
    assert s._clock(_ts(2026, 6, 12)) == "2026-06-12 11:23 周五"


def test_lunar_normal_day():
    info = lunar_info(_ts(2026, 6, 12))
    assert info["text"].startswith("农历四月")        # 农历日期
    assert "丙午马年" in info["text"]                  # 生肖年
    assert info["festival"] == ""                      # 非节日


def test_lunar_festival_detected():
    info = lunar_info(_ts(2026, 6, 19, 9, 0))           # 端午
    assert info["festival"] == "端午节"


def _dashboard_state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse", since=_ts(2026, 6, 12) - 720),
        "usage": Usage(input_tokens=2_000_000, output_tokens=400_000, cost_usd=699.0,
                       session_count=13, window_used_ratio=0.86),
        "todos": [TodoItem("a", "调通驱动", True), TodoItem("b", "换湿度传感器", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0},
        "clock": "2026-06-12 11:23 周五",
        "lunar": {"text": "农历四月廿七 · 丙午马年", "festival": ""},
        "now": _ts(2026, 6, 12),
    }


def test_frame_only_three_colors_and_96000_bytes():
    cfg = Config()   # 默认仪表盘布局
    frame = render_frame(cfg, _dashboard_state())
    assert len(frame.body) == 96000                    # 双 plane 帧大小不变
    img = Image.open(io.BytesIO(frame.png_bytes)).convert("RGB")
    colors = set(img.getdata())
    assert colors <= {(255, 255, 255), (0, 0, 0), (255, 0, 0)}   # 仅黑/白/红
