# 温度曲线 widget 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 屏上显示最近 24 小时室温折线 + 当前温度大数字 + 24h 高/低标记;新增持久化温度历史存储,hub 重启不丢。

**Architecture:** 新增 `EnvHistoryStore`(`~/inkpulse/env_history.json`,裸列表 `[[ts,温度],...]`,append 时按 24h 裁剪、入口过滤无效温度)。`/frame` 上报温度时入库;`build_render_state` 注入近 24h 采样;纯函数 `draw_temp_trend` 画折线。仿习惯打卡的 store/widget/registry 模式。

**Tech Stack:** Python 3.11 · Pillow · FastAPI · pytest。复用现有 `TodoStore`/`HabitStore` 落盘模式、`draw_usage_trend` 的 body-zone/缩放绘制、registry 适配器、config/state 接线。无新依赖。

设计来源:`docs/superpowers/specs/2026-06-14-inkpulse-temp-trend-design.md`。所有路径相对 `software/hub/`。

---

## 关键约定(全任务通用,先读)

- **测试命令**:`.venv/bin/python -m pytest`(系统 python3 是 3.10 且缺 cnlunar,直接 `pytest` 会 import 报错;venv 是 3.11)。
- **已知预存失败**:`tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`(WSL2 mDNS/网络环境所致,与本功能无关),全程忽略它;除它之外必须全绿。
- **存储格式**(`env_history.json`):裸 JSON 列表 `[[unix秒:float, 温度:float], ...]` 升序。坏/缺文件 → `[]`,不抛异常。
- **温度有效性**:`None`、非数值、或不在 `[-40, 85]°C` → append 入口静默丢弃(天然挡掉坏湿度哨兵值,因为只存 `t` 不存 `h`)。
- **保留窗口**:`RETENTION_S = 86400`(24h)。
- 每个任务结束 `commit`,运行目录 `software/hub/`。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `inkpulse_hub/collectors/env_history.py` | 新增 | `EnvHistoryStore` + 常量 `RETENTION_S`/`TEMP_MIN`/`TEMP_MAX` |
| `inkpulse_hub/config.py` | 改 | 新增 `env_history_store` 字段 + sources 覆盖 |
| `inkpulse_hub/state.py` | 改 | `HubState` 持有 store;`build_render_state` 注入 `env_history` |
| `inkpulse_hub/server.py` | 改 | `/frame` 温度有效时 `append` |
| `inkpulse_hub/render/widgets.py` | 改 | 新增 `draw_temp_trend` |
| `inkpulse_hub/render/registry.py` | 改 | 注册 `temp_trend` widget + 适配器 |
| `tests/test_env_history.py` | 新增 | `EnvHistoryStore` 单测 |
| `tests/test_widget_temp_trend.py` | 新增 | `draw_temp_trend` 测试 |
| `tests/test_config.py` | 改 | 断言 `env_history_store` 默认/覆盖 |
| `tests/test_state_phase2.py` | 改 | 断言 state 含 `env_history` |
| `tests/test_server.py` | 改 | `/frame?t=` 入库 / 无 `t` 不入库 |
| `tests/test_registry.py` | 改 | 断言 `temp_trend` 已注册并可绘制 |

---

## Task 1: EnvHistoryStore —— 存储 + append(裁剪/过滤) + window

**Files:**
- Create: `inkpulse_hub/collectors/env_history.py`
- Test: `tests/test_env_history.py`

- [ ] **Step 1: 写失败测试**

`tests/test_env_history.py`:

```python
from inkpulse_hub.collectors.env_history import EnvHistoryStore, RETENTION_S


def test_append_then_window(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, 23.4)
    s.append(1600.0, 23.6)
    assert s.window(1600.0) == [[1000.0, 23.4], [1600.0, 23.6]]


def test_append_rejects_invalid(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, None)
    s.append(1000.0, -100.0)     # 哨兵/越界
    s.append(1000.0, 999.0)      # 越界
    s.append(1000.0, "nan-ish")  # 非数值
    assert s.window(1000.0) == []


def test_prunes_older_than_24h(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, 20.0)                         # 很旧
    s.append(1000.0 + RETENTION_S + 1, 21.0)       # 触发裁剪 -> 旧点被裁
    assert s.window(1000.0 + RETENTION_S + 1) == [[1000.0 + RETENTION_S + 1, 21.0]]


def test_window_filters_by_now(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, 20.0)
    # now 比采样晚超过 24h -> 该点落在窗口外
    assert s.window(1000.0 + RETENTION_S + 5) == []


def test_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "env.json"
    p.write_text("{not a list", encoding="utf-8")
    assert EnvHistoryStore(str(p)).window(0.0) == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "env.json")
    EnvHistoryStore(path).append(1000.0, 22.2)
    assert EnvHistoryStore(path).window(1000.0) == [[1000.0, 22.2]]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_env_history.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'inkpulse_hub.collectors.env_history'`

- [ ] **Step 3: 写实现**

`inkpulse_hub/collectors/env_history.py`:

```python
# inkpulse_hub/collectors/env_history.py
import json
import os

RETENTION_S = 86400                 # 24h
TEMP_MIN, TEMP_MAX = -40.0, 85.0    # 合理温度范围, 挡 None/哨兵/越界


class EnvHistoryStore:
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

    def _write(self, samples: list) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False)

    def append(self, ts: float, temp) -> None:
        if temp is None:
            return
        try:
            t = float(temp)
        except (TypeError, ValueError):
            return
        if not (TEMP_MIN <= t <= TEMP_MAX):
            return
        samples = self._read()
        samples.append([float(ts), t])
        cutoff = float(ts) - RETENTION_S
        samples = [s for s in samples if s[0] >= cutoff]
        self._write(samples)

    def window(self, now: float) -> list:
        cutoff = now - RETENTION_S
        return sorted((s for s in self._read() if s[0] >= cutoff),
                      key=lambda s: s[0])
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_env_history.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/env_history.py tests/test_env_history.py
git commit -m "feat(env): EnvHistoryStore 温度历史存储(append 裁剪/过滤 + window)"
```

---

## Task 2: config.py —— 新增 env_history_store 字段

**Files:**
- Modify: `inkpulse_hub/config.py`(`Config` 字段 + `load_config` 覆盖)
- Test: `tests/test_config.py`(追加一条)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加:

```python
def test_env_history_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().env_history_store.endswith("inkpulse/env_history.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  env_history_store: /tmp/e.json\n", encoding="utf-8")
    assert load_config(str(p)).env_history_store == "/tmp/e.json"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_env_history_store_default_and_override -v`
Expected: FAIL —— `AttributeError: 'Config' object has no attribute 'env_history_store'`

- [ ] **Step 3: 实现**

`inkpulse_hub/config.py`:在 `Config` 数据类里、`habits_store` 字段下一行加:

```python
    env_history_store: str = os.path.expanduser("~/inkpulse/env_history.json")
```

在 `load_config` 内、`cfg.habits_store = ...` 那行下一行加:

```python
    cfg.env_history_store = os.path.expanduser(sources.get("env_history_store", cfg.env_history_store))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit -m "feat(config): 新增 env_history_store 路径字段与 sources 覆盖"
```

---

## Task 3: state.py —— 注入 env_history

**Files:**
- Modify: `inkpulse_hub/state.py`(import、`HubState.__init__`、`build_render_state`)
- Test: `tests/test_state_phase2.py`(追加用例)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_state_phase2.py` 末尾追加:

```python
def test_render_state_has_env_history(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "env_history" in state and isinstance(state["env_history"], list)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py::test_render_state_has_env_history -v`
Expected: FAIL —— `KeyError: 'env_history'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py`:

1. import 区,在 `from .collectors.habits import HabitStore` 下一行加:
```python
from .collectors.env_history import EnvHistoryStore
```

2. `HubState.__init__`,在 `self.habits = HabitStore(cfg.habits_store)` 下一行加:
```python
        self.env_history = EnvHistoryStore(cfg.env_history_store)
```

3. `build_render_state` 的返回 dict 里加一个键(放在 `"habit_today_idx": habit_today_idx,` 之后即可,不动其它键):
```python
            "env_history": self.env_history.window(now),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit -m "feat(state): build_render_state 注入 env_history"
```

---

## Task 4: server.py —— /frame 入库温度

**Files:**
- Modify: `inkpulse_hub/server.py`(`/frame` 处理函数内)
- Test: `tests/test_server.py`(追加用例)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_server.py` 末尾追加(顶部已 import `TestClient`/`create_app`/`Config`):

```python
def _app_env(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 env_history_store=str(tmp_path / "env.json"))
    return create_app(cfg)


def test_frame_with_temp_records_history(tmp_path):
    import time
    app = _app_env(tmp_path)
    TestClient(app).get("/frame", params={"t": 23.4})
    hist = app.state.hub.env_history.window(time.time())
    assert len(hist) == 1 and hist[0][1] == 23.4


def test_frame_without_temp_records_nothing(tmp_path):
    import time
    app = _app_env(tmp_path)
    TestClient(app).get("/frame", params={"rssi": -55})
    assert app.state.hub.env_history.window(time.time()) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_server.py::test_frame_with_temp_records_history -v`
Expected: FAIL —— `assert len([]) == 1`(温度未入库)

- [ ] **Step 3: 实现**

`inkpulse_hub/server.py`:`/frame` 处理函数里,`set_env` 那个 `if` 块之后、`f = render_frame(...)` 之前,加:

```python
        if t is not None:
            state.env_history.append(time.time(), t)
```

(`import time` 已在文件顶部——习惯打卡那期为 `/api/habits` 加过;若不存在则在顶部 import 区补 `import time`。先确认。)

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_server.py
git commit -m "feat(server): /frame 上报温度时写入 env_history"
```

---

## Task 5: draw_temp_trend widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(末尾新增函数)
- Test: `tests/test_widget_temp_trend.py`

- [ ] **Step 1: 写失败测试**

`tests/test_widget_temp_trend.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_temp_trend, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def test_draws_line_with_data():
    img, d = _img()
    samples = [[1000.0 + i * 600, 20 + i * 0.5] for i in range(10)]
    draw_temp_trend(d, Zone(0, 0, 400, 240), samples, now=1000.0 + 9 * 600)
    assert _has_black(img)


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_temp_trend(d, Zone(0, 0, 400, 240), [], now=1000.0)
    assert _has_black(img)   # "暂无温度数据" 文字也是黑像素; 关键不抛异常


def test_single_point_shows_hint():
    img, d = _img()
    draw_temp_trend(d, Zone(0, 0, 400, 240), [[1000.0, 22.0]], now=1000.0)
    assert _has_black(img)   # <2 点 -> 提示, 不崩


def test_flat_temperature_no_crash():
    img, d = _img()
    samples = [[1000.0 + i * 600, 22.0] for i in range(5)]   # 全等温度
    draw_temp_trend(d, Zone(0, 0, 400, 240), samples, now=1000.0 + 4 * 600)
    assert _has_black(img)   # tmin==tmax 画水平中线, 不除零


def test_none_now_falls_back_no_crash():
    img, d = _img()
    samples = [[1000.0 + i * 600, 20 + i] for i in range(3)]
    draw_temp_trend(d, Zone(0, 0, 400, 240), samples, now=None)
    assert _has_black(img)   # now=None -> 退回末点时间, 不崩
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_temp_trend.py -v`
Expected: FAIL —— `ImportError: cannot import name 'draw_temp_trend'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加:

```python
def draw_temp_trend(d: ImageDraw.ImageDraw, z: Zone, samples, now) -> None:
    """近24h 温度折线 + 当前值大数字(右上) + 高/低标记(左下)。
    samples=[[ts,temp], ...]; 纯黑, 无红。"""
    cy = _title_bar(d, z, "温度曲线 24h")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    pts = sorted(samples or [], key=lambda s: s[0])
    if len(pts) < 2:
        _center_text(d, body, "暂无温度数据", _font(18), BLACK)
        return
    temps = [p[1] for p in pts]
    tmin, tmax = min(temps), max(temps)
    if now is None:
        now = pts[-1][0]
    x_lo = now - 86400
    span = (now - x_lo) or 1
    pad = 20                                  # 上下留白给大数字/标记
    chart_top = body.y + pad
    chart_bot = body.y + body.h - pad
    chart_h = max(1, chart_bot - chart_top)
    trange = (tmax - tmin) or 1

    def px(ts):
        return body.x + int((ts - x_lo) / span * (body.w - 1))

    def py(t):
        if tmax == tmin:
            return chart_top + chart_h // 2   # 全等温度 -> 水平中线
        return chart_bot - int((t - tmin) / trange * chart_h)

    prev = None
    for p in pts:
        cur = (px(p[0]), py(p[1]))
        if prev is not None:
            d.line((prev[0], prev[1], cur[0], cur[1]), fill=BLACK, width=2)
        prev = cur

    big = f"{temps[-1]:.0f}°C"                 # 当前值(末点)大数字, 右上
    bf = _font(28)
    bw = d.textlength(big, font=bf)
    d.text((body.x + body.w - bw - 6, body.y + 2), big, fill=BLACK, font=bf)

    mark = f"高 {tmax:.0f}°  低 {tmin:.0f}°"   # 24h 峰谷, 左下(中文字, 不用箭头)
    d.text((body.x + 4, body.y + body.h - 16), mark, fill=BLACK, font=_font(14))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_temp_trend.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_temp_trend.py
git commit -m "feat(widget): draw_temp_trend 24h 温度折线 + 当前值 + 高低标记"
```

---

## Task 6: registry —— 注册 temp_trend widget

**Files:**
- Modify: `inkpulse_hub/render/registry.py`(适配器 + REGISTRY 条目)
- Test: `tests/test_registry.py`(`_state()` 补字段 + 断言)

- [ ] **Step 1: 改测试(先让其失败)**

`tests/test_registry.py` 的 `_state()` 返回 dict 内追加一键(升序、落在 now 窗口内):

```python
        "env_history": [[1718000000.0 - 3000, 20.0], [1718000000.0 - 2400, 21.0],
                        [1718000000.0 - 1800, 20.5], [1718000000.0, 22.0]],
```

把 `test_existing_widgets_registered` 的 `expected` 集合加入 `"temp_trend"`:

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist", "habits", "temp_trend"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL —— `temp_trend` 不在 REGISTRY

- [ ] **Step 3: 实现**

`inkpulse_hub/render/registry.py`:

1. 在 `_habits` 适配器之后加:
```python
def _temp_trend(d, img, z, state, cfg, p):
    W.draw_temp_trend(d, z, state.get("env_history", []), state.get("now"))
```

2. `REGISTRY` 字典里(`"habits": ...` 条目之后)加一条:
```python
    "temp_trend":    WidgetSpec("temp_trend", "温度曲线", _temp_trend, {"cols": 4, "rows": 3}),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit -m "feat(registry): 注册 temp_trend widget 与适配器"
```

---

## Task 7: 全量验证 + spec 验收对照

**Files:** 无改动(纯验证)

- [ ] **Step 1: 跑全部测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全绿,唯一允许失败是预存的 `tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`(mDNS/网络)。

- [ ] **Step 2: 预览看一眼 temp_trend**

用 Python 渲染样例数据确认折线/当前值/高低标记正常:

```bash
.venv/bin/python -c "
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_temp_trend, Zone
img = Image.new('RGB',(440,200),(255,255,255)); d=ImageDraw.Draw(img); d.fontmode='1'
import math
samples=[[1749800000.0+i*600, 20+4*math.sin(i/12)] for i in range(144)]
draw_temp_trend(d, Zone(0,0,440,200), samples, now=1749800000.0+143*600)
img.save('/tmp/temp_trend_preview.png'); print('saved')
"
```
打开 `/tmp/temp_trend_preview.png` 目视:有 24h 起伏折线、右上当前值大数字、左下「高 X° 低 Y°」。

- [ ] **Step 3: 对照 spec 第 11 节验收标准逐条打勾**

1. 板子上报温度后屏上 `temp_trend` 显示近 24h 折线 + 右上当前值 + 左下高/低 —— Task 4/5/6。
2. hub 重启后历史仍在(持久化)—— Task 1 `test_persistence_across_instances`。
3. 无数据/坏文件/坏温度值不崩;湿度坏通道数据不入库 —— Task 1/5(只存 `t`,append 过滤越界)。
4. 全部测试通过 —— Step 1。

- [ ] **Step 4: 文档归档提示**

合并后可把本期 spec+plan 与习惯打卡的 spec+plan 一并移入 `docs/superpowers/archive/`(沿用前几期 `chore: 归档…` 做法)。本步骤仅提示,归档动作收尾时单独做。

---

## 自检(写计划后已核对)

- **Spec 覆盖**:§5 存储/EnvHistoryStore → Task1;§7 config → Task2;§4+state 注入 → Task3;§4 `/frame` 入库 → Task4;§6 widget(折线+当前值+高低+全等温度+空/单点提示)→ Task5;§4 registry → Task6;§8 错误处理(坏文件当空、越界丢弃、<2 点提示、tmin==tmax 不除零)→ Task1/5;§9 测试计划 → 各任务 TDD;§10 无新依赖 → 已确认;§11 验收 → Task7。无遗漏。
- **类型/签名一致**:`EnvHistoryStore.append(ts,temp)→None`、`window(now)→list[[ts,temp]]`、`draw_temp_trend(d,z,samples,now)`、state 键 `env_history`、registry 适配器传 `state.get("now")` —— 全计划统一。
- **无占位符**:每个改码步骤均给出完整代码与确切路径/命令/预期输出。
```
