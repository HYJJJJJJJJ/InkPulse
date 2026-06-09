# inkpulse_hub/render/planes.py
import hashlib
from PIL import Image

WIDTH, HEIGHT = 800, 480
ROW_BYTES = WIDTH // 8          # 100
PLANE_BYTES = ROW_BYTES * HEIGHT  # 48000

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
