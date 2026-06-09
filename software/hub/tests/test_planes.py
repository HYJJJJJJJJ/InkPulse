from PIL import Image
from inkpulse_hub.render.planes import to_planes, pack_frame, frame_etag


def _img(w, h, color):
    return Image.new("RGB", (w, h), color)


def test_plane_sizes_for_full_resolution():
    img = _img(800, 480, (255, 255, 255))
    black, red = to_planes(img)
    assert len(black) == 48000 and len(red) == 48000


def test_black_pixel_sets_black_plane_msb():
    img = _img(8, 1, (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))  # 最左像素=黑
    black, red = to_planes(img)
    assert black[0] == 0b10000000  # MSB=最左
    assert red[0] == 0b00000000


def test_red_pixel_sets_red_plane_only():
    img = _img(8, 1, (255, 255, 255))
    img.putpixel((1, 0), (255, 0, 0))
    black, red = to_planes(img)
    assert black[0] == 0b00000000
    assert red[0] == 0b01000000  # 左数第二像素


def test_pack_and_etag_stable():
    img = _img(800, 480, (255, 255, 255))
    body = pack_frame(img)
    assert len(body) == 96000
    assert frame_etag(body) == frame_etag(pack_frame(_img(800, 480, (255, 255, 255))))
