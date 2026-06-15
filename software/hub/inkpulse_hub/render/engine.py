# inkpulse_hub/render/engine.py
import io
import logging
from dataclasses import dataclass
from PIL import Image, ImageDraw
from ..config import Config
from .planes import pack_frame_for, frame_etag
from .grid import cell_to_zone
from .registry import REGISTRY
from . import layouts as L
from .profiles import ScreenProfile, DEFAULT_PROFILE
from .widgets import draw_na


@dataclass
class Frame:
    body: bytes
    etag: str
    png_bytes: bytes


def render_frame(cfg: Config, state: dict, profile: ScreenProfile = DEFAULT_PROFILE) -> Frame:
    img = Image.new("RGB", (profile.w, profile.h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"

    state = {**state, "color": profile.color}   # 注入颜色模型, 供 widget 降级
    layout = L.get_layout(cfg.layouts_store, cfg.layout_name, profile.id)
    for p in layout["placements"]:
        z = cell_to_zone(layout["grid"], p, profile.w, profile.h)
        spec = REGISTRY.get(p["widget"])
        if spec is None:
            draw_na(d, z)
            continue
        try:
            spec.draw(d, img, z, state, cfg, p.get("params", {}))
        except Exception as e:
            logging.getLogger("inkpulse").warning("widget %s 渲染失败: %s", p.get("widget"), e)
            draw_na(d, z)

    body = pack_frame_for(img, profile)
    assert len(body) == profile.frame_bytes, \
        f"{profile.id} 帧字节={len(body)} 与 profile.frame_bytes={profile.frame_bytes} 不符"
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
