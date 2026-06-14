from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_weather, _wx_icon, Zone


def _img(w=300, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _weather():
    return {"cur_temp": 23.4, "cur_code": 2, "cur_cn": "多云", "cur_cat": "partly",
            "today_hi": 26.0, "today_lo": 18.0, "age_s": 720, "status": "ok",
            "days": [{"label": "明", "cn": "晴", "cat": "sun", "hi": 27.0, "lo": 19.0},
                     {"label": "周二", "cn": "阴", "cat": "cloud", "hi": 24.0, "lo": 17.0},
                     {"label": "周三", "cn": "小雨", "cat": "rain", "hi": 22.0, "lo": 16.0}]}


def test_draws_normal_weather():
    img, d = _img()
    draw_weather(d, Zone(0, 0, 300, 240), _weather(), "杭州")
    assert _has_black(img)


def test_all_seven_icons_draw():
    for cat in ["sun", "partly", "cloud", "fog", "rain", "snow", "thunder"]:
        img, d = _img(60, 60)
        _wx_icon(d, 30, 30, 18, cat)
        assert _has_black(img), f"{cat} 没画出黑像素"


def test_no_location_hint():
    img, d = _img()
    draw_weather(d, Zone(0, 0, 300, 240), None, None)   # place=None -> 未设置
    assert _has_black(img)


def test_loading_hint():
    img, d = _img()
    draw_weather(d, Zone(0, 0, 300, 240), None, "杭州")  # 有 place 无 weather -> 加载中
    assert _has_black(img)
