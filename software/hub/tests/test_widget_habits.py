from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_habits, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def test_draws_black_with_data():
    img, d = _img()
    habits = [{"name": "运动", "days": [True, True, False, False, False, False, False]}]
    draw_habits(d, Zone(0, 0, 400, 240), habits, today_idx=2)
    assert _has_black(img)


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_habits(d, Zone(0, 0, 400, 240), [], today_idx=3)
    assert _has_black(img)   # 提示文字也是黑像素;关键是不抛异常


def test_future_columns_left_blank():
    # today_idx=0 => 第 1..6 列都是未来,应留空(即便 days 全 True)
    img, d = _img(420, 120)
    habits = [{"name": "运动", "days": [True] * 7}]
    z = Zone(0, 0, 420, 120)
    draw_habits(d, z, habits, today_idx=0)
    # 取最后一列(周日,未来)格子中心附近,应为白
    name_w = max(60, z.w // 4)
    grid_x = z.x + name_w
    cw = (z.x + z.w - grid_x - 6) // 7
    cx = grid_x + 6 * cw + cw // 2
    cy = z.y + 26 + 6 + 22 + 15   # 标题栏+表头之后第一行附近
    assert img.getpixel((cx, cy)) == (255, 255, 255)


def test_today_idx_at_boundary_no_crash():
    img, d = _img()
    habits = [{"name": "阅读", "days": [False] * 7}]
    draw_habits(d, Zone(0, 0, 400, 240), habits, today_idx=6)   # 周日为今天
    assert _has_black(img)   # 空心格 + 今天描边都是黑;不抛异常即达标
