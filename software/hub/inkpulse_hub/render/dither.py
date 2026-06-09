# inkpulse_hub/render/dither.py
from PIL import Image

# 三色调色板：白/黑/红
_PALETTE_RGB = [(255, 255, 255), (0, 0, 0), (255, 0, 0)]


def _palette_image() -> Image.Image:
    pal = Image.new("P", (1, 1))
    flat = []
    for c in _PALETTE_RGB:
        flat += list(c)
    flat += [0, 0, 0] * (256 - len(_PALETTE_RGB))
    pal.putpalette(flat)
    return pal


def dither_bwr(src: Image.Image, size: tuple[int, int]) -> Image.Image:
    """缩放并以 Floyd–Steinberg 抖动量化到 白/黑/红 三色，返回 RGB 图。"""
    img = src.convert("RGB").resize(size)
    quant = img.quantize(palette=_palette_image(), dither=Image.FLOYDSTEINBERG)
    return quant.convert("RGB")
