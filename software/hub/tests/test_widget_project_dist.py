from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_project_dist, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _projects(pairs):
    return [{"project": p, "tokens": t, "cost": t / 1000} for p, t in pairs]


def test_draws_black_with_data():
    img, d = _img()
    draw_project_dist(d, Zone(0, 0, 400, 240), _projects([("InkPulse", 60), ("webapp", 40)]))
    assert _has_black(img)


def test_top_n_caps_and_merges_others():
    img, d = _img(h=300)
    projs = _projects([(f"proj{i}", 10 * (6 - i)) for i in range(6)])
    rows = []
    orig = ImageDraw.ImageDraw.text
    def spy(self, xy, text, *a, **k):
        rows.append(text)
        return orig(self, xy, text, *a, **k)
    ImageDraw.ImageDraw.text = spy
    try:
        draw_project_dist(d, Zone(0, 0, 400, 300), projs, top_n=2)
    finally:
        ImageDraw.ImageDraw.text = orig
    assert any("其他" in t for t in rows)
    assert any("proj0" in t for t in rows)
    assert not any("proj5" in t for t in rows)


def test_empty_shows_no_data_no_crash():
    img, d = _img()
    draw_project_dist(d, Zone(0, 0, 400, 240), [])
    # 不抛异常即可
