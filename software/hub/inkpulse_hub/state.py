# inkpulse_hub/state.py
import time
import datetime as _dt
from typing import Optional
import cnlunar
from .config import Config
from .models import ClaudeStatus
from .collectors.todos import TodoStore
from .collectors.habits import HabitStore
from .collectors.env_history import EnvHistoryStore
from .collectors.weather import WeatherService
from .collectors.events import EventStore, AGENDA_LIMIT
from .collectors.market import MarketService
from .collectors.agent_tasks import AgentTaskStore
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
        self.habits = HabitStore(cfg.habits_store)
        self.env_history = EnvHistoryStore(cfg.env_history_store)
        self.weather = WeatherService(cfg.weather_cache)
        self.events = EventStore(cfg.events_store)
        self.market = MarketService(cfg.market_cache)
        self.agent_tasks = AgentTaskStore(cfg.agent_tasks_store)
        self.env = {"temp": None, "humidity": None, "rssi": None}
        # web 同步令牌: 独立于设备 refresh_token, 只驱动网页自动刷新(数据改/配置改/设备拉帧均 bump)
        self.web_token = 0
        # 最后送给设备的帧(= 设备此刻物理显示的内容)
        self.device_frame_png: Optional[bytes] = None
        self.device_frame_etag: Optional[str] = None
        self.device_frame_pulled_at: Optional[float] = None
        self.device_frame_env = {"temp": None, "humidity": None, "rssi": None}

    def bump_web(self) -> int:
        """递增 web 同步令牌, 供 SSE 通知网页刷新。不影响设备 refresh_token。"""
        self.web_token += 1
        return self.web_token

    def record_device_frame(self, png_bytes: bytes, etag: str, now: float) -> None:
        """记录设备刚拉走的真实帧(非 304), 连同当时 env 快照, 并 bump web 令牌。"""
        self.device_frame_png = png_bytes
        self.device_frame_etag = etag
        self.device_frame_pulled_at = now
        self.device_frame_env = dict(self.env)
        self.bump_web()

    def set_claude_status(self, state: str, project: Optional[str] = None) -> None:
        self.claude = ClaudeStatus(state=state, project=project, since=time.time())
        self.bump_web()

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
        lat, lon = self.cfg.weather_lat, self.cfg.weather_lon
        if lat is not None and lon is not None:
            self.weather.maybe_refresh(lat, lon, now)
            weather = self.weather.current(now)
            weather_place = self.cfg.weather_place or None
        else:
            weather, weather_place = None, None
        syms = self.cfg.market_symbols or []
        if syms:
            self.market.maybe_refresh(syms, now)
            market = self.market.current()
        else:
            market = []
        habits, habit_today_idx = self.habits.week_view(now)
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
            "habits": habits,
            "habit_today_idx": habit_today_idx,
            "env_history": self.env_history.window(now),
            "weather": weather,
            "weather_place": weather_place,
            "events": self.events.upcoming(now, AGENDA_LIMIT),
            "market": market,
            "agent_tasks": self.agent_tasks.current(now),
            "now": now,
        }
