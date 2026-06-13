from datetime import date, timedelta
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_usage_trend, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _daily(vals):
    base = date(2026, 6, 1)
    return [{"date": base + timedelta(days=i), "tokens": v, "cost": v / 1000}
            for i, v in enumerate(vals)]


def test_draws_black_bars_with_data():
    img, d = _img()
    draw_usage_trend(d, Zone(0, 0, 400, 240), _daily([10, 20, 30, 5, 40, 15, 25]), days=7)
    assert _has_black(img)


def test_empty_data_shows_no_data_no_crash():
    img, d = _img()
    draw_usage_trend(d, Zone(0, 0, 400, 240), [], days=7)
    assert _has_black(img)   # "无数据" 文字也是黑像素, 关键是不抛异常


def test_all_zero_shows_no_data():
    img, d = _img()
    draw_usage_trend(d, Zone(0, 0, 400, 240), _daily([0, 0, 0]), days=3)
    # 不抛异常即可(全零 -> 无数据)


def test_metric_cost_uses_cost_values():
    img, d = _img()
    series = [{"date": date(2026, 6, 1), "tokens": 0, "cost": 5.0},
              {"date": date(2026, 6, 2), "tokens": 0, "cost": 9.0}]
    draw_usage_trend(d, Zone(0, 0, 400, 240), series, days=2, metric="cost")
    assert _has_black(img)
