# 天气 widget 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 屏上显示某地点当前天气(手绘图标+中文+温度)+ 今日高低 + 未来 3 天预报;地点由网页搜索城市设定;数据走 Open-Meteo,带缓存与失败降级,渲染不阻塞网络。

**Architecture:** 新增 `collectors/weather.py`:纯解析(`parse_weather`/`is_stale`)、薄网络层(`fetch_weather`/`geocode`,`urllib`)、带缓存的 `WeatherService`(stale-while-revalidate,后台线程刷新)。state 注入缓存数据并触发非阻塞刷新;`draw_weather` 纯绘制(7 类 Pillow 手绘图标);`/api/weather*` 端点 + `/config` 地点卡片。仿前几期 collector/widget/registry 模式。

**Tech Stack:** Python 3.11 · Pillow · FastAPI · pytest · 标准库 `urllib.request`/`json`/`threading`(无新依赖)。

设计来源:`docs/superpowers/specs/2026-06-14-inkpulse-weather-design.md`。所有路径相对 `software/hub/`。

---

## 关键约定(全任务通用,先读)

- **测试命令**:`.venv/bin/python -m pytest`(系统 python3 是 3.10 缺 cnlunar;venv 是 3.11)。
- **已知预存失败**:`tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`(WSL2 mDNS/网络,与本功能无关),全程忽略它;除它之外必须全绿。
- **绝不真连网络**:所有测试用 mock(`monkeypatch` 掉 `_get_json`/`geocode`/注入假 `fetch`)或纯解析样例 JSON。涉及坐标的测试必须用"新鲜缓存"或注入假 fetch,避免后台线程触发真实请求。
- **数据形状**(Open-Meteo `/v1/forecast` 响应,贯穿多任务):
  ```python
  SAMPLE_RAW = {
      "current": {"time": "2026-06-14T10:00", "temperature_2m": 23.4, "weather_code": 2},
      "daily": {"time": ["2026-06-14", "2026-06-15", "2026-06-16", "2026-06-17"],
                "weather_code": [2, 0, 3, 61],
                "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
                "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}
  }
  ```
- 每个任务结束 `commit`,运行目录 `software/hub/`。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `inkpulse_hub/collectors/weather.py` | 新增 | WMO 表 + `parse_weather`/`is_stale`(纯)+ `fetch_weather`/`geocode`(网络)+ `WeatherService`(缓存/SWR) |
| `inkpulse_hub/config.py` | 改 | `weather_cache` 字段 + sources;`weather_lat/lon/place` 进 RUNTIME_FIELDS |
| `inkpulse_hub/state.py` | 改 | `HubState` 持 `WeatherService`;注入 `weather`/`weather_place` + 非阻塞刷新 |
| `inkpulse_hub/render/widgets.py` | 改 | `draw_weather` + `_wx_icon`(7 类) |
| `inkpulse_hub/render/registry.py` | 改 | 注册 `weather` |
| `inkpulse_hub/server.py` | 改 | `/api/weather*` 端点 |
| `inkpulse_hub/web/config.html` | 改 | 天气地点卡片 |
| `tests/test_weather_parse.py` | 新增 | `parse_weather`/`is_stale`/WMO |
| `tests/test_weather_net.py` | 新增 | `fetch_weather`/`geocode`(mock) |
| `tests/test_weather_service.py` | 新增 | `WeatherService` 缓存/SWR |
| `tests/test_widget_weather.py` | 新增 | `draw_weather`/图标 |
| `tests/test_weather_api.py` | 新增 | `/api/weather*` |
| `tests/test_config.py` / `test_state_phase2.py` / `test_registry.py` | 改 | 各自追加断言 |

---

## Task 1: weather.py —— WMO 表 + parse_weather + is_stale(纯函数)

**Files:**
- Create: `inkpulse_hub/collectors/weather.py`
- Test: `tests/test_weather_parse.py`

- [ ] **Step 1: 写失败测试**

`tests/test_weather_parse.py`:

```python
from inkpulse_hub.collectors.weather import parse_weather, is_stale, WMO_CN, REFRESH_S

SAMPLE_RAW = {
    "current": {"time": "2026-06-14T10:00", "temperature_2m": 23.4, "weather_code": 2},
    "daily": {"time": ["2026-06-14", "2026-06-15", "2026-06-16", "2026-06-17"],
              "weather_code": [2, 0, 3, 61],
              "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
              "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}
}
# 2026-06-14 是周日; 故 06-15=明(周一), 06-16=周二, 06-17=周三
NOW = __import__("time").mktime((2026, 6, 14, 10, 0, 0, 0, 0, -1))


def test_parse_current_and_today():
    w = parse_weather(SAMPLE_RAW, NOW)
    assert w["cur_temp"] == 23.4 and w["cur_code"] == 2
    assert w["cur_cn"] == "多云" and w["cur_cat"] == "partly"
    assert w["today_hi"] == 26.0 and w["today_lo"] == 18.0


def test_parse_three_day_forecast():
    days = parse_weather(SAMPLE_RAW, NOW)["days"]
    assert len(days) == 3
    assert days[0] == {"label": "明", "cn": "晴", "cat": "sun", "hi": 27.0, "lo": 19.0}
    assert days[1]["label"] == "周二" and days[1]["cn"] == "阴" and days[1]["cat"] == "cloud"
    assert days[2]["label"] == "周三" and days[2]["cn"] == "小雨" and days[2]["cat"] == "rain"


def test_wmo_categories():
    assert WMO_CN[0] == ("晴", "sun")
    assert WMO_CN[45] == ("雾", "fog")
    assert WMO_CN[71] == ("小雪", "snow")
    assert WMO_CN[80] == ("阵雨", "rain")
    assert WMO_CN[95] == ("雷阵雨", "thunder")


def test_parse_unknown_code_falls_back():
    raw = {"current": {"temperature_2m": 10.0, "weather_code": 7},
           "daily": {"time": ["2026-06-14"], "weather_code": [7],
                     "temperature_2m_max": [11.0], "temperature_2m_min": [9.0]}}
    w = parse_weather(raw, NOW)
    assert w["cur_cn"] == "未知" and w["cur_cat"] == "cloud"
    assert w["days"] == []          # 无未来日


def test_is_stale_boundary():
    assert is_stale(1000.0, 1000.0 + REFRESH_S) is True       # 刚好到期
    assert is_stale(1000.0, 1000.0 + REFRESH_S - 1) is False  # 之内
    assert is_stale(1000.0, 1000.0 + REFRESH_S + 1) is True   # 之外
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_weather_parse.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'inkpulse_hub.collectors.weather'`

- [ ] **Step 3: 写实现**

`inkpulse_hub/collectors/weather.py`(本任务只放纯逻辑部分,网络/Service 在后续任务追加到同文件):

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_weather_parse.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/weather.py tests/test_weather_parse.py
git commit -m "feat(weather): WMO 中文表 + parse_weather + is_stale(纯逻辑)"
```

---

## Task 2: weather.py —— fetch_weather / geocode(网络层,mock 测)

**Files:**
- Modify: `inkpulse_hub/collectors/weather.py`(追加网络函数)
- Test: `tests/test_weather_net.py`

- [ ] **Step 1: 写失败测试**

`tests/test_weather_net.py`:

```python
import inkpulse_hub.collectors.weather as W


def test_geocode_parses_results(monkeypatch):
    sample = {"results": [
        {"name": "杭州", "latitude": 30.29, "longitude": 120.16,
         "country": "中国", "admin1": "浙江省"},
        {"name": "Hangzhou", "latitude": 30.0, "longitude": 120.0, "country": "中国"},
    ]}
    monkeypatch.setattr(W, "_get_json", lambda url: sample)
    out = W.geocode("杭州")
    assert out[0] == {"name": "杭州", "lat": 30.29, "lon": 120.16, "admin": "中国 浙江省"}
    assert out[1]["admin"] == "中国"


def test_geocode_empty_name_returns_empty(monkeypatch):
    monkeypatch.setattr(W, "_get_json", lambda url: {"results": []})
    assert W.geocode("   ") == []


def test_geocode_swallows_errors(monkeypatch):
    def boom(url):
        raise RuntimeError("network down")
    monkeypatch.setattr(W, "_get_json", boom)
    assert W.geocode("杭州") == []


def test_fetch_weather_passes_through(monkeypatch):
    captured = {}
    def fake(url):
        captured["url"] = url
        return {"ok": True}
    monkeypatch.setattr(W, "_get_json", fake)
    assert W.fetch_weather(30.29, 120.16) == {"ok": True}
    assert "latitude=30.29" in captured["url"] and "forecast_days=4" in captured["url"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_weather_net.py -v`
Expected: FAIL —— `AttributeError: module ... has no attribute '_get_json'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/collectors/weather.py` 顶部 import 区补:

```python
import json
import urllib.parse
import urllib.request
```

在文件中(`parse_weather` 之后)追加:

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_weather_net.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/weather.py tests/test_weather_net.py
git commit -m "feat(weather): fetch_weather/geocode 网络层(urllib, 失败降级)"
```

---

## Task 3: weather.py —— WeatherService(缓存 + SWR)

**Files:**
- Modify: `inkpulse_hub/collectors/weather.py`(追加 `WeatherService`)
- Test: `tests/test_weather_service.py`

- [ ] **Step 1: 写失败测试**

`tests/test_weather_service.py`:

```python
from inkpulse_hub.collectors.weather import WeatherService, REFRESH_S

SAMPLE_RAW = {
    "current": {"temperature_2m": 23.4, "weather_code": 2},
    "daily": {"time": ["2026-06-14", "2026-06-15", "2026-06-16", "2026-06-17"],
              "weather_code": [2, 0, 3, 61],
              "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
              "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}
}
NOW = 1749880000.0


def _svc(tmp_path):
    return WeatherService(str(tmp_path / "wcache.json"))


def test_current_none_when_no_cache(tmp_path):
    assert _svc(tmp_path).current(NOW) is None


def test_refresh_now_writes_cache_and_current_reads(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    w = s.current(NOW)
    assert w["cur_temp"] == 23.4 and w["status"] == "ok" and w["age_s"] == 0


def test_current_marks_stale(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    w = s.current(NOW + REFRESH_S + 10)
    assert w["status"] == "stale" and w["age_s"] == REFRESH_S + 10


def test_refresh_failure_keeps_old_cache(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    def boom(lat, lon):
        raise RuntimeError("down")
    s.refresh_now(30.29, 120.16, NOW + 5, fetch=boom)   # 不抛, 保留旧缓存
    assert s.current(NOW)["cur_temp"] == 23.4


def test_needs_refresh_logic(tmp_path):
    s = _svc(tmp_path)
    assert s._needs_refresh(30.29, 120.16, NOW) is True          # 无缓存
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    assert s._needs_refresh(30.29, 120.16, NOW + 10) is False    # 新鲜同坐标
    assert s._needs_refresh(30.29, 120.16, NOW + REFRESH_S + 1) is True   # 过期
    assert s._needs_refresh(99.0, 99.0, NOW + 10) is True        # 坐标变更


def test_clear_removes_cache(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    s.clear()
    assert s.current(NOW) is None


def test_maybe_refresh_noop_when_fresh(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    # 新鲜 -> 不应触发刷新(不起线程); 用会抛的 fetch 证明它没被调用
    def boom(lat, lon):
        raise AssertionError("should not fetch")
    s.maybe_refresh(30.29, 120.16, NOW + 10, fetch=boom)
    assert s.current(NOW)["cur_temp"] == 23.4
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_weather_service.py -v`
Expected: FAIL —— `ImportError: cannot import name 'WeatherService'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/collectors/weather.py` 顶部 import 区补:

```python
import os
import threading
```

文件末尾追加:

```python
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
        data = parse_weather(c["raw"], now)
        data["age_s"] = now - c["fetched_at"]
        data["status"] = "stale" if is_stale(c["fetched_at"], now) else "ok"
        return data

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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_weather_service.py -v`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/weather.py tests/test_weather_service.py
git commit -m "feat(weather): WeatherService 缓存 + stale-while-revalidate 后台刷新"
```

---

## Task 4: config.py —— weather 字段 + RUNTIME_FIELDS

**Files:**
- Modify: `inkpulse_hub/config.py`
- Test: `tests/test_config.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加:

```python
def test_weather_config_fields(tmp_path):
    from inkpulse_hub.config import Config, load_config, RUNTIME_FIELDS, save_runtime, load_runtime
    c = Config()
    assert c.weather_cache.endswith("inkpulse/weather_cache.json")
    assert c.weather_lat is None and c.weather_lon is None and c.weather_place == ""
    assert {"weather_lat", "weather_lon", "weather_place"} <= set(RUNTIME_FIELDS)
    # sources 覆盖 weather_cache
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  weather_cache: /tmp/w.json\n", encoding="utf-8")
    assert load_config(str(p)).weather_cache == "/tmp/w.json"
    # runtime 往返 weather_place
    c.weather_lat, c.weather_lon, c.weather_place = 30.29, 120.16, "杭州"
    rt = tmp_path / "rt.json"
    save_runtime(c, str(rt))
    c2 = Config()
    load_runtime(c2, str(rt))
    assert c2.weather_place == "杭州" and c2.weather_lat == 30.29
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_weather_config_fields -v`
Expected: FAIL —— `AttributeError: 'Config' object has no attribute 'weather_cache'`

- [ ] **Step 3: 实现**

`inkpulse_hub/config.py`:

1. 在 `Config` 数据类里、`env_history_store` 字段下一行加:
```python
    weather_cache: str = os.path.expanduser("~/inkpulse/weather_cache.json")
    weather_lat: Optional[float] = None
    weather_lon: Optional[float] = None
    weather_place: str = ""
```

2. 在 `load_config` 内、`cfg.env_history_store = ...` 那行下一行加:
```python
    cfg.weather_cache = os.path.expanduser(sources.get("weather_cache", cfg.weather_cache))
```

3. `RUNTIME_FIELDS` 列表追加三项(改成):
```python
RUNTIME_FIELDS = [
    "layout_name", "usage_budget_usd", "usage_window_token_limit", "refresh_periodic_s",
    "photo_pinned",
    "weather_lat", "weather_lon", "weather_place",
]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit -m "feat(config): weather_cache 字段 + weather_lat/lon/place 进 RUNTIME_FIELDS"
```

---

## Task 5: state.py —— 注入 weather + 非阻塞刷新

**Files:**
- Modify: `inkpulse_hub/state.py`
- Test: `tests/test_state_phase2.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_state_phase2.py` 末尾追加:

```python
def test_render_state_weather_none_without_location(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert state["weather"] is None and state["weather_place"] is None


def test_render_state_weather_from_fresh_cache(tmp_path):
    import json
    now = 1718000000.0
    raw = {"current": {"temperature_2m": 23.4, "weather_code": 2},
           "daily": {"time": ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13"],
                     "weather_code": [2, 0, 3, 61],
                     "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
                     "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}}
    wpath = tmp_path / "w.json"
    # 新鲜缓存(fetched_at == now) -> 不触发后台刷新, 无网络
    wpath.write_text(json.dumps({"fetched_at": now, "lat": 30.29, "lon": 120.16,
                                 "raw": raw}), encoding="utf-8")
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(wpath)
    cfg.weather_lat, cfg.weather_lon, cfg.weather_place = 30.29, 120.16, "杭州"
    st = HubState(cfg)
    state = st.build_render_state(now=now)
    assert state["weather"]["cur_temp"] == 23.4
    assert state["weather_place"] == "杭州"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py::test_render_state_weather_none_without_location -v`
Expected: FAIL —— `KeyError: 'weather'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py`:

1. import 区,在 `from .collectors.env_history import EnvHistoryStore` 下一行加:
```python
from .collectors.weather import WeatherService
```

2. `HubState.__init__`,在 `self.env_history = EnvHistoryStore(cfg.env_history_store)` 下一行加:
```python
        self.weather = WeatherService(cfg.weather_cache)
```

3. `build_render_state` 内,`now = now if now is not None else time.time()` 之后加:
```python
        lat, lon = self.cfg.weather_lat, self.cfg.weather_lon
        if lat is not None and lon is not None:
            self.weather.maybe_refresh(lat, lon, now)
            weather = self.weather.current(now)
            weather_place = self.cfg.weather_place or None
        else:
            weather, weather_place = None, None
```

4. 在返回 dict 里加两个键(放在 `"env_history": ...` 之后):
```python
            "weather": weather,
            "weather_place": weather_place,
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit -m "feat(state): 注入 weather/weather_place + 非阻塞 maybe_refresh"
```

---

## Task 6: widgets.py —— draw_weather + 7 类图标

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(末尾追加 `_wx_icon` + `draw_weather`)
- Test: `tests/test_widget_weather.py`

- [ ] **Step 1: 写失败测试**

`tests/test_widget_weather.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_weather, _wx_icon, Zone


def _img(w=300, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _weather():
    return {"cur_temp": 23.4, "cur_code": 2, "cur_cn": "多云", "cur_cat": "partly",
            "today_hi": 26.0, "today_lo": 18.0, "age_s": 720, "status": "ok",
            "days": [{"label": "明", "cn": "晴", "cat": "sun", "hi": 27.0, "lo": 19.0},
                     {"label": "周二", "cn": "阴", "cat": "cloud", "hi": 24.0, "lo": 17.0},
                     {"label": "周三", "cn": "小雨", "cat": "rain", "hi": 22.0, "lo": 16.0}]}


def test_draws_normal_weather():
    img, d = _img()
    draw_weather(d, Zone(0, 0, 300, 240), _weather(), "杭州")
    assert _has_black(img)


def test_all_seven_icons_draw():
    for cat in ["sun", "partly", "cloud", "fog", "rain", "snow", "thunder"]:
        img, d = _img(60, 60)
        _wx_icon(d, 30, 30, 18, cat)
        assert _has_black(img), f"{cat} 没画出黑像素"


def test_no_location_hint():
    img, d = _img()
    draw_weather(d, Zone(0, 0, 300, 240), None, None)   # place=None -> 未设置
    assert _has_black(img)


def test_loading_hint():
    img, d = _img()
    draw_weather(d, Zone(0, 0, 300, 240), None, "杭州")  # 有 place 无 weather -> 加载中
    assert _has_black(img)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_weather.py -v`
Expected: FAIL —— `ImportError: cannot import name 'draw_weather'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加:

```python
def _wx_icon(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, cat: str) -> None:
    """7 类天气图标, 纯黑 Pillow 手绘(字体无关)。cx,cy=中心, r=半径基准。"""
    def cloud(ox, oy, cr):
        # 三个叠圆 + 平底, 形成一朵云
        d.ellipse((ox - cr, oy - cr // 2, ox + cr, oy + cr // 2), outline=BLACK, width=2)
        d.ellipse((ox - cr * 2, oy - cr // 3, ox, oy + cr // 2), outline=BLACK, width=2)
        d.ellipse((ox, oy - cr // 3, ox + cr * 2, oy + cr // 2), outline=BLACK, width=2)

    if cat == "sun":
        d.ellipse((cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2), fill=BLACK)
        for i in range(8):
            import math
            a = i * math.pi / 4
            x0 = cx + int((r // 2 + 2) * math.cos(a))
            y0 = cy + int((r // 2 + 2) * math.sin(a))
            x1 = cx + int(r * math.cos(a))
            y1 = cy + int(r * math.sin(a))
            d.line((x0, y0, x1, y1), fill=BLACK, width=2)
    elif cat == "partly":
        d.ellipse((cx - r, cy - r, cx - r + r, cy), fill=BLACK)      # 左上小太阳
        cloud(cx, cy + r // 4, r // 2)
    elif cat == "cloud":
        cloud(cx, cy, r // 2)
    elif cat == "fog":
        cloud(cx, cy - r // 3, r // 2)
        for k in range(3):
            yy = cy + r // 3 + k * 5
            d.line((cx - r, yy, cx + r, yy), fill=BLACK, width=2)
    elif cat == "rain":
        cloud(cx, cy - r // 3, r // 2)
        for k in range(4):
            xx = cx - r + k * (r * 2 // 4) + 4
            d.line((xx, cy + r // 3, xx - 4, cy + r), fill=BLACK, width=2)
    elif cat == "snow":
        cloud(cx, cy - r // 3, r // 2)
        for k in range(3):
            xx = cx - r // 2 + k * (r // 2)
            d.ellipse((xx - 2, cy + r // 2 - 2, xx + 2, cy + r // 2 + 2), fill=BLACK)
    elif cat == "thunder":
        cloud(cx, cy - r // 3, r // 2)
        d.line((cx, cy + r // 4, cx - r // 3, cy + r // 2), fill=BLACK, width=2)
        d.line((cx - r // 3, cy + r // 2, cx + r // 4, cy + r // 2), fill=BLACK, width=2)
        d.line((cx + r // 4, cy + r // 2, cx - r // 6, cy + r), fill=BLACK, width=2)
    else:
        cloud(cx, cy, r // 2)


def draw_weather(d: ImageDraw.ImageDraw, z: Zone, weather, place) -> None:
    """天气 widget。三态由 (place, weather) 区分; 纯黑无红。
    place=None -> 未设置地点; place 有值且 weather=None -> 加载中; weather 有值 -> 正常。"""
    cy = _title_bar(d, z, f"天气 · {place}" if place else "天气")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    if place is None:
        _center_text(d, body, "未设置地点 · 去网页添加", _font(16), BLACK)
        return
    if weather is None:
        _center_text(d, body, "加载中…", _font(18), BLACK)
        return
    # 当前块: 大图标 + 中文词 + 当前温度大字
    _wx_icon(d, body.x + 26, body.y + 24, 18, weather["cur_cat"])
    d.text((body.x + 52, body.y + 4), weather["cur_cn"], fill=BLACK, font=_font(18))
    big = f"{weather['cur_temp']:.0f}°C"
    d.text((body.x + 52, body.y + 26), big, fill=BLACK, font=_font(26))
    d.text((body.x + 4, body.y + 52),
           f"今日 {weather['today_hi']:.0f}° / {weather['today_lo']:.0f}°",
           fill=BLACK, font=_font(15))
    # 分隔线
    sep_y = body.y + 74
    d.line((body.x + 4, sep_y, body.x + body.w - 4, sep_y), fill=BLACK, width=1)
    # 未来 3 天
    f = _font(15)
    for i, day in enumerate(weather.get("days", [])[:3]):
        ry = sep_y + 6 + i * 22
        d.text((body.x + 4, ry), day["label"], fill=BLACK, font=f)
        _wx_icon(d, body.x + 52, ry + 8, 8, day["cat"])
        d.text((body.x + 72, ry), f"{day['hi']:.0f}° / {day['lo']:.0f}°",
               fill=BLACK, font=f)
    # 缓存新鲜度(右下)
    mins = int(weather.get("age_s", 0)) // 60
    age = f"更新于 {mins} 分钟前"
    aw = d.textlength(age, font=_font(12))
    d.text((body.x + body.w - aw - 4, body.y + body.h - 14), age,
           fill=BLACK, font=_font(12))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_weather.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_weather.py
git commit -m "feat(widget): draw_weather + 7 类手绘天气图标(三态/纯黑)"
```

---

## Task 7: registry.py —— 注册 weather

**Files:**
- Modify: `inkpulse_hub/render/registry.py`
- Test: `tests/test_registry.py`(`_state()` 补字段 + 断言)

- [ ] **Step 1: 改测试(先让其失败)**

`tests/test_registry.py` 的 `_state()` 返回 dict 内追加两键:

```python
        "weather": {"cur_temp": 23.4, "cur_code": 2, "cur_cn": "多云", "cur_cat": "partly",
                    "today_hi": 26.0, "today_lo": 18.0, "age_s": 600, "status": "ok",
                    "days": [{"label": "明", "cn": "晴", "cat": "sun", "hi": 27.0, "lo": 19.0}]},
        "weather_place": "杭州",
```

把 `test_existing_widgets_registered` 的 `expected` 集合加入 `"weather"`:

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist", "habits", "temp_trend", "weather"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL —— `weather` 不在 REGISTRY

- [ ] **Step 3: 实现**

`inkpulse_hub/render/registry.py`:

1. 在 `_temp_trend` 适配器之后加:
```python
def _weather(d, img, z, state, cfg, p):
    W.draw_weather(d, z, state.get("weather"), state.get("weather_place"))
```

2. `REGISTRY` 字典里(`"temp_trend": ...` 之后)加一条:
```python
    "weather":       WidgetSpec("weather", "天气", _weather, {"cols": 3, "rows": 3}),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit -m "feat(registry): 注册 weather widget 与适配器"
```

---

## Task 8: server.py —— /api/weather* 端点

**Files:**
- Modify: `inkpulse_hub/server.py`
- Test: `tests/test_weather_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_weather_api.py`:

```python
from fastapi.testclient import TestClient
import inkpulse_hub.collectors.weather as W
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 weather_cache=str(tmp_path / "w.json"),
                 runtime_store=str(tmp_path / "rt.json"))
    return create_app(cfg)


def test_search_proxies_geocode(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "geocode",
                        lambda q: [{"name": "杭州", "lat": 30.29, "lon": 120.16, "admin": "中国 浙江省"}])
    r = TestClient(_app(tmp_path)).get("/api/weather/search", params={"q": "杭州"})
    assert r.status_code == 200 and r.json()[0]["name"] == "杭州"


def test_set_and_get_location(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    assert c.post("/api/weather/location",
                  json={"lat": 30.29, "lon": 120.16, "name": "杭州"}).status_code == 200
    assert app.state.cfg.weather_place == "杭州" and app.state.cfg.weather_lat == 30.29
    got = c.get("/api/weather").json()
    assert got["place"] == "杭州" and got["lat"] == 30.29 and got["weather"] is None


def test_set_location_missing_field_400(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.post("/api/weather/location", json={"lat": 30.29}).status_code == 400


def test_delete_location(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    c.post("/api/weather/location", json={"lat": 30.29, "lon": 120.16, "name": "杭州"})
    assert c.delete("/api/weather/location").status_code == 200
    assert app.state.cfg.weather_place == "" and app.state.cfg.weather_lat is None
    assert c.get("/api/weather").json()["weather"] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_weather_api.py -v`
Expected: FAIL —— `/api/weather/search` 返回 404

- [ ] **Step 3: 实现**

`inkpulse_hub/server.py`:

1. 顶部 import 区(`from .collectors.habits import week_dates` 那行附近)加:
```python
from .collectors import weather as weather_mod
```
(`import time`、`save_runtime`、`JSONResponse`、`Request` 均已在顶部,复用。)

2. 在 habits 端点之后、`# ---- 配置中心` 注释之前,插入:
```python
    @app.get("/api/weather/search")
    def api_weather_search(q: str = ""):
        return weather_mod.geocode(q)

    @app.post("/api/weather/location")
    async def api_weather_set_location(request: Request):
        data = await request.json()
        lat, lon, name = data.get("lat"), data.get("lon"), data.get("name")
        if lat is None or lon is None or not (name or "").strip():
            return JSONResponse({"error": "lat/lon/name required"}, status_code=400)
        cfg.weather_lat, cfg.weather_lon, cfg.weather_place = float(lat), float(lon), name.strip()
        save_runtime(cfg, cfg.runtime_store)
        state.weather.clear()
        return {"ok": True}

    @app.delete("/api/weather/location")
    def api_weather_del_location():
        cfg.weather_lat, cfg.weather_lon, cfg.weather_place = None, None, ""
        save_runtime(cfg, cfg.runtime_store)
        state.weather.clear()
        return {"ok": True}

    @app.get("/api/weather")
    def api_weather_get():
        w = None
        if cfg.weather_lat is not None and cfg.weather_lon is not None:
            w = state.weather.current(time.time())
        return {"place": cfg.weather_place, "lat": cfg.weather_lat,
                "lon": cfg.weather_lon, "weather": w}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_weather_api.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_weather_api.py
git commit -m "feat(api): /api/weather 搜索/设/删地点 + 当前天气"
```

---

## Task 9: config.html —— 天气地点卡片

**Files:**
- Modify: `inkpulse_hub/web/config.html`
- 手动验证(纯前端,无单测)

- [ ] **Step 1: 加卡片**

在习惯打卡卡片之后、`#wrap` 收尾 `</div>`(`<script>` 之前)插入:

```html
  <div class="card">
    <h2>天气地点</h2>
    <div id="weatherLoc" class="hint">加载中…</div>
    <div class="row" style="margin-top:12px">
      <input id="weatherQuery" placeholder="搜索城市,如 杭州" onkeydown="if(event.key==='Enter')searchWeather()">
      <button onclick="searchWeather()">搜索</button>
    </div>
    <div id="weatherResults"></div>
  </div>
```

- [ ] **Step 2: load() 里挂载**

在 `load()` 函数体末尾(现有 `loadHabits();` 那行)下一行加:

```javascript
  loadWeatherLoc();
```

- [ ] **Step 3: 加 JS 函数**

在 `<script>` 块末尾(`</script>` 之前)加:

```javascript
async function loadWeatherLoc(){
  const w=await (await fetch('/api/weather')).json();
  const box=document.getElementById('weatherLoc');
  if(w.place){
    box.innerHTML=`<div class="row"><span style="flex:1">当前:${esc(w.place)}</span><button class="ghost" onclick="clearWeather()">清除</button></div>`;
  }else{
    box.innerHTML='<div class="hint">未设置地点</div>';
  }
}
async function searchWeather(){
  const q=document.getElementById('weatherQuery').value.trim();if(!q)return;
  const list=await (await fetch('/api/weather/search?q='+encodeURIComponent(q))).json();
  const box=document.getElementById('weatherResults');box.innerHTML='';
  if(!list.length){box.innerHTML='<div class="hint">没找到</div>';return;}
  list.forEach(r=>box.insertAdjacentHTML('beforeend',
    `<div class="row"><span style="flex:1">${esc(r.name)} · ${esc(r.admin||'')}</span><button onclick='pickWeather(${r.lat},${r.lon},${JSON.stringify(r.name)})'>选择</button></div>`));
}
async function pickWeather(lat,lon,name){
  await fetch('/api/weather/location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lat,lon,name})});
  document.getElementById('weatherResults').innerHTML='';
  document.getElementById('weatherQuery').value='';
  loadWeatherLoc();setTimeout(refreshPreview,300);
}
async function clearWeather(){
  await fetch('/api/weather/location',{method:'DELETE'});loadWeatherLoc();setTimeout(refreshPreview,300);
}
```

- [ ] **Step 4: 手动验证**

```bash
# 用 venv python 起服务(参考 tests/test_weather_api.py 的 create_app), 或停掉 systemd 服务后 ./run.sh
# 浏览器开 /config
```
检查:
1. 「天气地点」卡片出现,显示"未设置地点"。
2. 搜"杭州"→ 出候选列表(需联网/代理);点"选择"→ 卡片变"当前:杭州",预览刷新。
3. "清除"→ 回到"未设置地点"。

> 注:搜索要真连 Open-Meteo 地理编码,确保代理在跑。

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/web/config.html
git commit -m "feat(web): /config 天气地点卡片(搜城市/选定/清除)"
```

---

## Task 10: 全量验证 + 预览 + spec 验收

**Files:** 无改动(纯验证)

- [ ] **Step 1: 跑全部测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全绿,唯一允许失败是预存的 `tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`。确认**没有任何测试真连网络**(运行应在数秒内完成)。

- [ ] **Step 2: 渲染 weather widget 预览**

```bash
.venv/bin/python -c "
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_weather, Zone
w={'cur_temp':23.4,'cur_code':2,'cur_cn':'多云','cur_cat':'partly','today_hi':26.0,'today_lo':18.0,
   'age_s':720,'status':'ok',
   'days':[{'label':'明','cn':'晴','cat':'sun','hi':27.0,'lo':19.0},
           {'label':'周二','cn':'阴','cat':'cloud','hi':24.0,'lo':17.0},
           {'label':'周三','cn':'小雨','cat':'rain','hi':22.0,'lo':16.0}]}
img=Image.new('RGB',(300,240),(255,255,255)); d=ImageDraw.Draw(img); d.fontmode='1'
draw_weather(d, Zone(0,0,300,240), w, '杭州'); img.save('/tmp/weather_preview.png'); print('saved')
"
```
打开 `/tmp/weather_preview.png` 目视:标题「天气 · 杭州」、当前块(图标+多云+23°C)、今日高低、3 天预报(各带小图标)、右下"更新于 12 分钟前"。

- [ ] **Step 3: 对照 spec 第 12 节验收逐条打勾**

1. 选定地点后屏上显示当前天气+今日高低+3 天 —— Task 5/6/7/8/9。
2. 网络后台抓取不阻塞渲染;失败用旧缓存+新鲜度 —— Task 3/5(`current` 不触网,`maybe_refresh` 起线程)。
3. 未设地点/加载中/坏缓存/无结果不崩 —— Task 3/6/8。
4. 全部测试通过且不真连网络 —— Step 1。

- [ ] **Step 4: 归档提示**

合并后可把本期 spec+plan 移入 `docs/superpowers/archive/`(沿用 `chore: 归档…`)。仅提示。

---

## 自检(写计划后已核对)

- **Spec 覆盖**:§5.1 WMO 表 → T1;§5.2 fetch/geocode → T2,parse → T1;§5.3 Service/SWR/clear → T3;§4 config 字段+RUNTIME → T4;§4 state 注入+非阻塞刷新 → T5;§6 widget 三态+7 图标 → T6;§4 registry → T7;§7 API(search/POST/DELETE/GET,缺字段 400)→ T8;§8 网页卡片 → T9;§9 错误处理(无坐标/加载中/失败留旧缓存/坏缓存/无结果/防并发)→ T3/T5/T6/T8;§10 测试(均 mock 不真连)→ 各任务;§11 无新依赖 → 确认;§12 验收 → T10。无遗漏。
- **签名一致**:`parse_weather(raw,now)`、`is_stale(fetched_at,now)`、`fetch_weather(lat,lon)`、`geocode(name)`、`WeatherService.current(now)/maybe_refresh(lat,lon,now,fetch=)/refresh_now(.../fetch=)/_needs_refresh/clear`、`draw_weather(d,z,weather,place)`、`_wx_icon(d,cx,cy,r,cat)`、state 键 `weather`/`weather_place` —— 全计划统一。`maybe_refresh` 拆出 `_needs_refresh`+`refresh_now` 是对 spec §5.3 的可测性细化(纯决策 + 同步抓取分离,线程只是包装),已在 T3 注明。
- **无占位符**:每个改码步骤均给出完整代码与确切路径/命令/预期输出。
- **网络隔离**:所有测试 mock `_get_json`/`geocode` 或注入假 `fetch` 或用新鲜缓存;state/api 测试不触发后台线程真连。T10 Step1 显式核对运行时长。
```
