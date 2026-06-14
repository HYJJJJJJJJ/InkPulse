# 日程 widget 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本地录入的近期日程板:网页 `/config` 加日程(标题+日期+可选时间),墨水屏 `agenda` widget 按时间排出近期日程(今天/明天/日期标签 + 时间/全天 + 标题),过期自动隐去。

**Architecture:** 新增 `EventStore`(`~/inkpulse/events.json`,仿 TodoStore)做增删/排序/`upcoming` 过滤;`build_render_state` 注入近期日程;纯函数 `draw_agenda` 绘制;`/api/events*` + `/config` 日程卡片。无联网、无新依赖。

**Tech Stack:** Python 3.11 · Pillow · FastAPI · pytest · 标准库 `datetime`/`uuid`/`json`。

设计来源:`docs/superpowers/specs/2026-06-14-inkpulse-agenda-design.md`。所有路径相对 `software/hub/`。

---

## 关键约定(全任务通用,先读)

- **测试命令**:`.venv/bin/python -m pytest`(系统 python3 是 3.10 缺 cnlunar;venv 是 3.11)。
- **已知预存失败**:`tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`(WSL2 mDNS/网络),忽略它;除它之外必须全绿。
- **存储格式**(`events.json`):裸 JSON 列表 `[{"id","title","date","time"}, ...]`(`date`="YYYY-MM-DD",`time`="HH:MM" 或 ""=全天)。`id=uuid4().hex[:8]`。坏/缺文件 → `[]`,不抛异常。
- **排序键**:`(date, time or "00:00")` —— 全天(`time=""`)排当天定时事件之前。
- **过期判定**:`upcoming` 只留 `date >= 今天`(今天由 `now` 经 `date.fromtimestamp(now).isoformat()` 求)。
- 每个任务结束 `commit`,运行目录 `software/hub/`。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `inkpulse_hub/collectors/events.py` | 新增 | `EventStore` + `AGENDA_LIMIT` |
| `inkpulse_hub/config.py` | 改 | `events_store` 字段 + sources 覆盖 |
| `inkpulse_hub/state.py` | 改 | `HubState` 持 `EventStore`;注入 `events` |
| `inkpulse_hub/render/widgets.py` | 改 | 新增 `draw_agenda` |
| `inkpulse_hub/render/registry.py` | 改 | 注册 `agenda` |
| `inkpulse_hub/server.py` | 改 | `/api/events*` 端点 |
| `inkpulse_hub/web/config.html` | 改 | 日程卡片 |
| `tests/test_events.py` | 新增 | `EventStore` 单测 |
| `tests/test_events_api.py` | 新增 | API 契约 |
| `tests/test_widget_agenda.py` | 新增 | `draw_agenda` |
| `tests/test_config.py` / `test_state_phase2.py` / `test_registry.py` | 改 | 各自追加断言 |

---

## Task 1: EventStore —— 存储 + add/delete/list/upcoming

**Files:**
- Create: `inkpulse_hub/collectors/events.py`
- Test: `tests/test_events.py`

- [ ] **Step 1: 写失败测试**

`tests/test_events.py`:

```python
from inkpulse_hub.collectors.events import EventStore, AGENDA_LIMIT
import time


def _now(y, m, d):
    return time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))


def test_add_list_delete(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    e = s.add("团队周会", "2026-06-14", "14:30")
    assert e["title"] == "团队周会" and e["date"] == "2026-06-14" and e["time"] == "14:30"
    assert len(e["id"]) == 8
    assert [x["title"] for x in s.list()] == ["团队周会"]
    s.delete(e["id"])
    assert s.list() == []


def test_list_sorted_allday_before_timed(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    s.add("定时", "2026-06-14", "09:00")
    s.add("全天", "2026-06-14", "")        # 同日全天 -> 排在 09:00 之前
    s.add("次日", "2026-06-15", "08:00")
    assert [x["title"] for x in s.list()] == ["全天", "定时", "次日"]


def test_upcoming_filters_past(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    s.add("昨天", "2026-06-13", "10:00")
    s.add("今天", "2026-06-14", "10:00")
    s.add("明天", "2026-06-15", "10:00")
    up = s.upcoming(_now(2026, 6, 14), 10)
    assert [x["title"] for x in up] == ["今天", "明天"]      # 昨天被过滤


def test_upcoming_respects_limit(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    for i in range(5):
        s.add(f"e{i}", "2026-06-20", f"0{i}:00")
    assert len(s.upcoming(_now(2026, 6, 14), 3)) == 3


def test_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "events.json"
    p.write_text("{not a list", encoding="utf-8")
    assert EventStore(str(p)).list() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "events.json")
    EventStore(path).add("持久", "2026-06-14", "")
    assert [x["title"] for x in EventStore(path).list()] == ["持久"]


def test_agenda_limit_is_int():
    assert isinstance(AGENDA_LIMIT, int) and AGENDA_LIMIT > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_events.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'inkpulse_hub.collectors.events'`

- [ ] **Step 3: 写实现**

`inkpulse_hub/collectors/events.py`:

```python
# inkpulse_hub/collectors/events.py
import json
import os
import uuid
import datetime as _dt

AGENDA_LIMIT = 8   # state 注入上限(widget 再按高度截断)


class EventStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError
            return data
        except (json.JSONDecodeError, ValueError, OSError):
            return []

    def _write(self, items: list) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _key(e):
        return (e.get("date", ""), e.get("time") or "00:00")

    def list(self) -> list:
        return sorted(self._read(), key=self._key)

    def add(self, title: str, date: str, time: str = "") -> dict:
        items = self._read()
        e = {"id": uuid.uuid4().hex[:8], "title": title, "date": date, "time": time or ""}
        items.append(e)
        self._write(items)
        return e

    def delete(self, eid: str) -> None:
        self._write([e for e in self._read() if e.get("id") != eid])

    def upcoming(self, now: float, limit: int) -> list:
        today = _dt.date.fromtimestamp(now).isoformat()
        future = [e for e in self.list() if e.get("date", "") >= today]
        return future[:limit]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_events.py -v`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/events.py tests/test_events.py
git commit -m "feat(events): EventStore 存储 + add/delete/list/upcoming"
```

---

## Task 2: config.py —— 新增 events_store 字段

**Files:**
- Modify: `inkpulse_hub/config.py`
- Test: `tests/test_config.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加:

```python
def test_events_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().events_store.endswith("inkpulse/events.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  events_store: /tmp/ev.json\n", encoding="utf-8")
    assert load_config(str(p)).events_store == "/tmp/ev.json"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_events_store_default_and_override -v`
Expected: FAIL —— `AttributeError: 'Config' object has no attribute 'events_store'`

- [ ] **Step 3: 实现**

`inkpulse_hub/config.py`:在 `Config` 数据类里、`weather_place` 字段下一行加:

```python
    events_store: str = os.path.expanduser("~/inkpulse/events.json")
```

在 `load_config` 内、`cfg.weather_cache = ...` 那行下一行加:

```python
    cfg.events_store = os.path.expanduser(sources.get("events_store", cfg.events_store))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit -m "feat(config): 新增 events_store 路径字段与 sources 覆盖"
```

---

## Task 3: state.py —— 注入 events

**Files:**
- Modify: `inkpulse_hub/state.py`
- Test: `tests/test_state_phase2.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_state_phase2.py` 末尾追加:

```python
def test_render_state_has_events(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "events" in state and isinstance(state["events"], list)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py::test_render_state_has_events -v`
Expected: FAIL —— `KeyError: 'events'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py`:

1. import 区,在 `from .collectors.weather import WeatherService` 下一行加:
```python
from .collectors.events import EventStore, AGENDA_LIMIT
```

2. `HubState.__init__`,在 `self.weather = WeatherService(cfg.weather_cache)` 下一行加:
```python
        self.events = EventStore(cfg.events_store)
```

3. `build_render_state` 的返回 dict 里加一个键(放在 `"weather_place": ...,` 之后即可,不动其它键):
```python
            "events": self.events.upcoming(now, AGENDA_LIMIT),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit -m "feat(state): build_render_state 注入 events(upcoming)"
```

---

## Task 4: draw_agenda widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(末尾新增函数)
- Test: `tests/test_widget_agenda.py`

- [ ] **Step 1: 写失败测试**

`tests/test_widget_agenda.py`:

```python
import time
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_agenda, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


NOW = time.mktime((2026, 6, 14, 12, 0, 0, 0, 0, -1))   # 2026-06-14 周日


def test_draws_with_data():
    img, d = _img()
    events = [{"title": "团队周会", "date": "2026-06-14", "time": "14:30"},
              {"title": "交报告", "date": "2026-06-14", "time": ""},
              {"title": "看演出", "date": "2026-06-18", "time": "19:00"}]
    draw_agenda(d, Zone(0, 0, 400, 240), events, NOW)
    assert _has_black(img)


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_agenda(d, Zone(0, 0, 400, 240), [], NOW)
    assert _has_black(img)   # 提示文字也是黑像素; 关键不抛异常


def test_today_tomorrow_and_allday_labels_no_crash():
    img, d = _img()
    events = [{"title": "今日事", "date": "2026-06-14", "time": "08:00"},   # 今天
              {"title": "明日事", "date": "2026-06-15", "time": ""},        # 明天 全天
              {"title": "后续事", "date": "2026-06-20", "time": "10:00"}]   # 6/20
    draw_agenda(d, Zone(0, 0, 400, 240), events, NOW)
    assert _has_black(img)


def test_long_title_truncated_no_crash():
    img, d = _img(300, 120)
    events = [{"title": "这是一个非常非常非常长的日程标题需要被截断" * 3,
               "date": "2026-06-14", "time": "09:00"}]
    draw_agenda(d, Zone(0, 0, 300, 120), events, NOW)
    assert _has_black(img)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_agenda.py -v`
Expected: FAIL —— `ImportError: cannot import name 'draw_agenda'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加(复用文件内已有的 `_title_bar`/`_center_text`/`_font`/`Zone`/`BLACK`,以及模块级 `_WEEKDAYS`;注:`widgets.py` 顶部已 `import` 所需,若 `datetime` 未导入则在文件顶部加 `import datetime as _dt`):

```python
def draw_agenda(d: ImageDraw.ImageDraw, z: Zone, events, now) -> None:
    """近期日程列表。events=[{"title","date","time"}, ...] 已升序; now 用于今天/明天标签。纯黑。"""
    import datetime as _dt
    cy = _title_bar(d, z, "日程")
    if not events:
        _center_text(d, z, "无日程 · 去网页添加", _font(18), BLACK)
        return
    today = _dt.date.fromtimestamp(now)
    f = _font(18)
    row_h = 30
    max_rows = max(1, (z.y + z.h - cy - 4) // row_h)
    for i, e in enumerate(events[:max_rows]):
        y = cy + i * row_h
        # 相对日标签
        try:
            ed = _dt.date.fromisoformat(e.get("date", ""))
            delta = (ed - today).days
            if delta == 0:
                day = "今天"
            elif delta == 1:
                day = "明天"
            else:
                day = f"{ed.month}/{ed.day} 周{'一二三四五六日'[ed.weekday()]}"
        except ValueError:
            day = e.get("date", "")
        tm = e.get("time") or "全天"
        prefix = f"{day} {tm} "
        d.text((z.x + 6, y), prefix, fill=BLACK, font=f)
        # 标题: 在前缀之后, 按剩余宽度截断
        tx = z.x + 6 + int(d.textlength(prefix, font=f))
        title = e.get("title", "")
        avail = z.x + z.w - tx - 6
        while title and d.textlength(title, font=f) > avail:
            title = title[:-1]
        d.text((tx, y), title, fill=BLACK, font=f)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_agenda.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_agenda.py
git commit -m "feat(widget): draw_agenda 近期日程列表(相对日/时间/全天/截断)"
```

---

## Task 5: registry —— 注册 agenda widget

**Files:**
- Modify: `inkpulse_hub/render/registry.py`
- Test: `tests/test_registry.py`(`_state()` 补字段 + 断言)

- [ ] **Step 1: 改测试(先让其失败)**

`tests/test_registry.py` 的 `_state()` 返回 dict 内追加一键:

```python
        "events": [{"title": "团队周会", "date": "2026-06-14", "time": "14:30"}],
```

把 `test_existing_widgets_registered` 的 `expected` 集合加入 `"agenda"`:

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist", "habits", "temp_trend", "weather", "agenda"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL —— `agenda` 不在 REGISTRY

- [ ] **Step 3: 实现**

`inkpulse_hub/render/registry.py`:

1. 在 `_weather` 适配器之后加:
```python
def _agenda(d, img, z, state, cfg, p):
    W.draw_agenda(d, z, state.get("events", []), state.get("now"))
```

2. `REGISTRY` 字典里(`"weather": ...` 之后)加一条:
```python
    "agenda":        WidgetSpec("agenda", "日程", _agenda, {"cols": 4, "rows": 3}),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit -m "feat(registry): 注册 agenda widget 与适配器"
```

---

## Task 6: server —— /api/events 系列端点

**Files:**
- Modify: `inkpulse_hub/server.py`
- Test: `tests/test_events_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_events_api.py`:

```python
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 events_store=str(tmp_path / "events.json"))
    return TestClient(create_app(cfg))


def test_get_empty(tmp_path):
    assert _client(tmp_path).get("/api/events").json() == []


def test_add_and_get(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/events", json={"title": "团队周会", "date": "2026-06-14", "time": "14:30"})
    assert r.status_code == 200 and r.json()["id"]
    got = c.get("/api/events").json()
    assert [e["title"] for e in got] == ["团队周会"]


def test_add_rejects_blank_title(tmp_path):
    assert _client(tmp_path).post("/api/events",
        json={"title": "  ", "date": "2026-06-14", "time": ""}).status_code == 400


def test_add_rejects_bad_date(tmp_path):
    assert _client(tmp_path).post("/api/events",
        json={"title": "x", "date": "2026/06/14", "time": ""}).status_code == 400


def test_add_rejects_bad_time(tmp_path):
    assert _client(tmp_path).post("/api/events",
        json={"title": "x", "date": "2026-06-14", "time": "9点"}).status_code == 400


def test_add_allday_ok(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/events",
        json={"title": "全天事", "date": "2026-06-14", "time": ""}).status_code == 200


def test_delete(tmp_path):
    c = _client(tmp_path)
    eid = c.post("/api/events", json={"title": "x", "date": "2026-06-14", "time": ""}).json()["id"]
    assert c.delete(f"/api/events/{eid}").status_code == 200
    assert c.get("/api/events").json() == []
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_events_api.py -v`
Expected: FAIL —— GET `/api/events` 返回 404

- [ ] **Step 3: 实现**

`inkpulse_hub/server.py`:

1. 顶部 import 区(`import time` 附近)加:
```python
import datetime as _dt
```

2. 在 weather 端点之后、`# ---- 配置中心` 注释之前,插入:
```python
    def _valid_event(title, date, time):
        if not (title or "").strip():
            return False
        try:
            _dt.date.fromisoformat(date)
        except (TypeError, ValueError):
            return False
        if time:
            try:
                _dt.time.fromisoformat(time)
            except (TypeError, ValueError):
                return False
        return True

    @app.get("/api/events")
    def api_events_list():
        return state.events.list()

    @app.post("/api/events")
    async def api_events_add(request: Request):
        data = await request.json()
        title, date, time = data.get("title", ""), data.get("date", ""), data.get("time", "") or ""
        if not _valid_event(title, date, time):
            return JSONResponse({"error": "invalid event"}, status_code=400)
        return state.events.add(title.strip(), date, time)

    @app.delete("/api/events/{eid}")
    def api_events_delete(eid: str):
        state.events.delete(eid)
        return {"ok": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_events_api.py -v`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_events_api.py
git commit -m "feat(api): /api/events 列表/增(校验)/删"
```

---

## Task 7: config.html —— 日程卡片

**Files:**
- Modify: `inkpulse_hub/web/config.html`
- 手动验证(纯前端,无单测)

- [ ] **Step 1: 加卡片**

在天气地点卡片之后、`#wrap` 收尾 `</div>`(`<script>` 之前)插入:

```html
  <div class="card">
    <h2>日程</h2>
    <div id="events"></div>
    <div class="row" style="margin-top:12px">
      <input id="evTitle" placeholder="日程标题..." style="flex:2">
      <input id="evDate" type="date" style="flex:1">
      <input id="evTime" type="time" style="flex:1">
      <button onclick="addEvent()">添加</button>
    </div>
  </div>
```

- [ ] **Step 2: load() 里挂载**

在 `load()` 函数体末尾(现有 `loadWeatherLoc();` 那行)下一行加:

```javascript
  loadEvents();
```

- [ ] **Step 3: 加 JS 函数**

在 `<script>` 块末尾(`</script>` 之前)加:

```javascript
async function loadEvents(){
  const list=await (await fetch('/api/events')).json();
  const box=document.getElementById('events');box.innerHTML='';
  if(!list.length){box.innerHTML='<div class="hint">还没有日程</div>';return;}
  list.forEach(e=>box.insertAdjacentHTML('beforeend',
    `<div class="row"><span style="flex:1">${esc(e.date)} ${esc(e.time||'全天')} · ${esc(e.title)}</span><button class="ghost" onclick="delEvent('${e.id}')">×</button></div>`));
}
async function addEvent(){
  const t=document.getElementById('evTitle'), dt=document.getElementById('evDate'), tm=document.getElementById('evTime');
  const title=t.value.trim(), date=dt.value, time=tm.value;
  if(!title||!date){alert('请填标题和日期');return;}
  const r=await fetch('/api/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,date,time})});
  if(!r.ok){alert('添加失败(检查日期/时间格式)');return;}
  t.value='';tm.value='';loadEvents();setTimeout(refreshPreview,300);
}
async function delEvent(id){
  await fetch('/api/events/'+id,{method:'DELETE'});loadEvents();setTimeout(refreshPreview,300);
}
```

- [ ] **Step 4: 手动验证**

```bash
# 用 venv python 起临时实例(参考 tests/test_events_api.py 的 create_app), 或停 systemd 服务后 ./run.sh
# 浏览器开 /config
```
检查:
1. 「日程」卡片出现,显示"还没有日程"。
2. 填标题 + 日期(+可选时间)→ 添加 → 列表出现该条,预览刷新。
3. `×` 删除。

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/web/config.html
git commit -m "feat(web): /config 日程卡片(标题+日期+可选时间, 增删)"
```

---

## Task 8: 全量验证 + 预览 + spec 验收

**Files:** 无改动(纯验证)

- [ ] **Step 1: 跑全部测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全绿,唯一允许失败是预存的 `tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`。

- [ ] **Step 2: 渲染 agenda 预览**

```bash
.venv/bin/python -c "
import time
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_agenda, Zone
now=time.mktime((2026,6,14,12,0,0,0,0,-1))
ev=[{'title':'团队周会','date':'2026-06-14','time':'14:30'},
    {'title':'交报告','date':'2026-06-14','time':''},
    {'title':'体检','date':'2026-06-15','time':'09:00'},
    {'title':'看演出','date':'2026-06-18','time':'19:00'}]
img=Image.new('RGB',(360,200),(255,255,255)); d=ImageDraw.Draw(img); d.fontmode='1'
draw_agenda(d, Zone(0,0,360,200), ev, now); img.save('/tmp/agenda_preview.png'); print('saved')
"
```
打开 `/tmp/agenda_preview.png` 目视:标题「日程」、各行 今天/明天/`6/18 周三` + 时间(或"全天")+ 标题。

- [ ] **Step 3: 对照 spec 第 12 节验收逐条打勾**

1. 网页增删日程 + 屏上按时间排出近期日程(相对日 + 时间/全天 + 标题)、过期隐去 —— Task 1/3/4/5/6/7。
2. 无日程/坏文件不崩;坏日期/坏时间/空标题被 API 拒 —— Task 1/4/6。
3. 全部测试通过 —— Step 1。

- [ ] **Step 4: 归档提示**

合并后可把本期 spec+plan 移入 `docs/superpowers/archive/`。仅提示。

---

## 自检(写计划后已核对)

- **Spec 覆盖**:§5.1 存储格式 → T1;§5.2 EventStore(list 排序/add/delete/upcoming 过滤+limit)→ T1;§4 config 字段 → T2;§4 state 注入 → T3;§6 widget(空提示/相对日今天明天日期/时间全天/截断)→ T4;§4 registry → T5;§7 API(GET/POST 校验 title 空、date 坏、time 坏 / DELETE)→ T6;§8 网页卡片 → T7;§9 错误处理(坏文件当空、400、空提示)→ T1/T4/T6;§10 测试 → 各任务;§11 无新依赖 → 确认;§12 验收 → T8。无遗漏。
- **签名/命名一致**:`EventStore.list()/add(title,date,time="")/delete(eid)/upcoming(now,limit)`、`AGENDA_LIMIT`、`draw_agenda(d,z,events,now)`、state 键 `events`、registry `agenda`、config `events_store` —— 全计划统一。排序键 `(date, time or "00:00")` 在 store 与 spec 一致。
- **无占位符**:每个改码步骤均给出完整代码与确切路径/命令/预期输出。
```
