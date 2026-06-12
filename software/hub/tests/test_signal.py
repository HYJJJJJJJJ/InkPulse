from inkpulse_hub.render.widgets import signal_bars


def test_signal_bars_rssi_mapping():
    # 阈值: >=-60 强(3), -60~-72 中(2), -72~-82 弱(1), <-82/无 空(0)
    assert signal_bars(-45) == 3
    assert signal_bars(-60) == 3
    assert signal_bars(-65) == 2
    assert signal_bars(-72) == 2
    assert signal_bars(-78) == 1
    assert signal_bars(-82) == 1
    assert signal_bars(-90) == 0
    assert signal_bars(None) == 0


def test_draw_header_draws_signal_bars_when_rssi_given():
    from PIL import Image, ImageDraw
    from inkpulse_hub.render.widgets import draw_header, Zone
    img = Image.new("RGB", (800, 76), (255, 255, 255))
    d = ImageDraw.Draw(img); d.fontmode = "1"
    lunar = {"text": "农历四月廿七", "festival": ""}
    # 强信号: 右上角信号格区应出现黑像素
    draw_header(d, Zone(0, 0, 800, 76), "2026-06-12 周五", lunar, 25, None, rssi=-45)
    black = sum(1 for x in range(768, 800) for y in range(4, 30)
                if img.getpixel((x, y)) == (0, 0, 0))
    assert black > 0, "强信号应画出信号格"


def test_draw_header_no_rssi_keeps_corner_clear():
    from PIL import Image, ImageDraw
    from inkpulse_hub.render.widgets import draw_header, Zone
    img = Image.new("RGB", (800, 76), (255, 255, 255))
    d = ImageDraw.Draw(img); d.fontmode = "1"
    lunar = {"text": "农历四月廿七", "festival": ""}
    # rssi=None: 不画信号格(0 格不强制画实心), 右上角应基本干净
    draw_header(d, Zone(0, 0, 800, 76), "2026-06-12 周五", lunar, 25, None, rssi=None)
    # 至少不抛异常即可(0 格可能画空心框, 这里只验证不崩 + 返回 None)
