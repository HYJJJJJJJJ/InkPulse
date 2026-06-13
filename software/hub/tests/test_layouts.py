from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import (
    draw_big_clock, draw_usage_ring, draw_month_calendar, Zone,
)
from inkpulse_hub.models import Usage


def _img(w, h):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def test_big_clock_draws_time():
    img, d = _img(480, 200)
    draw_big_clock(d, Zone(0, 0, 480, 200), 1718000000.0)
    black = sum(1 for x in range(480) for y in range(200)
                if img.getpixel((x, y)) == (0, 0, 0))
    assert black > 200   # 巨型时钟应画出不少黑像素


def test_usage_ring_red_when_high():
    img, d = _img(200, 200)
    draw_usage_ring(d, Zone(0, 0, 200, 200), Usage(window_used_ratio=0.95))
    red = any(img.getpixel((x, y)) == (255, 0, 0)
              for x in range(200) for y in range(200))
    assert red   # 高占用(>=0.9)环标红


def test_usage_ring_no_crash_when_empty():
    img, d = _img(200, 200)
    draw_usage_ring(d, Zone(0, 0, 200, 200), Usage())   # ratio 可能 None
    # 不抛异常即可


def test_month_calendar_renders():
    img, d = _img(400, 260)
    draw_month_calendar(d, Zone(0, 0, 400, 260), 1718000000.0)
    black = sum(1 for x in range(400) for y in range(260)
                if img.getpixel((x, y)) == (0, 0, 0))
    assert black > 100   # 月历网格 + 数字


def test_all_builtin_layouts_render_full_frame():
    from inkpulse_hub.render.engine import render_frame
    from inkpulse_hub.render import layouts as L
    from inkpulse_hub.config import Config
    from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem
    expected = {"dash", "photo", "usage", "todo", "clock", "split"}
    assert expected <= set(L.load_store("")["layouts"])
    state = {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0, "rssi": -55},
        "clock": "2026-06-13 14:32 周五",
        "lunar": {"text": "农历四月廿七", "festival": ""},
        "now": 1718000000.0,
    }
    for name in expected:
        cfg = Config()
        cfg.layouts_store = ""
        cfg.layout_name = name
        f = render_frame(cfg, state)
        assert len(f.body) == 96000, f"{name} 帧大小错"
