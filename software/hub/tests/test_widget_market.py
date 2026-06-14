from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_market, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has(img, color):
    return any(img.getpixel((x, y)) == color
              for x in range(img.width) for y in range(img.height))


def _q(name, price, pct, t="cn", code="x"):
    return {"type": t, "code": code, "name": name, "price": price, "change_pct": pct}


def test_up_is_red_down_is_black():
    img, d = _img()
    draw_market(d, Zone(0, 0, 400, 240),
                [_q("上证指数", 4031.51, 1.12), _q("某跌票", 10.0, -2.0)])
    assert _has(img, (0, 0, 0)) and _has(img, (255, 0, 0))   # 有黑(名/价/跌) + 有红(涨)


def test_all_down_no_red():
    img, d = _img()
    draw_market(d, Zone(0, 0, 400, 240), [_q("跌一", 10.0, -1.0), _q("跌二", 5.0, -0.5)])
    assert _has(img, (0, 0, 0)) and not _has(img, (255, 0, 0))


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_market(d, Zone(0, 0, 400, 240), [])
    assert _has(img, (0, 0, 0))


def test_long_name_truncated_no_crash():
    img, d = _img(280, 100)
    draw_market(d, Zone(0, 0, 280, 100), [_q("超长名称" * 8, 1.0, 0.0)])
    assert _has(img, (0, 0, 0))
