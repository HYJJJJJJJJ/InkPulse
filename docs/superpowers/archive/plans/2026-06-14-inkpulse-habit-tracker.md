# 习惯打卡 widget 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在墨水屏上以"本周打卡墙"展示若干习惯,网页 `/config` 管理习惯并逐日打卡(可补打本周已过的日子,未来禁用)。

**Architecture:** 新增 `HabitStore`(`~/inkpulse/habits.json`)负责存储与本周视图计算;`build_render_state` 注入结构化数据;纯函数 `draw_habits` 只消费数据;FastAPI 增 `/api/habits*`;`config.html` 加「习惯打卡」卡片。存储/计算与展示分离,widget 为纯函数便于确定性测试。

**Tech Stack:** Python 3.11 · Pillow · FastAPI · pytest。复用现有 `TodoStore` / `draw_todos` / `draw_month_calendar` / registry 适配器 / config 卡片模式,无新依赖。

设计来源:`docs/superpowers/specs/2026-06-13-inkpulse-habit-tracker-design.md`。所有路径相对 `software/hub/`。

---

## 关键约定(全任务通用,先读)

- **存储格式**(`habits.json`):`{"habits":[{"id","name"}], "log":{"YYYY-MM-DD":[id,...]}}`。`id = uuid4().hex[:8]`(同 `TodoStore`)。
- **习惯用纯 dict**(`{"id","name"}`),不建 dataclass(spec 5.1),故 `models.py` 不改。
- **本周**:周一为第 0 列;`today_idx = date.weekday()`(周一=0…周日=6)。ISO 日期串 `YYYY-MM-DD` 可直接字典序比较大小(用于"未来日期"判断)。
- **■/□ 用绘制矩形实现**(实心 = 已打卡,空心 = 已过未打,留空 = 未来),不用字体字形 —— 与 `draw_month_calendar` 的画格方式一致,可精确对齐并给"今天列"描边,且不依赖字体是否含 U+25A0/U+25A1。这满足 spec 6「实心方块/空心方块」的意图。
- 每个任务结束都 `commit`。测试用 `pytest`,运行目录 `software/hub/`。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `inkpulse_hub/collectors/habits.py` | 新增 | `HabitStore` + `week_dates(now)` 模块函数 |
| `inkpulse_hub/config.py` | 改 | 新增 `habits_store` 字段 + `sources.habits_store` 覆盖 |
| `inkpulse_hub/state.py` | 改 | `HubState` 持有 `HabitStore`;`build_render_state` 注入 `habits` / `habit_today_idx` |
| `inkpulse_hub/render/widgets.py` | 改 | 新增 `draw_habits` |
| `inkpulse_hub/render/registry.py` | 改 | 注册 `habits` widget + 适配器 |
| `inkpulse_hub/server.py` | 改 | `/api/habits` 系列端点 |
| `inkpulse_hub/web/config.html` | 改 | 「习惯打卡」卡片 + JS |
| `tests/test_habits.py` | 新增 | `HabitStore` 单测 |
| `tests/test_habits_api.py` | 新增 | API 契约测试 |
| `tests/test_widget_habits.py` | 新增 | `draw_habits` 测试 |
| `tests/test_state_phase2.py` | 改 | 断言 state 含 `habits` / `habit_today_idx` |
| `tests/test_registry.py` | 改 | 断言 `habits` 已注册并可绘制 |

---

## Task 1: HabitStore —— 存储读写 + list/add/delete

**Files:**
- Create: `inkpulse_hub/collectors/habits.py`
- Test: `tests/test_habits.py`

- [ ] **Step 1: 写失败测试**

`tests/test_habits.py`:

```python
from inkpulse_hub.collectors.habits import HabitStore


def test_add_list_delete(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    assert h["name"] == "运动" and len(h["id"]) == 8
    assert [x["name"] for x in store.list()] == ["运动"]

    store.add("阅读")
    assert [x["name"] for x in store.list()] == ["运动", "阅读"]

    store.delete(h["id"])
    assert [x["name"] for x in store.list()] == ["阅读"]


def test_missing_file_is_empty(tmp_path):
    assert HabitStore(str(tmp_path / "nope.json")).list() == []


def test_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "habits.json"
    p.write_text("{not json", encoding="utf-8")
    assert HabitStore(str(p)).list() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "habits.json")
    HabitStore(path).add("喝水")
    assert [x["name"] for x in HabitStore(path).list()] == ["喝水"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_habits.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'inkpulse_hub.collectors.habits'`

- [ ] **Step 3: 写最小实现**

`inkpulse_hub/collectors/habits.py`:

```python
# inkpulse_hub/collectors/habits.py
from __future__ import annotations   # 必需: list() 方法遮蔽内建 list,
                                     # 否则后定义的 week_view 的 tuple[list[...]] 注解在类定义时报错
import json
import os
import time
import uuid
import datetime as _dt


def week_dates(now: float) -> tuple[list[str], int]:
    """本周(周一→周日)7 个 ISO 日期串 + 今天列索引(周一=0…周日=6)。"""
    lt = time.localtime(now)
    today = _dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)
    monday = today - _dt.timedelta(days=today.weekday())
    dates = [(monday + _dt.timedelta(days=i)).isoformat() for i in range(7)]
    return dates, today.weekday()


class HabitStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self) -> dict:
        if not os.path.exists(self.path):
            return {"habits": [], "log": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError
            data.setdefault("habits", [])
            data.setdefault("log", {})
            return data
        except (json.JSONDecodeError, ValueError, OSError):
            return {"habits": [], "log": {}}

    def _write(self, data: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list(self) -> list[dict]:
        return self._read()["habits"]

    def add(self, name: str) -> dict:
        data = self._read()
        h = {"id": uuid.uuid4().hex[:8], "name": (name or "").strip()}
        data["habits"].append(h)
        self._write(data)
        return h

    def delete(self, hid: str) -> None:
        data = self._read()
        data["habits"] = [h for h in data["habits"] if h["id"] != hid]
        for day in data["log"].values():
            if hid in day:
                day.remove(hid)
        self._write(data)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_habits.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/habits.py tests/test_habits.py
git commit -m "feat(habits): HabitStore 存储读写 + list/add/delete + week_dates"
```

---

## Task 2: HabitStore —— toggle / is_done / week_view

**Files:**
- Modify: `inkpulse_hub/collectors/habits.py`(`HabitStore` 内追加方法)
- Test: `tests/test_habits.py`(追加用例)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_habits.py` 末尾追加:

```python
def test_toggle_roundtrip_and_is_done(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    assert store.is_done(h["id"], "2026-06-10") is False
    store.toggle(h["id"], "2026-06-10")
    assert store.is_done(h["id"], "2026-06-10") is True
    store.toggle(h["id"], "2026-06-10")              # 再次 toggle => 取消
    assert store.is_done(h["id"], "2026-06-10") is False


def test_delete_clears_log_entries(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    store.toggle(h["id"], "2026-06-10")
    store.delete(h["id"])
    # 重新打开,该 id 不应再出现在任何一天的 log 里
    raw = HabitStore(str(tmp_path / "habits.json"))._read()
    assert all(h["id"] not in day for day in raw["log"].values())


def test_week_view_structure(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    # 2026-06-14 是周日 -> today_idx 应为 6;本周一是 2026-06-08
    store.toggle(h["id"], "2026-06-08")   # 周一
    now = __import__("time").mktime((2026, 6, 14, 12, 0, 0, 0, 0, -1))
    rows, today_idx = store.week_view(now)
    assert today_idx == 6
    assert rows == [{"name": "运动", "days": [True, False, False, False, False, False, False]}]


def test_week_view_empty_when_no_habits(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    now = __import__("time").mktime((2026, 6, 14, 12, 0, 0, 0, 0, -1))
    rows, today_idx = store.week_view(now)
    assert rows == [] and 0 <= today_idx <= 6
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_habits.py -k "toggle or week_view or delete_clears" -v`
Expected: FAIL —— `AttributeError: 'HabitStore' object has no attribute 'toggle'`

- [ ] **Step 3: 写最小实现**

在 `inkpulse_hub/collectors/habits.py` 的 `HabitStore` 类内、`delete` 之后追加:

```python
    def toggle(self, hid: str, date_iso: str) -> None:
        data = self._read()
        day = data["log"].setdefault(date_iso, [])
        if hid in day:
            day.remove(hid)
        else:
            day.append(hid)
        self._write(data)

    def is_done(self, hid: str, date_iso: str) -> bool:
        return hid in self._read()["log"].get(date_iso, [])

    def week_view(self, now: float) -> tuple[list[dict], int]:
        dates, today_idx = week_dates(now)
        data = self._read()
        log = data["log"]
        rows = [
            {"name": h["name"],
             "days": [h["id"] in log.get(dt, []) for dt in dates]}
            for h in data["habits"]
        ]
        return rows, today_idx
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_habits.py -v`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/habits.py tests/test_habits.py
git commit -m "feat(habits): HabitStore toggle/is_done/week_view"
```

---

## Task 3: config.py —— 新增 habits_store 字段

**Files:**
- Modify: `inkpulse_hub/config.py:17`(字段)与 `:42` 附近(sources 覆盖)
- Test: `tests/test_config.py`(追加一条)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加(若文件无 import,顶部已有 `from inkpulse_hub.config import ...`,沿用):

```python
def test_habits_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().habits_store.endswith("inkpulse/habits.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  habits_store: /tmp/h.json\n", encoding="utf-8")
    assert load_config(str(p)).habits_store == "/tmp/h.json"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_config.py::test_habits_store_default_and_override -v`
Expected: FAIL —— `AttributeError: 'Config' object has no attribute 'habits_store'`

- [ ] **Step 3: 实现**

`inkpulse_hub/config.py` 在 `todos_store` 字段下一行(第 17 行后)加:

```python
    habits_store: str = os.path.expanduser("~/inkpulse/habits.json")
```

`load_config` 内、`cfg.todos_store = ...` 那行(第 42 行)下一行加:

```python
    cfg.habits_store = os.path.expanduser(sources.get("habits_store", cfg.habits_store))
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_config.py -v`
Expected: PASS(全绿)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit -m "feat(config): 新增 habits_store 路径字段与 sources 覆盖"
```

---

## Task 4: state.py —— 注入 habits / habit_today_idx

**Files:**
- Modify: `inkpulse_hub/state.py`(import、`HubState.__init__`、`build_render_state`)
- Test: `tests/test_state_phase2.py`(追加用例)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_state_phase2.py` 末尾追加:

```python
def test_render_state_has_habits(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "habits" in state and isinstance(state["habits"], list)
    assert "habit_today_idx" in state and 0 <= state["habit_today_idx"] <= 6
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_state_phase2.py::test_render_state_has_habits -v`
Expected: FAIL —— `KeyError: 'habits'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py`:

1. import 区(第 8 行 `from .collectors.todos import TodoStore` 下)加:
```python
from .collectors.habits import HabitStore
```

2. `HubState.__init__`(`self.todos = ...` 那行下)加:
```python
        self.habits = HabitStore(cfg.habits_store)
```

3. `build_render_state` 内,`now = ...` 之后、`return {` 之前加一行计算,并在返回 dict 里加两个键:
```python
        now = now if now is not None else time.time()
        habits, habit_today_idx = self.habits.week_view(now)
        return {
            ...
            "now": now,
            "habits": habits,
            "habit_today_idx": habit_today_idx,
        }
```
(把 `"habits"` / `"habit_today_idx"` 两行加进现有返回 dict 即可,其余键不动。)

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit -m "feat(state): build_render_state 注入 habits 与 habit_today_idx"
```

---

## Task 5: draw_habits widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(末尾新增函数)
- Test: `tests/test_widget_habits.py`

- [ ] **Step 1: 写失败测试**

`tests/test_widget_habits.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_habits, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def test_draws_black_with_data():
    img, d = _img()
    habits = [{"name": "运动", "days": [True, True, False, False, False, False, False]}]
    draw_habits(d, Zone(0, 0, 400, 240), habits, today_idx=2)
    assert _has_black(img)


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_habits(d, Zone(0, 0, 400, 240), [], today_idx=3)
    assert _has_black(img)   # 提示文字也是黑像素;关键是不抛异常


def test_future_columns_left_blank():
    # today_idx=0 => 第 1..6 列都是未来,应留空(即便 days 全 True)
    img, d = _img(420, 120)
    habits = [{"name": "运动", "days": [True] * 7}]
    z = Zone(0, 0, 420, 120)
    draw_habits(d, z, habits, today_idx=0)
    # 取最后一列(周日,未来)格子中心附近,应为白
    name_w = max(60, z.w // 4)
    grid_x = z.x + name_w
    cw = (z.x + z.w - grid_x - 6) // 7
    cx = grid_x + 6 * cw + cw // 2
    cy = z.y + 26 + 6 + 22 + 15   # 标题栏+表头之后第一行附近
    assert img.getpixel((cx, cy)) == (255, 255, 255)


def test_today_idx_at_boundary_no_crash():
    img, d = _img()
    habits = [{"name": "阅读", "days": [False] * 7}]
    draw_habits(d, Zone(0, 0, 400, 240), habits, today_idx=6)   # 周日为今天
    assert _has_black(img)   # 空心格 + 今天描边都是黑;不抛异常即达标
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_widget_habits.py -v`
Expected: FAIL —— `ImportError: cannot import name 'draw_habits'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加:

```python
def draw_habits(d: ImageDraw.ImageDraw, z: Zone, habits: list, today_idx: int) -> None:
    """本周(周一→周日)打卡墙。habits=[{"name","days":[bool×7]}], today_idx=今天列(周一=0)。
    实心方块=已打卡, 空心方块=已过未打, 留空=未来; 今天列额外描边。纯黑, 无红。"""
    cy = _title_bar(d, z, "习惯打卡")
    if not habits:
        _center_text(d, z, "无习惯 · 去网页添加", _font(18), BLACK)
        return
    heads = ["一", "二", "三", "四", "五", "六", "日"]
    name_w = max(60, z.w // 4)                 # 左侧习惯名列宽
    grid_x = z.x + name_w
    cw = (z.x + z.w - grid_x - 6) // 7          # 每列宽
    hf = _font(15)
    for c, hd in enumerate(heads):             # 星期表头, 与下方格子列对齐
        d.text((grid_x + c * cw + cw // 2 - 7, cy), hd, fill=BLACK, font=hf)
    row_y0 = cy + 22
    avail = z.y + z.h - row_y0 - 4
    row_h = 30
    max_rows = max(1, avail // row_h)
    nf = _font(18)
    for r, hb in enumerate(habits[:max_rows]):
        y = row_y0 + r * row_h
        name = hb["name"]
        while name and d.textlength(name, font=nf) > name_w - 10:   # 超长截断
            name = name[:-1]
        d.text((z.x + 6, y + 4), name, fill=BLACK, font=nf)
        box = min(cw, row_h) - 12
        midy = y + row_h // 2
        for c in range(7):
            cx = grid_x + c * cw + (cw - box) // 2
            by = midy - box // 2
            rect = (cx, by, cx + box, by + box)
            if c > today_idx:
                pass                                   # 未来: 留空
            elif hb["days"][c]:
                d.rectangle(rect, fill=BLACK)          # ■ 已打卡
            else:
                d.rectangle(rect, outline=BLACK)       # □ 已过未打
            if c == today_idx:                         # 今天列描边强调
                d.rectangle((cx - 3, by - 3, cx + box + 3, by + box + 3),
                            outline=BLACK, width=1)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_widget_habits.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_habits.py
git commit -m "feat(widget): draw_habits 本周打卡墙(实心/空心/未来留空+今天描边)"
```

---

## Task 6: registry —— 注册 habits widget

**Files:**
- Modify: `inkpulse_hub/render/registry.py`(适配器 + REGISTRY 条目)
- Test: `tests/test_registry.py`(`_state()` 补字段 + 断言)

- [ ] **Step 1: 改测试(先让其失败)**

`tests/test_registry.py` 的 `_state()` 返回 dict 内追加两键:

```python
        "habits": [{"name": "运动", "days": [True, False, False, False, False, False, False]}],
        "habit_today_idx": 1,
```

把 `test_existing_widgets_registered` 的 `expected` 集合加入 `"habits"`:

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist", "habits"}
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL —— `assert {'habits'} <= set(REGISTRY)` 不成立 / KeyError

- [ ] **Step 3: 实现**

`inkpulse_hub/render/registry.py`:

1. 在 `_project_dist` 适配器之后加:
```python
def _habits(d, img, z, state, cfg, p):
    W.draw_habits(d, z, state.get("habits", []), state.get("habit_today_idx", 0))
```

2. `REGISTRY` 字典里(`"project_dist": ...` 之后)加一条:
```python
    "habits":        WidgetSpec("habits", "习惯打卡", _habits, {"cols": 4, "rows": 3}),
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit -m "feat(registry): 注册 habits widget 与适配器"
```

---

## Task 7: server —— /api/habits 系列端点

**Files:**
- Modify: `inkpulse_hub/server.py`(import + 4 个路由,放在 todos 端点 `/api/todos/{tid}` delete 之后)
- Test: `tests/test_habits_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_habits_api.py`:

```python
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config
from inkpulse_hub.collectors.habits import week_dates
import time


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 habits_store=str(tmp_path / "habits.json"))
    return TestClient(create_app(cfg))


def test_get_empty_structure(tmp_path):
    r = _client(tmp_path).get("/api/habits").json()
    assert r["habits"] == [] and r["done"] == {}
    assert len(r["week"]) == 7 and 0 <= r["today_idx"] <= 6


def test_add_reject_empty_name(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/habits", json={"name": "运动"}).status_code == 200
    assert c.post("/api/habits", json={"name": "   "}).status_code == 400
    assert [h["name"] for h in c.get("/api/habits").json()["habits"]] == ["运动"]


def test_toggle_today_and_done_matrix(tmp_path):
    c = _client(tmp_path)
    hid = c.post("/api/habits", json={"name": "运动"}).json()["id"]
    dates, idx = week_dates(time.time())
    today = dates[idx]
    assert c.post(f"/api/habits/{hid}/toggle", json={"date": today}).status_code == 200
    done = c.get("/api/habits").json()["done"][hid]
    assert done[idx] is True


def test_toggle_future_rejected(tmp_path):
    c = _client(tmp_path)
    hid = c.post("/api/habits", json={"name": "运动"}).json()["id"]
    dates, idx = week_dates(time.time())
    if idx < 6:                       # 本周还有未来日
        future = dates[idx + 1]
        assert c.post(f"/api/habits/{hid}/toggle", json={"date": future}).status_code == 400
    # 显式造一个远未来日, 必拒
    assert c.post(f"/api/habits/{hid}/toggle", json={"date": "2099-01-01"}).status_code == 400


def test_toggle_unknown_id_404(tmp_path):
    c = _client(tmp_path)
    dates, idx = week_dates(time.time())
    assert c.post("/api/habits/deadbeef/toggle",
                  json={"date": dates[idx]}).status_code == 404


def test_delete_habit(tmp_path):
    c = _client(tmp_path)
    hid = c.post("/api/habits", json={"name": "运动"}).json()["id"]
    assert c.delete(f"/api/habits/{hid}").status_code == 200
    assert c.get("/api/habits").json()["habits"] == []
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_habits_api.py -v`
Expected: FAIL —— GET `/api/habits` 返回 404(路由未定义)

- [ ] **Step 3: 实现**

`inkpulse_hub/server.py`:

1. 顶部 import 区(第 7 行 `from .render.registry import REGISTRY` 后)加:
```python
import time
from .collectors.habits import week_dates
```

2. 在 `api_delete`(todos 的 `@app.delete("/api/todos/{tid}")`,约第 78–81 行)之后、`# ---- 配置中心` 注释之前,插入:
```python
    @app.get("/api/habits")
    def api_habits_list():
        dates, today_idx = week_dates(time.time())
        habits = state.habits.list()
        done = {h["id"]: [state.habits.is_done(h["id"], dt) for dt in dates]
                for h in habits}
        return {"habits": habits, "week": dates, "done": done, "today_idx": today_idx}

    @app.post("/api/habits")
    async def api_habits_add(request: Request):
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "empty name"}, status_code=400)
        return state.habits.add(name)

    @app.delete("/api/habits/{hid}")
    def api_habits_delete(hid: str):
        state.habits.delete(hid)
        return {"ok": True}

    @app.post("/api/habits/{hid}/toggle")
    async def api_habits_toggle(hid: str, request: Request):
        data = await request.json()
        date_iso = (data.get("date") or "").strip()
        if hid not in {h["id"] for h in state.habits.list()}:
            return JSONResponse({"error": "unknown habit"}, status_code=404)
        dates, today_idx = week_dates(time.time())
        if date_iso > dates[today_idx]:        # ISO 串字典序即日期序
            return JSONResponse({"error": "future date"}, status_code=400)
        state.habits.toggle(hid, date_iso)
        return {"ok": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_habits_api.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_habits_api.py
git commit -m "feat(api): /api/habits 列表/增/删/打卡(拒未来日与未知id)"
```

---

## Task 8: config.html —— 「习惯打卡」卡片

**Files:**
- Modify: `inkpulse_hub/web/config.html`(`<style>` 加 1 条规则、待办卡片后加 1 张卡片、`load()` 加 1 行、`<script>` 末尾加 4 个函数)
- 手动验证(纯前端,无单测)

- [ ] **Step 1: 加样式**

在 `<style>` 块内任意位置(如 `.hint` 规则附近)加:

```css
.hcell{width:26px;height:26px;padding:0;margin:0 1px;border:1px solid #d4d4d8;background:#fff;border-radius:4px;cursor:pointer;font-size:12px}
.hcell.on{background:#000;color:#fff;border-color:#000}
.hcell:disabled{opacity:.35;cursor:not-allowed}
```

- [ ] **Step 2: 加卡片**

在待办卡片(`<div class="card"><h2>待办</h2>…</div>`,约第 86–93 行)之后、`</div>`(`#wrap` 收尾,约第 95 行)之前插入:

```html
  <div class="card">
    <h2>习惯打卡</h2>
    <div id="habits"></div>
    <div class="row" style="margin-top:12px">
      <input id="habitName" placeholder="新习惯..." onkeydown="if(event.key==='Enter')addHabit()">
      <button onclick="addHabit()">添加</button>
    </div>
  </div>
```

- [ ] **Step 3: load() 里挂载**

在 `load()` 函数体末尾(现有 `loadTodos();` 那行,约第 124 行)下一行加:

```javascript
  loadHabits();
```

- [ ] **Step 4: 加 JS 函数**

在 `<script>` 块末尾(`</script>` 之前)加:

```javascript
const HWEEK=['一','二','三','四','五','六','日'];
async function loadHabits(){
  const data=await (await fetch('/api/habits')).json();
  const box=document.getElementById('habits');box.innerHTML='';
  if(!data.habits.length){box.innerHTML='<div class="hint">还没有习惯</div>';return;}
  data.habits.forEach(h=>{
    const cells=data.done[h.id].map((on,i)=>{
      const future=i>data.today_idx;
      return `<button class="hcell${on?' on':''}" ${future?'disabled':''} title="${data.week[i]}" onclick="toggleHabit('${h.id}','${data.week[i]}')">${HWEEK[i]}</button>`;
    }).join('');
    box.insertAdjacentHTML('beforeend',
      `<div class="row"><span style="flex:1">${esc(h.name)}</span>${cells}<button class="ghost" onclick="delHabit('${h.id}')">×</button></div>`);
  });
}
async function addHabit(){
  const i=document.getElementById('habitName');const n=i.value.trim();if(!n)return;
  await fetch('/api/habits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  i.value='';loadHabits();setTimeout(refreshPreview,300);
}
async function toggleHabit(id,date){
  await fetch('/api/habits/'+id+'/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date})});
  loadHabits();setTimeout(refreshPreview,300);
}
async function delHabit(id){
  await fetch('/api/habits/'+id,{method:'DELETE'});loadHabits();setTimeout(refreshPreview,300);
}
```

- [ ] **Step 5: 手动验证**

```bash
# 在仓库根目录用既有方式起 hub(参考 run.sh),浏览器开 /config
```
检查:
1. 「习惯打卡」卡片出现;输入框 + 「添加」可新增习惯。
2. 每个习惯一行 7 个按钮(一…日);今天及之前可点(toggle 后实心/空心翻转),未来按钮置灰禁用。
3. `×` 删除习惯;打卡/增删后预览图刷新。

- [ ] **Step 6: 提交**

```bash
git add inkpulse_hub/web/config.html
git commit -m "feat(web): /config 新增习惯打卡卡片(点格打卡, 未来禁用)"
```

---

## Task 9: 全量验证 + spec 验收对照

**Files:** 无改动(纯验证)

- [ ] **Step 1: 跑全部测试**

Run: `pytest -q`
Expected: 全绿(含新增 `test_habits.py` / `test_habits_api.py` / `test_widget_habits.py`,及改动的 `test_state_phase2.py` / `test_registry.py` / `test_config.py`)

- [ ] **Step 2: 真机/预览看一眼 habits widget**

把某个布局加入 `habits` widget(或在布局编辑器放置),开 `/preview.png` 确认:本周打卡墙渲染正常,今天列描边、未来列留空、数据与网页一致。

- [ ] **Step 3: 对照 spec 第 12 节验收标准逐条打勾**

1. 网页能增删习惯 + 点本周已到日格子打卡,未来禁用 —— Task 7/8。
2. 屏上 `habits` widget 显示本周打卡墙,今天列描边、未来留空 —— Task 5/6。
3. 无习惯/坏文件不崩;toggle 未来日被拒 —— Task 1/5/7 测试覆盖。
4. 全部测试通过 —— Step 1。

- [ ] **Step 4: 文档归档提示**

实现合并后,可把 spec 与本 plan 移入 `docs/superpowers/archive/`(沿用前两期 `chore: 归档…` 的做法)。本步骤仅提示,归档动作在收尾时单独做。

---

## 自检(写计划后已核对)

- **Spec 覆盖**:§5 存储/HabitStore → Task1/2;§5.3 本周计算 → `week_dates`(Task1);§4+state 注入 → Task4;§6 widget → Task5;§4 registry → Task6;§7 API(GET/POST/DELETE/toggle 含未来拒、未知 id 404、空名 400)→ Task7;§8 网页卡片 → Task8;§9 错误处理(坏文件当空、404、400、空习惯提示)→ Task1/5/7;§10 测试计划 → 各任务 TDD;§11 无新依赖 → 已确认;§12 验收 → Task9。无遗漏。
- **类型/签名一致**:`HabitStore.list()→list[dict]`、`week_view(now)→(list,int)`、`week_dates(now)→(list[str],int)`、`draw_habits(d,z,habits,today_idx)`、state 键 `habits`/`habit_today_idx`、API `done` 按 id 键 —— 全计划统一。
- **无占位符**:每个改码步骤均给出完整代码与确切路径/命令/预期输出。
```
