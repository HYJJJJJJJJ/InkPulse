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


from inkpulse_hub.render.planes import to_plane_bw, pack_frame_for
from inkpulse_hub.render.profiles import PROFILES


def test_bw_plane_size_and_black_bit():
    img = _img(8, 1, (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))      # 最左像素=黑
    plane = to_plane_bw(img)
    assert plane[0] == 0b10000000        # bit=1 表示黑, MSB=最左


def test_pack_frame_for_bwr_matches_legacy():
    img = _img(800, 480, (255, 255, 255))
    assert pack_frame_for(img, PROFILES["bwr_750"]) == pack_frame(img)
    assert len(pack_frame_for(img, PROFILES["bwr_750"])) == 96000


def test_pack_frame_for_bw_rotates_to_48000():
    # bw_426 渲染画布 480x800, 旋转 90 -> 800x480 -> 单 plane 48000B
    img = _img(480, 800, (255, 255, 255))
    body = pack_frame_for(img, PROFILES["bw_426"])
    assert len(body) == 48000


def test_pack_frame_for_bw_black_canvas_all_ones():
    img = _img(480, 800, (0, 0, 0))      # 全黑
    body = pack_frame_for(img, PROFILES["bw_426"])
    assert set(body) == {0xFF}           # 每 bit=1
