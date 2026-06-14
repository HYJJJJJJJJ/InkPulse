# inkpulse_hub/collectors/weather.py
import datetime as _dt
import json
import os
import threading
import urllib.parse
import urllib.request

REFRESH_S = 1800   # 缓存 30 分钟过期

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# WMO 天气码 -> (中文词, 图标类别)。类别: sun/partly/cloud/fog/rain/snow/thunder
WMO_CN = {
    0: ("晴", "sun"), 1: ("晴", "sun"), 2: ("多云", "partly"), 3: ("阴", "cloud"),
    45: ("雾", "fog"), 48: ("雾", "fog"),
    51: ("毛毛雨", "rain"), 53: ("毛毛雨", "rain"), 55: ("毛毛雨", "rain"),
    56: ("冻雨", "rain"), 57: ("冻雨", "rain"),
    61: ("小雨", "rain"), 63: ("中雨", "rain"), 65: ("大雨", "rain"),
    66: ("冻雨", "rain"), 67: ("冻雨", "rain"),
    71: ("小雪", "snow"), 73: ("中雪", "snow"), 75: ("大雪", "snow"), 77: ("雪粒", "snow"),
    80: ("阵雨", "rain"), 81: ("阵雨", "rain"), 82: ("强阵雨", "rain"),
    85: ("阵雪", "snow"), 86: ("阵雪", "snow"),
    95: ("雷阵雨", "thunder"), 96: ("雷阵雨", "thunder"), 99: ("雷阵雨", "thunder"),
}


def _cn_cat(code):
    return WMO_CN.get(int(code), ("未知", "cloud"))


def is_stale(fetched_at, now) -> bool:
    return (now - fetched_at) >= REFRESH_S


def parse_weather(raw: dict, now: float) -> dict:
    """纯函数: Open-Meteo forecast JSON -> 结构化天气。未来 3 天(明/周X)。"""
    cur = raw["current"]
    cur_cn, cur_cat = _cn_cat(cur["weather_code"])
    daily = raw["daily"]
    dates = [_dt.date.fromisoformat(s) for s in daily["time"]]
    today = _dt.date.fromtimestamp(now)
    days = []
    for i in range(1, min(4, len(dates))):
        cn, cat = _cn_cat(daily["weather_code"][i])
        dt = dates[i]
        label = "明" if dt == today + _dt.timedelta(days=1) else _WEEKDAYS[dt.weekday()]
        days.append({"label": label, "cn": cn, "cat": cat,
                     "hi": float(daily["temperature_2m_max"][i]),
                     "lo": float(daily["temperature_2m_min"][i])})
    return {
        "cur_temp": float(cur["temperature_2m"]),
        "cur_code": int(cur["weather_code"]),
        "cur_cn": cur_cn, "cur_cat": cur_cat,
        "today_hi": float(daily["temperature_2m_max"][0]),
        "today_lo": float(daily["temperature_2m_min"][0]),
        "days": days,
    }


OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT_S = 8


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        return json.load(r)


def fetch_weather(lat, lon) -> dict:
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "auto", "forecast_days": 4,
    })
    return _get_json(f"{OPEN_METEO}?{q}")


def geocode(name) -> list:
    if not (name or "").strip():
        return []
    q = urllib.parse.urlencode({"name": name, "count": 5, "language": "zh"})
    try:
        data = _get_json(f"{GEOCODE}?{q}")
    except Exception:
        return []
    out = []
    for r in (data.get("results") or []):
        admin = " ".join(x for x in [r.get("country", ""), r.get("admin1", "")] if x)
        out.append({"name": r.get("name", ""), "lat": r.get("latitude"),
                    "lon": r.get("longitude"), "admin": admin})
    return out


class WeatherService:
    """带缓存的天气服务。current() 只读缓存(渲染用, 不触网);
    maybe_refresh() 过期才起后台线程抓取(不阻塞渲染)。"""

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._refreshing = False

    def _read_cache(self):
        if not os.path.exists(self.cache_path):
            return None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or "raw" not in d:
                return None
            return d
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    def _write_cache(self, fetched_at, lat, lon, raw):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": fetched_at, "lat": lat, "lon": lon, "raw": raw},
                      f, ensure_ascii=False)

    def current(self, now):
        c = self._read_cache()
        if c is None:
            return None
        try:
            data = parse_weather(c["raw"], now)
            data["age_s"] = now - c["fetched_at"]
            data["status"] = "stale" if is_stale(c["fetched_at"], now) else "ok"
            return data
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    def clear(self):
        try:
            os.remove(self.cache_path)
        except OSError:
            pass

    def _needs_refresh(self, lat, lon, now):
        c = self._read_cache()
        return (c is None or c.get("lat") != lat or c.get("lon") != lon
                or is_stale(c["fetched_at"], now))

    def refresh_now(self, lat, lon, now, fetch=fetch_weather):
        """同步抓取并写缓存; 失败吞掉记日志、保留旧缓存。供后台线程与测试调用。"""
        try:
            raw = fetch(lat, lon)
            self._write_cache(now, lat, lon, raw)
        except Exception as e:
            print(f"[weather] refresh failed: {e}")

    def maybe_refresh(self, lat, lon, now, fetch=fetch_weather):
        """过期/坐标变更才刷新; 起 daemon 线程, 立即返回(防并发)。"""
        if not self._needs_refresh(lat, lon, now):
            return
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def _job():
            try:
                self.refresh_now(lat, lon, now, fetch)
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=_job, daemon=True).start()
