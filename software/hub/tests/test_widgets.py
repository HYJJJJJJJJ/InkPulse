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


_LUNAR = {"text": "农历四月廿七 · 丙午马年", "festival": ""}


def test_usage_and_todos_and_header_draw():
    img, d = _canvas()
    draw_usage(d, Zone(480, 76, 320, 192), Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.5))
    draw_todos(d, Zone(0, 268, 800, 212), [TodoItem("a", "x", False), TodoItem("b", "y", True)])
    draw_header(d, Zone(0, 0, 800, 76), "2026-06-12 11:23 周五", _LUNAR, temp=22.0, humidity=55.0)
    assert _nonwhite_count(img, Zone(480, 76, 320, 192)) > 0
    assert _nonwhite_count(img, Zone(0, 268, 800, 212)) > 0
    assert _nonwhite_count(img, Zone(0, 0, 800, 76)) > 0


def _has_red(img):
    return any(p == (255, 0, 0) for p in img.getdata())


def test_header_date_is_red_lunar_black():
    # 哲学B: 日期始终红强调; 普通农历无红
    img, d = _canvas()
    draw_header(d, Zone(0, 0, 800, 76), "2026-06-12 11:23 周五", _LUNAR, 22.0, 55.0)
    assert _has_red(img)   # 日期红


def test_header_festival_red():
    img, d = _canvas()
    draw_header(d, Zone(0, 0, 800, 76), "2026-06-19 09:00 周五",
                {"text": "农历五月初五 · 丙午马年", "festival": "端午节"}, 22.0, 55.0)
    assert _has_red(img)   # 日期 + 节日都红


def test_usage_hero_red_only_when_over_budget():
    # 未配预算 → 花费黑(仅看 usage 区有无红, 窗口 0.5 不触发红)
    img, d = _canvas()
    draw_usage(d, Zone(480, 76, 320, 192), Usage(cost_usd=699.0, window_used_ratio=0.5), budget_usd=None)
    assert not _has_red(img)
    # 配预算且超 → 花费红
    img2, d2 = _canvas()
    draw_usage(d2, Zone(480, 76, 320, 192), Usage(cost_usd=699.0, window_used_ratio=0.5), budget_usd=100.0)
    assert _has_red(img2)


def test_usage_window_over_90_percent_red():
    img, d = _canvas()
    draw_usage(d, Zone(480, 76, 320, 192), Usage(cost_usd=1.0, window_used_ratio=0.95), budget_usd=None)
    assert _has_red(img)   # 95% 百分比红
    img2, d2 = _canvas()
    draw_usage(d2, Zone(480, 76, 320, 192), Usage(cost_usd=1.0, window_used_ratio=0.50), budget_usd=None)
    assert not _has_red(img2)   # 50% 不红


def test_status_shows_elapsed():
    img, d = _canvas()
    import time
    now = 1000_000.0
    s = ClaudeStatus(state="working", project="InkPulse", since=now - 12 * 60)  # 12 分钟前
    draw_claude_status(d, Zone(0, 76, 480, 192), s, now=now)
    assert _nonwhite_count(img, Zone(0, 76, 480, 192)) > 0   # 含 "已 12 分钟"
