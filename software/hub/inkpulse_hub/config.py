# inkpulse_hub/config.py
import os
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
    layout: list[str] = field(default_factory=lambda: list(DEFAULT_LAYOUT))
    # 5h 滚动窗口的 token 估算上限(用于 usage 进度条占用比例);按你的订阅档位调整
    usage_window_token_limit: Optional[int] = 2_000_000


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
    layout = data.get("layout", {})
    cfg.layout = layout.get("widgets", cfg.layout)
    usage = data.get("usage", {})
    cfg.usage_window_token_limit = usage.get("window_token_limit", cfg.usage_window_token_limit)
    return cfg
