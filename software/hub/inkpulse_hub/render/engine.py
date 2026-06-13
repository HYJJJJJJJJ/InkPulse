# inkpulse_hub/render/engine.py
import io
import logging
from dataclasses import dataclass
from PIL import Image, ImageDraw
from ..config import Config
from .planes import pack_frame, frame_etag, WIDTH, HEIGHT
from .grid import cell_to_zone
from .registry import REGISTRY
from . import layouts as L
from .widgets import draw_na


@dataclass
class Frame:
    body: bytes       # 96000B 双 plane
    etag: str
    png_bytes: bytes  # /preview.png 用


def render_frame(cfg: Config, state: dict) -> Frame:
    img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"   # 关抗锯齿: 墨水屏三色量化, 文字纯黑/白

    layout = L.get_layout(cfg.layouts_store, cfg.layout_name)
    for p in layout["placements"]:
        z = cell_to_zone(layout["grid"], p)
        spec = REGISTRY.get(p["widget"])
        if spec is None:
            draw_na(d, z)
            continue
        try:
            spec.draw(d, img, z, state, cfg, p.get("params", {}))
        except Exception as e:
            logging.getLogger("inkpulse").warning("widget %s 渲染失败: %s", p.get("widget"), e)
            draw_na(d, z)   # 按 widget 隔离容错

    body = pack_frame(img)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
