from PIL import Image
from inkpulse_hub.render.widgets import draw_qrcode, Zone


def _img():
    return Image.new("RGB", (200, 200), (255, 255, 255))


def test_qrcode_paints_black_and_only_bw():
    img = _img()
    draw_qrcode(img, Zone(0, 0, 200, 200), "https://example.com")
    colors = {img.getpixel((x, y)) for x in range(0, 200, 3) for y in range(0, 200, 3)}
    assert (0, 0, 0) in colors                       # 画了黑模块
    assert colors <= {(0, 0, 0), (255, 255, 255)}    # 仅黑白, 无灰/红(墨水屏友好)


def test_qrcode_empty_content_no_crash():
    img = _img()
    draw_qrcode(img, Zone(0, 0, 200, 200), "")
    # 空内容不画、不抛异常
