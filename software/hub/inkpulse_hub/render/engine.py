# inkpulse_hub/render/engine.py
import io
from dataclasses import dataclass
from PIL import Image
from ..config import Config
from .planes import pack_frame, frame_etag, WIDTH, HEIGHT
from .dither import dither_bwr
from . import widgets as W


@dataclass
class Frame:
    body: bytes       # 96000B 双 plane
    etag: str
    png_bytes: bytes  # /preview.png 用


# 默认布局各 widget 的固定分区
ZONES = {
    "header_clock_env": W.Zone(0, 0, WIDTH, 60),
    "claude_status": W.Zone(0, 60, 480, 200),
    "usage": W.Zone(480, 60, 320, 200),
    "todos": W.Zone(0, 260, WIDTH, 220),
    "photo": W.Zone(0, 0, WIDTH, HEIGHT),  # 全屏照片布局
}


def render_frame(cfg: Config, state: dict) -> Frame:
    img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))

    if cfg.layout == ["photo"] and state.get("photo") is not None:
        photo = dither_bwr(Image.open(state["photo"].path), (WIDTH, HEIGHT))
        img.paste(photo, (0, 0))
    else:
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        # 关抗锯齿: 墨水屏只有黑/白/红, 抗锯齿灰边会在三色量化(to_planes 严格相等)时
        # 丢失, 导致小字笔画发虚看不清。1-bit 模式让文字渲染为纯黑/白。
        d.fontmode = "1"
        for name in cfg.layout:
            z = ZONES.get(name)
            if z is None:
                continue
            if name == "header_clock_env":
                env = state.get("env", {})
                W.draw_header(d, z, state.get("clock", ""), env.get("temp"), env.get("humidity"))
            elif name == "claude_status":
                W.draw_claude_status(d, z, state["claude"])
            elif name == "usage":
                W.draw_usage(d, z, state["usage"])
            elif name == "todos":
                W.draw_todos(d, z, state.get("todos", []))

    body = pack_frame(img)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
