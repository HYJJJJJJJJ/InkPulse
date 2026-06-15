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
