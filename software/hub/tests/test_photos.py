from PIL import Image
from inkpulse_hub.collectors.photos import pick_photo
from inkpulse_hub.render.dither import dither_bwr


def test_pick_photo_none_when_empty(tmp_path):
    assert pick_photo(str(tmp_path)) is None


def test_pick_photo_returns_image_file(tmp_path):
    f = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (120, 0, 0)).save(f)
    p = pick_photo(str(tmp_path))
    assert p is not None and p.path.endswith("a.png")


def test_dither_outputs_only_three_colors():
    src = Image.new("RGB", (16, 16), (200, 40, 40))  # 偏红的灰
    out = dither_bwr(src, (16, 16))
    colors = {px for px in out.getdata()}
    assert colors <= {(255, 255, 255), (0, 0, 0), (255, 0, 0)}
    assert out.size == (16, 16)
