# inkpulse_hub/config.py
import os
import json
from dataclasses import dataclass, field
from typing import Optional
import yaml

DEFAULT_LAYOUT = ["header_clock_env", "claude_status", "usage", "todos"]


@dataclass
class Config:
    refresh_min_interval_s: int = 60
    refresh_periodic_s: int = 600
    claude_logs: str = os.path.expanduser("~/.claude/projects")
    photos_dir: str = os.path.expanduser("~/inkpulse/photos")
    todos_store: str = os.path.expanduser("~/inkpulse/todos.json")
    habits_store: str = os.path.expanduser("~/inkpulse/habits.json")
    env_history_store: str = os.path.expanduser("~/inkpulse/env_history.json")
    weather_cache: str = os.path.expanduser("~/inkpulse/weather_cache.json")
    weather_lat: Optional[float] = None
    weather_lon: Optional[float] = None
    weather_place: str = ""
    events_store: str = os.path.expanduser("~/inkpulse/events.json")
    market_cache: str = os.path.expanduser("~/inkpulse/market_cache.json")
    market_symbols: list = field(default_factory=list)
    runtime_store: str = os.path.expanduser("~/inkpulse/runtime.json")
    layouts_store: str = os.path.expanduser("~/inkpulse/layouts.json")
    layout: list[str] = field(default_factory=lambda: list(DEFAULT_LAYOUT))
    layout_name: str = "dash"   # 当前布局: dash/photo/usage/todo/clock/split
    # 5h 滚动窗口的 token 估算上限(用于 usage 进度条占用比例);按你的订阅档位调整
    usage_window_token_limit: Optional[int] = 2_000_000
    # 今日花费预算(USD);设了且超过时仪表盘花费数字标红。默认 None=不启用(数字恒黑)
    usage_budget_usd: Optional[float] = None
    # 钉住显示的照片文件名(空=按时间自动轮换);photo 布局用
    photo_pinned: str = ""


def load_config(path: Optional[str]) -> Config:
    cfg = Config()
    if not path or not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    refresh = data.get("refresh", {})
    cfg.refresh_min_interval_s = refresh.get("min_interval_s", cfg.refresh_min_interval_s)
    cfg.refresh_periodic_s = refresh.get("periodic_s", cfg.refresh_periodic_s)
    sources = data.get("sources", {})
    cfg.claude_logs = os.path.expanduser(sources.get("claude_logs", cfg.claude_logs))
    cfg.photos_dir = os.path.expanduser(sources.get("photos_dir", cfg.photos_dir))
    cfg.todos_store = os.path.expanduser(sources.get("todos_store", cfg.todos_store))
    cfg.habits_store = os.path.expanduser(sources.get("habits_store", cfg.habits_store))
    cfg.env_history_store = os.path.expanduser(sources.get("env_history_store", cfg.env_history_store))
    cfg.weather_cache = os.path.expanduser(sources.get("weather_cache", cfg.weather_cache))
    cfg.events_store = os.path.expanduser(sources.get("events_store", cfg.events_store))
    cfg.market_cache = os.path.expanduser(sources.get("market_cache", cfg.market_cache))
    cfg.runtime_store = os.path.expanduser(sources.get("runtime_store", cfg.runtime_store))
    cfg.layouts_store = os.path.expanduser(sources.get("layouts_store", cfg.layouts_store))
    layout = data.get("layout", {})
    cfg.layout = layout.get("widgets", cfg.layout)
    cfg.layout_name = layout.get("name", cfg.layout_name)
    usage = data.get("usage", {})
    cfg.usage_window_token_limit = usage.get("window_token_limit", cfg.usage_window_token_limit)
    cfg.usage_budget_usd = usage.get("budget_usd", cfg.usage_budget_usd)
    return cfg


# 运行时可调字段(web 配置面板改的项), 存 runtime.json, 与部署级 config.yaml 分离。
RUNTIME_FIELDS = [
    "layout_name", "usage_budget_usd", "usage_window_token_limit", "refresh_periodic_s",
    "photo_pinned",
    "weather_lat", "weather_lon", "weather_place",
    "market_symbols",
]


def save_runtime(cfg: Config, path: str) -> None:
    data = {f: getattr(cfg, f) for f in RUNTIME_FIELDS}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_runtime(cfg: Config, path: str) -> None:
    """从 runtime.json 覆盖 cfg 的可调字段(只认 RUNTIME_FIELDS)。文件不存在则 no-op。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh) or {}
    for k in RUNTIME_FIELDS:
        if k in data:
            setattr(cfg, k, data[k])
