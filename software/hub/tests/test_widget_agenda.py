import time
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_agenda, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


NOW = time.mktime((2026, 6, 14, 12, 0, 0, 0, 0, -1))   # 2026-06-14 周日


def test_draws_with_data():
    img, d = _img()
    events = [{"title": "团队周会", "date": "2026-06-14", "time": "14:30"},
              {"title": "交报告", "date": "2026-06-14", "time": ""},
              {"title": "看演出", "date": "2026-06-18", "time": "19:00"}]
    draw_agenda(d, Zone(0, 0, 400, 240), events, NOW)
    assert _has_black(img)


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_agenda(d, Zone(0, 0, 400, 240), [], NOW)
    assert _has_black(img)   # 提示文字也是黑像素; 关键不抛异常


def test_today_tomorrow_and_allday_labels_no_crash():
    img, d = _img()
    events = [{"title": "今日事", "date": "2026-06-14", "time": "08:00"},   # 今天
              {"title": "明日事", "date": "2026-06-15", "time": ""},        # 明天 全天
              {"title": "后续事", "date": "2026-06-20", "time": "10:00"}]   # 6/20
    draw_agenda(d, Zone(0, 0, 400, 240), events, NOW)
    assert _has_black(img)


def test_long_title_truncated_no_crash():
    img, d = _img(300, 120)
    events = [{"title": "这是一个非常非常非常长的日程标题需要被截断" * 3,
               "date": "2026-06-14", "time": "09:00"}]
    draw_agenda(d, Zone(0, 0, 300, 120), events, NOW)
    assert _has_black(img)
