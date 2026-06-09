from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import Zone, draw_claude_status, draw_usage, draw_todos, draw_header
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _canvas():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    return img, ImageDraw.Draw(img)


def _nonwhite_count(img, zone):
    cnt = 0
    for y in range(zone.y, zone.y + zone.h):
        for x in range(zone.x, zone.x + zone.w):
            if img.getpixel((x, y)) != (255, 255, 255):
                cnt += 1
    return cnt


def test_status_draws_something():
    img, d = _canvas()
    z = Zone(0, 60, 480, 200)
    draw_claude_status(d, z, ClaudeStatus(state="working", project="InkPulse"))
    assert _nonwhite_count(img, z) > 0


def test_attention_state_uses_red():
    img, d = _canvas()
    z = Zone(0, 60, 480, 200)
    draw_claude_status(d, z, ClaudeStatus(state="error"))
    reds = sum(1 for p in img.getdata() if p == (255, 0, 0))
    assert reds > 0


def test_idle_state_no_red():
    img, d = _canvas()
    draw_claude_status(d, Zone(0, 60, 480, 200), ClaudeStatus(state="working"))
    assert all(p != (255, 0, 0) for p in img.getdata())


def test_usage_and_todos_and_header_draw():
    img, d = _canvas()
    draw_usage(d, Zone(480, 60, 320, 200), Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.5))
    draw_todos(d, Zone(0, 260, 800, 220), [TodoItem("a", "x", False), TodoItem("b", "y", True)])
    draw_header(d, Zone(0, 0, 800, 60), "6/9 周一 14:32", temp=22.0, humidity=55.0)
    assert _nonwhite_count(img, Zone(480, 60, 320, 200)) > 0
    assert _nonwhite_count(img, Zone(0, 260, 800, 220)) > 0
    assert _nonwhite_count(img, Zone(0, 0, 800, 60)) > 0
