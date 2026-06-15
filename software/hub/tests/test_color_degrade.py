from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_month_calendar, accent_for, Zone, RED, BLACK
from inkpulse_hub.render.dither import dither_mono


def _img(w, h):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img); d.fontmode = "1"
    return img, d


def test_accent_for_bw_is_black():
    assert accent_for({"color": "bw"}) == BLACK
    assert accent_for({"color": "bwr"}) == RED
    assert accent_for({}) == RED          # 缺省=彩色


def test_calendar_bw_has_no_red_pixel():
    img, d = _img(400, 260)
    draw_month_calendar(d, Zone(0, 0, 400, 260), 1718000000.0, accent=BLACK)
    red = any(img.getpixel((x, y)) == (255, 0, 0)
              for x in range(400) for y in range(260))
    assert not red                         # BW 下不得出现红像素


def test_calendar_bwr_keeps_red_today():
    img, d = _img(400, 260)
    draw_month_calendar(d, Zone(0, 0, 400, 260), 1718000000.0, accent=RED)
    red = any(img.getpixel((x, y)) == (255, 0, 0)
              for x in range(400) for y in range(260))
    assert red                             # 彩色下今天仍标红


def test_dither_mono_only_bw():
    src = Image.new("RGB", (40, 40), (200, 30, 30))   # 红
    out = dither_mono(src, (40, 40))
    colors = {out.getpixel((x, y)) for x in range(40) for y in range(40)}
    assert colors <= {(0, 0, 0), (255, 255, 255)}      # 只有黑白


def test_header_bw_has_no_red_pixel():
    from inkpulse_hub.render.widgets import draw_header
    img, d = _img(800, 60)
    # 周日 + 含节日, 彩色下本会标红
    draw_header(d, Zone(0, 0, 800, 60), "2026-01-01 00:00 周四",
                {"text": "元旦", "festival": "元旦"},
                22.0, 55.0, -55, accent=BLACK)
    red = any(img.getpixel((x, y)) == (255, 0, 0)
              for x in range(800) for y in range(60))
    assert not red


def test_claude_status_bw_no_red():
    from inkpulse_hub.render.widgets import draw_claude_status
    from inkpulse_hub.models import ClaudeStatus
    img, d = _img(300, 200)
    s = ClaudeStatus(state="error", project="X")   # needs_attention -> would be red
    draw_claude_status(d, Zone(0, 0, 300, 200), s, None, accent=BLACK)
    assert not any(img.getpixel((x, y)) == (255, 0, 0)
                   for x in range(300) for y in range(200))


def test_usage_bw_no_red_when_over():
    from inkpulse_hub.render.widgets import draw_usage
    from inkpulse_hub.models import Usage
    img, d = _img(300, 200)
    u = Usage(input_tokens=5_000_000, output_tokens=5_000_000, window_used_ratio=0.99)
    draw_usage(d, Zone(0, 0, 300, 200), u, budget_usd=0.01, accent=BLACK)
    assert not any(img.getpixel((x, y)) == (255, 0, 0)
                   for x in range(300) for y in range(200))


def test_usage_ring_bw_no_red_when_high():
    from inkpulse_hub.render.widgets import draw_usage_ring
    from inkpulse_hub.models import Usage
    img, d = _img(200, 200)
    draw_usage_ring(d, Zone(0, 0, 200, 200), Usage(window_used_ratio=0.95), accent=BLACK)
    assert not any(img.getpixel((x, y)) == (255, 0, 0)
                   for x in range(200) for y in range(200))


def test_market_and_countdown_bw_no_red():
    from inkpulse_hub.render.widgets import draw_market, draw_countdown
    img, d = _img(300, 200)
    # days=0 => "就在今天", 0<=days<=3 会触发红色
    draw_countdown(d, Zone(0, 0, 300, 100), 1718000000.0, "2024-06-10", "新年", accent=BLACK)
    # change_pct > 0 => 涨, 彩色下会触发红色
    draw_market(d, Zone(0, 100, 300, 100),
                [{"name": "AAPL", "price": 100.0, "change_pct": 2.5}], accent=BLACK)
    assert not any(img.getpixel((x, y)) == (255, 0, 0)
                   for x in range(300) for y in range(200))
