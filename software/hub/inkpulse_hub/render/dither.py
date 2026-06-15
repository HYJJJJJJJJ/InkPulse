# inkpulse_hub/render/dither.py
from PIL import Image, ImageOps

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
    """等比缩放(保持原比例, letterbox 白边居中)并以 Floyd–Steinberg 抖动量化到
    白/黑/红 三色，返回 RGB 图。避免硬缩放到 800×480 导致拉伸变形。"""
    fitted = ImageOps.contain(src.convert("RGB"), size)   # 等比缩放, 完整放进 size 内
    img = Image.new("RGB", size, (255, 255, 255))         # 白底画布
    img.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    quant = img.quantize(palette=_palette_image(), dither=Image.FLOYDSTEINBERG)
    return quant.convert("RGB")


def dither_mono(src: Image.Image, size: tuple[int, int]) -> Image.Image:
    """等比缩放 + Floyd–Steinberg 抖动到纯黑白, 返回 RGB。BW 屏照片用。"""
    fitted = ImageOps.contain(src.convert("RGB"), size)
    img = Image.new("RGB", size, (255, 255, 255))
    img.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return img.convert("L").convert("1").convert("RGB")
