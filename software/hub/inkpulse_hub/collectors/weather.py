# inkpulse_hub/collectors/weather.py
import datetime as _dt

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
