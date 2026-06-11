# inkpulse_hub/state.py
import time
from typing import Optional
from .config import Config
from .models import ClaudeStatus
from .collectors.todos import TodoStore
from .collectors.usage import collect_usage
from .collectors.photos import pick_photo

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class HubState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.claude = ClaudeStatus()
        self.todos = TodoStore(cfg.todos_store)
        self.env = {"temp": None, "humidity": None}

    def set_claude_status(self, state: str, project: Optional[str] = None) -> None:
        self.claude = ClaudeStatus(state=state, project=project, since=time.time())

    def set_env(self, temp, humidity) -> None:
        self.env = {"temp": temp, "humidity": humidity}

    def add_todo(self, text: str):
        return self.todos.add(text)

    def _clock(self, now: float) -> str:
        lt = time.localtime(now)
        return f"{lt.tm_mon}/{lt.tm_mday} {_WEEKDAYS[lt.tm_wday]} {lt.tm_hour:02d}:{lt.tm_min:02d}"

    def build_render_state(self, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        return {
            "claude": self.claude,
            "usage": collect_usage(
                self.cfg.claude_logs,
                window_token_limit=self.cfg.usage_window_token_limit,
            ),
            "todos": self.todos.list(),
            "photo": pick_photo(self.cfg.photos_dir, now=now),
            "env": dict(self.env),
            "clock": self._clock(now),
        }
