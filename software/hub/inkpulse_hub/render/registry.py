# inkpulse_hub/render/registry.py
# Widget 注册表: 统一签名 draw(d, img, zone, state, cfg, params)。
# 适配器负责从 state/cfg/params 取数, 调用 widgets.py 里的纯绘制函数。
from dataclasses import dataclass, field
from typing import Callable
from PIL import Image
from . import widgets as W
from .dither import dither_bwr


@dataclass
class WidgetSpec:
    name: str
    label: str
    draw: Callable          # (d, img, zone, state, cfg, params) -> None
    default_span: dict      # {"cols": int, "rows": int}
    params: list = field(default_factory=list)  # [{key,label,type,default}]


def _header(d, img, z, state, cfg, p):
    env = state.get("env", {})
    W.draw_header(d, z, state.get("clock", ""), state.get("lunar"),
                  env.get("temp"), env.get("humidity"), env.get("rssi"))


def _claude(d, img, z, state, cfg, p):
    W.draw_claude_status(d, z, state["claude"], state.get("now"))


def _usage(d, img, z, state, cfg, p):
    W.draw_usage(d, z, state["usage"], cfg.usage_budget_usd)


def _usage_ring(d, img, z, state, cfg, p):
    W.draw_usage_ring(d, z, state["usage"])


def _todos(d, img, z, state, cfg, p):
    W.draw_todos(d, z, state.get("todos", []))


def _big_clock(d, img, z, state, cfg, p):
    W.draw_big_clock(d, z, state.get("now"))


def _calendar(d, img, z, state, cfg, p):
    W.draw_month_calendar(d, z, state.get("now"))


def _photo(d, img, z, state, cfg, p):
    photo = state.get("photo")
    if photo is None:
        W._center_text(d, z, "无照片", W._font(24), W.BLACK)
        return
    im = dither_bwr(Image.open(photo.path), (z.w, z.h))
    img.paste(im, (z.x, z.y))


def _countdown(d, img, z, state, cfg, p):
    W.draw_countdown(d, z, state.get("now"), p.get("date"), p.get("label", ""))


REGISTRY: dict[str, WidgetSpec] = {
    "header":        WidgetSpec("header", "头部", _header, {"cols": 8, "rows": 1}),
    "claude_status": WidgetSpec("claude_status", "Claude状态", _claude, {"cols": 4, "rows": 3}),
    "usage":         WidgetSpec("usage", "今日用量", _usage, {"cols": 4, "rows": 3}),
    "usage_ring":    WidgetSpec("usage_ring", "用量环", _usage_ring, {"cols": 3, "rows": 3}),
    "todos":         WidgetSpec("todos", "待办", _todos, {"cols": 8, "rows": 2}),
    "big_clock":     WidgetSpec("big_clock", "大时钟", _big_clock, {"cols": 8, "rows": 4}),
    "calendar":      WidgetSpec("calendar", "月历", _calendar, {"cols": 4, "rows": 3}),
    "photo":         WidgetSpec("photo", "整屏照片", _photo, {"cols": 8, "rows": 6}),
    "countdown":     WidgetSpec("countdown", "倒计时", _countdown, {"cols": 3, "rows": 2},
                                [{"key": "date", "label": "目标日期", "type": "date", "default": ""},
                                 {"key": "label", "label": "标签", "type": "text", "default": ""}]),
}
