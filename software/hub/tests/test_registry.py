from PIL import Image, ImageDraw
from inkpulse_hub.render.registry import REGISTRY, WidgetSpec
from inkpulse_hub.render.widgets import Zone
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0, "rssi": -55},
        "clock": "2026-06-13 14:32 周五",
        "lunar": {"text": "农历四月廿七", "festival": ""},
        "now": 1718000000.0,
        "usage_daily": [{"date": __import__("datetime").date(2026, 6, 13), "tokens": 100, "cost": 0.1}],
        "usage_projects": [{"project": "InkPulse", "tokens": 100, "cost": 0.1}],
    }


def _img():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def test_existing_widgets_registered():
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist"}
    assert expected <= set(REGISTRY)
    for name in expected:
        assert isinstance(REGISTRY[name], WidgetSpec)
        assert REGISTRY[name].default_span["cols"] >= 1


def test_each_widget_draws_without_error():
    img, d = _img()
    z = Zone(0, 0, 400, 240)
    for name, spec in REGISTRY.items():
        spec.draw(d, img, z, _state(), Config(), {})   # 不应抛异常


def test_phase2_widgets_have_select_metric_param():
    for name in ("usage_trend", "project_dist"):
        params = REGISTRY[name].params
        metric = next(p for p in params if p["key"] == "metric")
        assert metric["type"] == "select"
        assert {"tokens", "cost"} <= {o["value"] for o in metric["options"]}


def test_header_widget_paints_pixels():
    img, d = _img()
    REGISTRY["header"].draw(d, img, Zone(0, 0, 800, 80), _state(), Config(), {})
    black = sum(1 for x in range(800) for y in range(80)
                if img.getpixel((x, y)) == (0, 0, 0))
    assert black > 50
