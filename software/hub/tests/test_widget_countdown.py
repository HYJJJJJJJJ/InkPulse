from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_countdown, Zone


def _img():
    img = Image.new("RGB", (300, 160), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_red(img):
    return any(img.getpixel((x, y)) == (255, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


NOW = 1718000000.0   # 2024-06-10 (本地时区附近)


def test_future_date_renders_black():
    img, d = _img()
    draw_countdown(d, Zone(0, 0, 300, 160), NOW, "2099-01-01", "新年")
    assert _has_black(img)


def test_near_date_within_3_days_is_red():
    img, d = _img()
    import datetime
    soon = (datetime.date.fromtimestamp(NOW) + datetime.timedelta(days=2)).isoformat()
    draw_countdown(d, Zone(0, 0, 300, 160), NOW, soon, "马上")
    assert _has_red(img)   # 0..3 天内告警红


def test_bad_date_does_not_crash():
    img, d = _img()
    draw_countdown(d, Zone(0, 0, 300, 160), NOW, "not-a-date", "x")
    # 不抛异常即可
