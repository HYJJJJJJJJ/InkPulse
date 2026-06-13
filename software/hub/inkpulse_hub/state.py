# inkpulse_hub/state.py
import time
import datetime as _dt
from typing import Optional
import cnlunar
from .config import Config
from .models import ClaudeStatus
from .collectors.todos import TodoStore
from .collectors.usage import collect_usage, collect_daily_usage, collect_project_usage
from .collectors.photos import pick_photo

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def lunar_info(now: float) -> dict:
    """农历信息(纯算法, 不联网)。返回 {"text": 主体, "festival": 节日名或""}。
    主体形如 "农历四月廿七 · 丙午马年[ · 芒种]"; 节日单独返回, 供渲染标红。"""
    a = cnlunar.Lunar(_dt.datetime.fromtimestamp(now), godType="8char")
    month = a.lunarMonthCn
    if month and month[-1] in "大小":   # "四月小" -> "四月"
        month = month[:-1]
    parts = [f"农历{month}{a.lunarDayCn}", f"{a.year8Char}{a.chineseYearZodiac}年"]
    term = (a.todaySolarTerms or "").strip()
    if term and term != "无":
        parts.append(term)
    festival = (a.get_legalHolidays() or a.get_otherLunarHolidays()
                or a.get_otherHolidays() or "").strip()
    return {"text": " · ".join(parts), "festival": festival}


class HubState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.claude = ClaudeStatus()
        self.todos = TodoStore(cfg.todos_store)
        self.env = {"temp": None, "humidity": None, "rssi": None}

    def set_claude_status(self, state: str, project: Optional[str] = None) -> None:
        self.claude = ClaudeStatus(state=state, project=project, since=time.time())

    def set_env(self, temp, humidity, rssi=None) -> None:
        self.env = {"temp": temp, "humidity": humidity, "rssi": rssi}

    def add_todo(self, text: str):
        return self.todos.add(text)

    def _clock(self, now: float) -> str:
        lt = time.localtime(now)
        return (f"{lt.tm_year}-{lt.tm_mon:02d}-{lt.tm_mday:02d} "
                f"{lt.tm_hour:02d}:{lt.tm_min:02d} {_WEEKDAYS[lt.tm_wday]}")

    def build_render_state(self, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        return {
            "claude": self.claude,
            "usage": collect_usage(
                self.cfg.claude_logs,
                window_token_limit=self.cfg.usage_window_token_limit,
            ),
            "todos": self.todos.list(),
            "photo": pick_photo(self.cfg.photos_dir, now=now,
                                pinned=getattr(self.cfg, "photo_pinned", "")),
            "env": dict(self.env),
            "clock": self._clock(now),
            "usage_daily": collect_daily_usage(self.cfg.claude_logs),
            "usage_projects": collect_project_usage(self.cfg.claude_logs),
            "lunar": lunar_info(now),
            "now": now,
        }
