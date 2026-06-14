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


def _qrcode(d, img, z, state, cfg, p):
    W.draw_qrcode(img, z, p.get("content", ""))


def _usage_trend(d, img, z, state, cfg, p):
    W.draw_usage_trend(d, z, state.get("usage_daily", []),
                       days=int(p.get("days", 7) or 7),
                       metric=p.get("metric", "tokens"))


def _project_dist(d, img, z, state, cfg, p):
    W.draw_project_dist(d, z, state.get("usage_projects", []),
                        top_n=int(p.get("top_n", 5) or 5),
                        metric=p.get("metric", "tokens"))


def _habits(d, img, z, state, cfg, p):
    W.draw_habits(d, z, state.get("habits", []), state.get("habit_today_idx", 0))


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
    "qrcode":        WidgetSpec("qrcode", "二维码", _qrcode, {"cols": 2, "rows": 3},
                                [{"key": "content", "label": "内容(URL/文本)", "type": "text", "default": ""}]),
    "usage_trend":   WidgetSpec("usage_trend", "用量趋势", _usage_trend, {"cols": 4, "rows": 3},
        [{"key": "days", "label": "天数", "type": "number", "default": 7},
         {"key": "metric", "label": "度量", "type": "select", "default": "tokens",
          "options": [{"value": "tokens", "label": "Token数"},
                      {"value": "cost", "label": "花费$"}]}]),
    "project_dist":  WidgetSpec("project_dist", "项目分布", _project_dist, {"cols": 4, "rows": 3},
        [{"key": "top_n", "label": "显示前N项", "type": "number", "default": 5},
         {"key": "metric", "label": "度量", "type": "select", "default": "tokens",
          "options": [{"value": "tokens", "label": "Token数"},
                      {"value": "cost", "label": "花费$"}]}]),
    "habits":        WidgetSpec("habits", "习惯打卡", _habits, {"cols": 4, "rows": 3}),
}
