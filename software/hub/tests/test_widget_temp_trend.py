from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_temp_trend, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def test_draws_line_with_data():
    img, d = _img()
    samples = [[1000.0 + i * 600, 20 + i * 0.5] for i in range(10)]
    draw_temp_trend(d, Zone(0, 0, 400, 240), samples, now=1000.0 + 9 * 600)
    assert _has_black(img)


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_temp_trend(d, Zone(0, 0, 400, 240), [], now=1000.0)
    assert _has_black(img)   # "暂无温度数据" 文字也是黑像素; 关键不抛异常


def test_single_point_shows_hint():
    img, d = _img()
    draw_temp_trend(d, Zone(0, 0, 400, 240), [[1000.0, 22.0]], now=1000.0)
    assert _has_black(img)   # <2 点 -> 提示, 不崩


def test_flat_temperature_no_crash():
    img, d = _img()
    samples = [[1000.0 + i * 600, 22.0] for i in range(5)]   # 全等温度
    draw_temp_trend(d, Zone(0, 0, 400, 240), samples, now=1000.0 + 4 * 600)
    assert _has_black(img)   # tmin==tmax 画水平中线, 不除零


def test_none_now_falls_back_no_crash():
    img, d = _img()
    samples = [[1000.0 + i * 600, 20 + i] for i in range(3)]
    draw_temp_trend(d, Zone(0, 0, 400, 240), samples, now=None)
    assert _has_black(img)   # now=None -> 退回末点时间, 不崩
