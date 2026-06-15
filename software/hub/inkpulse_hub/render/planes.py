# inkpulse_hub/render/planes.py
import hashlib
from PIL import Image

_BLACK = (0, 0, 0)
_RED = (255, 0, 0)


def to_planes(img: Image.Image) -> tuple[bytes, bytes]:
    """RGB(仅白/黑/红) -> (黑plane, 红plane)。bit=1 表示该色;红优先。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    row_bytes = (w + 7) // 8
    black = bytearray(row_bytes * h)
    red = bytearray(row_bytes * h)
    px = rgb.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            byte_i = y * row_bytes + (x >> 3)
            bit = 0x80 >> (x & 7)
            if p == _RED:
                red[byte_i] |= bit
            elif p == _BLACK:
                black[byte_i] |= bit
    return bytes(black), bytes(red)


def pack_frame(img: Image.Image) -> bytes:
    black, red = to_planes(img)
    return black + red


def frame_etag(body: bytes) -> str:
    return '"' + hashlib.sha1(body).hexdigest() + '"'


def to_plane_bw(img: Image.Image) -> bytes:
    """RGB(白/黑) -> 单 plane。bit=1 表示黑(非纯白即视为黑)。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    row_bytes = (w + 7) // 8
    plane = bytearray(row_bytes * h)
    px = rgb.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] != (255, 255, 255):     # 非白 -> 黑
                plane[y * row_bytes + (x >> 3)] |= 0x80 >> (x & 7)
    return bytes(plane)


def pack_frame_for(img, profile) -> bytes:
    """按 profile 旋转并打包: bwr -> black+red 双 plane; bw -> 单 plane。
    旋转方向(顺时针 profile.rotate)是面板贴装约定, 真机 bring-up 可改符号。"""
    if profile.rotate:
        img = img.rotate(-profile.rotate, expand=True)   # 负角=顺时针
    if profile.color == "bw":
        return to_plane_bw(img)
    black, red = to_planes(img)
    return black + red
