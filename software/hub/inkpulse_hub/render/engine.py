# inkpulse_hub/render/engine.py
import io
from dataclasses import dataclass
from PIL import Image, ImageDraw
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
    # header 两行(日期时间 + 农历)需 76px; 下方各区顺移, 总高仍 480
    "header_clock_env": W.Zone(0, 0, WIDTH, 76),
    "claude_status": W.Zone(0, 76, 480, 192),
    "usage": W.Zone(480, 76, 320, 192),
    "todos": W.Zone(0, 268, WIDTH, 212),
    "photo": W.Zone(0, 0, WIDTH, HEIGHT),  # 全屏照片布局
}


# ---- 布局渲染函数(每个布局一个; 统一签名 draw_xxx(d, img, state, cfg)) ----

def draw_dash(d, img, state, cfg):
    """状态仪表盘: header + 状态 + 用量 + 待办(现有默认布局)。"""
    for name in cfg.layout:
        z = ZONES.get(name)
        if z is None:
            continue
        if name == "header_clock_env":
            env = state.get("env", {})
            W.draw_header(d, z, state.get("clock", ""), state.get("lunar"),
                          env.get("temp"), env.get("humidity"), env.get("rssi"))
        elif name == "claude_status":
            W.draw_claude_status(d, z, state["claude"], state.get("now"))
        elif name == "usage":
            W.draw_usage(d, z, state["usage"], cfg.usage_budget_usd)
        elif name == "todos":
            W.draw_todos(d, z, state.get("todos", []))


def draw_photo(d, img, state, cfg):
    """整屏三色照片; 无图回退仪表盘。"""
    if state.get("photo") is not None:
        photo = dither_bwr(Image.open(state["photo"].path), (WIDTH, HEIGHT))
        img.paste(photo, (0, 0))
    else:
        draw_dash(d, img, state, cfg)


def draw_clock(d, img, state, cfg):
    """万年历摆钟: 巨型时钟 + 农历/节气 + 月历。"""
    now = state.get("now")
    W.draw_big_clock(d, W.Zone(0, 8, WIDTH, 176), now)
    lunar = state.get("lunar") or {}
    W._center_text(d, W.Zone(0, 190, WIDTH, 42), lunar.get("text", ""), W._font(26), W.BLACK)
    W.draw_month_calendar(d, W.Zone(40, 244, WIDTH - 80, 228), now)


def draw_split(d, img, state, cfg):
    """均衡双栏: 左(header+状态+用量) / 右(月历+待办)。"""
    env = state.get("env", {})
    W.draw_header(d, W.Zone(0, 0, 400, 76), state.get("clock", ""), state.get("lunar"),
                  env.get("temp"), env.get("humidity"), env.get("rssi"))
    W.draw_claude_status(d, W.Zone(0, 76, 400, 200), state["claude"], state.get("now"))
    W.draw_usage(d, W.Zone(0, 276, 400, 204), state["usage"], cfg.usage_budget_usd)
    W.draw_month_calendar(d, W.Zone(408, 8, 384, 232), state.get("now"))
    W.draw_todos(d, W.Zone(400, 246, 400, 234), state.get("todos", []))
    d.line((400, 0, 400, HEIGHT), fill=W.BLACK, width=1)


def draw_usage(d, img, state, cfg):
    """用量主导: 巨号 token + 5h 进度环; 状态/待办压小。"""
    u = state["usage"]
    tok = getattr(u, "input_tokens", 0) + getattr(u, "output_tokens", 0)
    W._center_text(d, W.Zone(0, 28, 520, 150), f"{tok:,}", W._font(72), W.BLACK)
    W._center_text(d, W.Zone(0, 184, 520, 50), "tokens · 5h", W._font(26), W.BLACK)
    W.draw_usage_ring(d, W.Zone(520, 18, 280, 252), u)
    d.line((0, 280, WIDTH, 280), fill=W.BLACK, width=1)
    W.draw_claude_status(d, W.Zone(0, 286, 400, 194), state["claude"], state.get("now"))
    W.draw_todos(d, W.Zone(400, 286, 400, 194), state.get("todos", []))


def draw_todo(d, img, state, cfg):
    """待办看板: 左大待办清单 / 右侧栏(月历+状态)。"""
    W.draw_todos(d, W.Zone(0, 0, 528, HEIGHT), state.get("todos", []))
    W.draw_month_calendar(d, W.Zone(540, 8, 252, 224), state.get("now"))
    W.draw_claude_status(d, W.Zone(528, 240, 272, 240), state["claude"], state.get("now"))
    d.line((530, 0, 530, HEIGHT), fill=W.BLACK, width=1)


# 布局注册表: 加布局 = 加一个函数 + 一项
LAYOUTS = {
    "dash":  draw_dash,
    "photo": draw_photo,
    "usage": draw_usage,
    "todo":  draw_todo,
    "clock": draw_clock,
    "split": draw_split,
}


def render_frame(cfg: Config, state: dict) -> Frame:
    img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # 关抗锯齿: 墨水屏三色量化, 1-bit 模式让文字纯黑/白, 小字不发虚。
    d.fontmode = "1"
    draw = LAYOUTS.get(cfg.layout_name, draw_dash)
    draw(d, img, state, cfg)

    body = pack_frame(img)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
