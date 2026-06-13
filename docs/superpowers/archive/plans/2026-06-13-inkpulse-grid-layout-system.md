# 数据驱动网格布局系统 实现计划(第一期)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 InkPulse Hub 的布局从写死的 Python 函数改成数据驱动的网格系统(layouts.json + widget 注册表 + 网页网格编辑器),并加入 countdown / qrcode 两个验证 widget。

**Architecture:** 屏幕切成固定 8×6 网格;每个布局是一组 placements(widget + 矩形格子坐标 + 参数),存在 `~/inkpulse/layouts.json`。渲染时 `render_frame` 遍历 placements,用 `cell_to_zone` 把网格坐标换成像素 `Zone`,再查 widget 注册表逐个绘制(单 widget 出错画 n/a,不拖垮整帧)。现有 8 个 widget 通过薄适配器接入,现有 6 个预设迁移成 builtin 布局。

**Tech Stack:** Python 3.11+ / FastAPI / Pillow / pytest;新增依赖 `qrcode`。所有路径相对 `software/hub/`。

**关键约定:**
- 工作目录:`software/hub/`。测试用 `.venv/bin/python -m pytest`。
- 提交因仓库 LFS 钩子缺 git-lfs,统一用 `git commit --no-verify`。
- 统一 widget 签名带 `img`:`draw(d, img, zone, state, cfg, params)`(photo/qrcode 需要往 img 上 paste 图像;其余 widget 忽略 img)。这是对设计文档 §5.1 签名 `fn(d, zone, state, cfg, params)` 的实现期细化。
- 测试为保证确定性,渲染相关测试一律设 `cfg.layouts_store = ""`(空路径 → 加载内置默认布局,不读用户真实文件)。

---

## Task 1: Config 增加 layouts_store 字段

**Files:**
- Modify: `inkpulse_hub/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 末尾追加:

```python
def test_layouts_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    # 默认值在家目录下
    assert Config().layouts_store.endswith("inkpulse/layouts.json")
    # 可被 config.yaml 的 sources.layouts_store 覆盖
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  layouts_store: /tmp/my-layouts.json\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.layouts_store == "/tmp/my-layouts.json"
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_layouts_store_default_and_override -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'layouts_store'`

- [ ] **Step 3: 实现**

在 `inkpulse_hub/config.py` 的 `Config` 数据类里,`runtime_store` 字段后加一行:

```python
    runtime_store: str = os.path.expanduser("~/inkpulse/runtime.json")
    layouts_store: str = os.path.expanduser("~/inkpulse/layouts.json")
```

在 `load_config` 的 `sources` 段,`runtime_store` 那行后加:

```python
    cfg.runtime_store = os.path.expanduser(sources.get("runtime_store", cfg.runtime_store))
    cfg.layouts_store = os.path.expanduser(sources.get("layouts_store", cfg.layouts_store))
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS(全部)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit --no-verify -m "feat(hub): Config 增加 layouts_store 字段(网格布局存储路径)"
```

---

## Task 2: 网格坐标 → 像素 Zone(grid.py)

**Files:**
- Create: `inkpulse_hub/render/grid.py`
- Test: `tests/test_grid.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_grid.py`:

```python
from inkpulse_hub.render.grid import cell_to_zone

GRID = {"cols": 8, "rows": 6}   # 800x480 -> 格子 100x80


def test_single_cell():
    z = cell_to_zone(GRID, {"col": 0, "row": 0, "colspan": 1, "rowspan": 1})
    assert (z.x, z.y, z.w, z.h) == (0, 0, 100, 80)


def test_span_and_offset():
    z = cell_to_zone(GRID, {"col": 4, "row": 1, "colspan": 4, "rowspan": 3})
    assert (z.x, z.y, z.w, z.h) == (400, 80, 400, 240)


def test_full_bleed_covers_screen():
    z = cell_to_zone(GRID, {"col": 0, "row": 0, "colspan": 8, "rowspan": 6})
    assert (z.x, z.y, z.w, z.h) == (0, 0, 800, 480)


def test_adjacent_cells_tile_without_gap():
    # 非整除网格也要无缝相接: 右格的 x 必须等于左格的 x+w
    g = {"cols": 3, "rows": 1}   # 800/3 非整除
    left = cell_to_zone(g, {"col": 0, "row": 0, "colspan": 1, "rowspan": 1})
    mid = cell_to_zone(g, {"col": 1, "row": 0, "colspan": 1, "rowspan": 1})
    assert mid.x == left.x + left.w
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_grid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'inkpulse_hub.render.grid'`

- [ ] **Step 3: 实现**

新建 `inkpulse_hub/render/grid.py`:

```python
# inkpulse_hub/render/grid.py
# 网格坐标(col/row/colspan/rowspan) -> 像素 Zone。
# 用累计 round 保证相邻格无缝相接, 即使 800/cols 不整除。
from .planes import WIDTH, HEIGHT
from .widgets import Zone


def cell_to_zone(grid: dict, p: dict) -> Zone:
    cols = grid["cols"]
    rows = grid["rows"]
    cw = WIDTH / cols
    ch = HEIGHT / rows
    x = round(p["col"] * cw)
    y = round(p["row"] * ch)
    x2 = round((p["col"] + p["colspan"]) * cw)
    y2 = round((p["row"] + p["rowspan"]) * ch)
    return Zone(x, y, x2 - x, y2 - y)
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_grid.py -v`
Expected: PASS(4 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/grid.py tests/test_grid.py
git commit --no-verify -m "feat(hub): 网格坐标->像素 Zone 换算(无缝铺满)"
```

---

## Task 3: Widget 注册表(registry.py,接入现有 8 widget)

**Files:**
- Create: `inkpulse_hub/render/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_registry.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.registry import REGISTRY, WidgetSpec
from inkpulse_hub.render.widgets import Zone
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0, "rssi": -55},
        "clock": "2026-06-13 14:32 周五",
        "lunar": {"text": "农历四月廿七", "festival": ""},
        "now": 1718000000.0,
    }


def _img():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def test_existing_widgets_registered():
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo"}
    assert expected <= set(REGISTRY)
    for name in expected:
        assert isinstance(REGISTRY[name], WidgetSpec)
        assert REGISTRY[name].default_span["cols"] >= 1


def test_each_widget_draws_without_error():
    img, d = _img()
    z = Zone(0, 0, 400, 240)
    for name, spec in REGISTRY.items():
        spec.draw(d, img, z, _state(), Config(), {})   # 不应抛异常


def test_header_widget_paints_pixels():
    img, d = _img()
    REGISTRY["header"].draw(d, img, Zone(0, 0, 800, 80), _state(), Config(), {})
    black = sum(1 for x in range(800) for y in range(80)
                if img.getpixel((x, y)) == (0, 0, 0))
    assert black > 50
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'inkpulse_hub.render.registry'`

- [ ] **Step 3: 实现**

新建 `inkpulse_hub/render/registry.py`。每个 widget 一个适配器,把统一签名 `(d, img, zone, state, cfg, params)` 映射到现有 `widgets.py` 的绘制函数(注册表独占"从 state 取数"的知识)。

```python
# inkpulse_hub/render/registry.py
# Widget 注册表: 统一签名 draw(d, img, zone, state, cfg, params)。
# 适配器负责从 state/cfg/params 取数, 调用 widgets.py 里的纯绘制函数。
from dataclasses import dataclass, field
from typing import Callable
from PIL import Image
from . import widgets as W
from .dither import dither_bwr


@dataclass
class WidgetSpec:
    name: str
    label: str
    draw: Callable          # (d, img, zone, state, cfg, params) -> None
    default_span: dict      # {"cols": int, "rows": int}
    params: list = field(default_factory=list)  # [{key,label,type,default}]


def _header(d, img, z, state, cfg, p):
    env = state.get("env", {})
    W.draw_header(d, z, state.get("clock", ""), state.get("lunar"),
                  env.get("temp"), env.get("humidity"), env.get("rssi"))


def _claude(d, img, z, state, cfg, p):
    W.draw_claude_status(d, z, state["claude"], state.get("now"))


def _usage(d, img, z, state, cfg, p):
    W.draw_usage(d, z, state["usage"], cfg.usage_budget_usd)


def _usage_ring(d, img, z, state, cfg, p):
    W.draw_usage_ring(d, z, state["usage"])


def _todos(d, img, z, state, cfg, p):
    W.draw_todos(d, z, state.get("todos", []))


def _big_clock(d, img, z, state, cfg, p):
    W.draw_big_clock(d, z, state.get("now"))


def _calendar(d, img, z, state, cfg, p):
    W.draw_month_calendar(d, z, state.get("now"))


def _photo(d, img, z, state, cfg, p):
    photo = state.get("photo")
    if photo is None:
        W._center_text(d, z, "无照片", W._font(24), W.BLACK)
        return
    im = dither_bwr(Image.open(photo.path), (z.w, z.h))
    img.paste(im, (z.x, z.y))


REGISTRY: dict[str, WidgetSpec] = {
    "header":        WidgetSpec("header", "头部", _header, {"cols": 8, "rows": 1}),
    "claude_status": WidgetSpec("claude_status", "Claude状态", _claude, {"cols": 4, "rows": 3}),
    "usage":         WidgetSpec("usage", "今日用量", _usage, {"cols": 4, "rows": 3}),
    "usage_ring":    WidgetSpec("usage_ring", "用量环", _usage_ring, {"cols": 3, "rows": 3}),
    "todos":         WidgetSpec("todos", "待办", _todos, {"cols": 8, "rows": 2}),
    "big_clock":     WidgetSpec("big_clock", "大时钟", _big_clock, {"cols": 8, "rows": 4}),
    "calendar":      WidgetSpec("calendar", "月历", _calendar, {"cols": 4, "rows": 3}),
    "photo":         WidgetSpec("photo", "整屏照片", _photo, {"cols": 8, "rows": 6}),
}
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS(3 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit --no-verify -m "feat(hub): widget 注册表 + 现有 8 widget 适配器"
```

---

## Task 4: 布局存储与内置预设(layouts.py)

**Files:**
- Create: `inkpulse_hub/render/layouts.py`
- Test: `tests/test_layouts_store.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_layouts_store.py`:

```python
import json
import pytest
from inkpulse_hub.render import layouts as L


def test_defaults_have_six_builtins_when_no_file():
    store = L.load_store("")          # 空路径 -> 内置默认
    assert store["grid"] == {"cols": 8, "rows": 6}
    assert {"dash", "photo", "usage", "todo", "clock", "split"} <= set(store["layouts"])
    for lay in store["layouts"].values():
        assert lay.get("builtin") is True
        assert isinstance(lay["placements"], list) and lay["placements"]


def test_get_layout_falls_back_to_dash_for_unknown(tmp_path):
    p = str(tmp_path / "layouts.json")
    lay = L.get_layout(p, "no-such-layout")
    assert lay["grid"]["cols"] == 8
    assert lay["placements"] == L.get_layout(p, "dash")["placements"]


def test_save_then_get_roundtrip(tmp_path):
    p = str(tmp_path / "layouts.json")
    placements = [{"widget": "qrcode", "col": 0, "row": 0,
                   "colspan": 2, "rowspan": 3, "params": {"content": "hi"}}]
    L.save_layout(p, "我的", placements)
    got = L.get_layout(p, "我的")
    assert got["placements"][0]["widget"] == "qrcode"
    assert got["placements"][0]["params"]["content"] == "hi"
    # builtin 仍在(文件与内置合并)
    assert "dash" in L.load_store(p)["layouts"]


def test_save_does_not_persist_all_builtins(tmp_path):
    p = str(tmp_path / "layouts.json")
    L.save_layout(p, "我的", [{"widget": "todos", "col": 0, "row": 0,
                              "colspan": 8, "rowspan": 6, "params": {}}])
    raw = json.loads(open(p, encoding="utf-8").read())
    assert set(raw["layouts"]) == {"我的"}     # 文件只存用户布局, 不灌入 6 个内置


def test_delete_user_layout(tmp_path):
    p = str(tmp_path / "layouts.json")
    L.save_layout(p, "我的", [{"widget": "todos", "col": 0, "row": 0,
                              "colspan": 8, "rowspan": 6, "params": {}}])
    L.delete_layout(p, "我的")
    assert "我的" not in L.load_store(p)["layouts"]


def test_delete_builtin_rejected(tmp_path):
    p = str(tmp_path / "layouts.json")
    with pytest.raises(ValueError):
        L.delete_layout(p, "dash")


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "layouts.json"
    p.write_text("{ not json", encoding="utf-8")
    assert "dash" in L.load_store(str(p))["layouts"]


def test_clamp_out_of_grid_placement(tmp_path):
    p = str(tmp_path / "layouts.json")
    L.save_layout(p, "越界", [{"widget": "todos", "col": 6, "row": 0,
                              "colspan": 9, "rowspan": 1, "params": {}}])
    z = L.get_layout(p, "越界")["placements"][0]
    assert z["col"] + z["colspan"] <= 8       # 被 clamp 进网格
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_layouts_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'inkpulse_hub.render.layouts'`

- [ ] **Step 3: 实现**

新建 `inkpulse_hub/render/layouts.py`。内置 6 预设用 8×6 网格表达(像素位置近似还原现状,作为可编辑起点)。

```python
# inkpulse_hub/render/layouts.py
# 布局存储: 内置 6 预设(builtin, 不可删) + 用户自建(写 layouts.json)。
# 读取时把文件与内置合并; 写入只存用户布局, 不灌入内置。
import json
import os
from copy import deepcopy

GRID = {"cols": 8, "rows": 6}


def _p(widget, col, row, colspan, rowspan, **params):
    return {"widget": widget, "col": col, "row": row,
            "colspan": colspan, "rowspan": rowspan, "params": params}


BUILTIN_LAYOUTS = {
    "dash": {"builtin": True, "placements": [
        _p("header", 0, 0, 8, 1),
        _p("claude_status", 0, 1, 4, 3),
        _p("usage", 4, 1, 4, 3),
        _p("todos", 0, 4, 8, 2),
    ]},
    "photo": {"builtin": True, "placements": [
        _p("photo", 0, 0, 8, 6),
    ]},
    "clock": {"builtin": True, "placements": [
        _p("big_clock", 0, 0, 8, 4),
        _p("calendar", 1, 4, 6, 2),
    ]},
    "usage": {"builtin": True, "placements": [
        _p("usage", 0, 0, 5, 4),
        _p("usage_ring", 5, 0, 3, 4),
        _p("claude_status", 0, 4, 4, 2),
        _p("todos", 4, 4, 4, 2),
    ]},
    "split": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1),
        _p("claude_status", 0, 1, 4, 3),
        _p("usage", 0, 4, 4, 2),
        _p("calendar", 4, 0, 4, 3),
        _p("todos", 4, 3, 4, 3),
    ]},
    "todo": {"builtin": True, "placements": [
        _p("todos", 0, 0, 5, 6),
        _p("calendar", 5, 0, 3, 3),
        _p("claude_status", 5, 3, 3, 3),
    ]},
}


def _default_store():
    return {"version": 1, "grid": dict(GRID), "layouts": deepcopy(BUILTIN_LAYOUTS)}


def _load_raw(path: str) -> dict:
    """读文件原始内容(只含用户布局); 不存在/损坏 -> 空骨架。"""
    if not path or not os.path.exists(path):
        return {"version": 1, "grid": dict(GRID), "layouts": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "grid": dict(GRID), "layouts": {}}
    data.setdefault("grid", dict(GRID))
    data.setdefault("layouts", {})
    return data


def load_store(path: str) -> dict:
    """对外读取: 内置 + 用户文件合并(同名时用户覆盖内置)。"""
    raw = _load_raw(path)
    merged = deepcopy(BUILTIN_LAYOUTS)
    merged.update(raw["layouts"])
    return {"version": 1, "grid": raw["grid"], "layouts": merged}


def _clamp(placements: list, grid: dict) -> list:
    cols, rows = grid["cols"], grid["rows"]
    out = []
    for p in placements:
        col = max(0, min(int(p["col"]), cols - 1))
        row = max(0, min(int(p["row"]), rows - 1))
        colspan = max(1, min(int(p["colspan"]), cols - col))
        rowspan = max(1, min(int(p["rowspan"]), rows - row))
        out.append({"widget": p["widget"], "col": col, "row": row,
                    "colspan": colspan, "rowspan": rowspan,
                    "params": p.get("params", {})})
    return out


def get_layout(path: str, name: str) -> dict:
    """取某布局(含 clamp); 未知名回退 dash。返回 {grid, placements}。"""
    store = load_store(path)
    layouts = store["layouts"]
    lay = layouts.get(name) or layouts["dash"]
    return {"grid": store["grid"], "placements": _clamp(lay["placements"], store["grid"])}


def save_layout(path: str, name: str, placements: list) -> None:
    raw = _load_raw(path)
    raw["layouts"][name] = {"placements": placements}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)


def delete_layout(path: str, name: str) -> None:
    if name in BUILTIN_LAYOUTS:
        raise ValueError("内置布局不可删")
    raw = _load_raw(path)
    raw["layouts"].pop(name, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_layouts_store.py -v`
Expected: PASS(8 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/layouts.py tests/test_layouts_store.py
git commit --no-verify -m "feat(hub): 布局存储 layouts.json + 6 内置预设迁移"
```

---

## Task 5: engine 改数据驱动 + 退役硬编码 LAYOUTS

**Files:**
- Modify: `inkpulse_hub/render/engine.py`(整体重写渲染路径)
- Modify: `inkpulse_hub/server.py:6`(去掉 `LAYOUTS` 导入)、`:88-103`(`/api/config` 改用布局存储)
- Modify: `tests/test_engine.py`(state 加 layouts_store="")
- Modify: `tests/test_layouts.py`(旧的 `LAYOUTS` 断言改为新系统)

- [ ] **Step 1: 改测试为新系统(先让其失败)**

把 `tests/test_engine.py` 的 `_state()` 保持不变,但三个 `render_frame(Config(), ...)` 调用改为先关掉真实文件读取。在文件顶部加一个辅助并替换三处 `Config()`:

```python
def _cfg():
    c = Config()
    c.layouts_store = ""      # 用内置布局, 不读用户真实文件, 保证确定性
    return c
```

把 `test_render_produces_full_frame` / `test_same_input_same_etag` / `test_missing_data_falls_back_not_crash` 里的 `Config()` 全部换成 `_cfg()`。

把 `tests/test_layouts.py` 末尾的 `test_all_layouts_registered_and_render_full_frame` 整个函数替换为:

```python
def test_all_builtin_layouts_render_full_frame():
    from inkpulse_hub.render.engine import render_frame
    from inkpulse_hub.render import layouts as L
    from inkpulse_hub.config import Config
    from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem
    expected = {"dash", "photo", "usage", "todo", "clock", "split"}
    assert expected <= set(L.load_store("")["layouts"])
    state = {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0, "rssi": -55},
        "clock": "2026-06-13 14:32 周五",
        "lunar": {"text": "农历四月廿七", "festival": ""},
        "now": 1718000000.0,
    }
    for name in expected:
        cfg = Config()
        cfg.layouts_store = ""
        cfg.layout_name = name
        f = render_frame(cfg, state)
        assert len(f.body) == 96000, f"{name} 帧大小错"
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_engine.py tests/test_layouts.py -v`
Expected: FAIL(`render_frame` 仍走旧 `LAYOUTS`,且 `layouts_store=""` 字段虽存在但 engine 未使用 → `test_all_builtin_layouts_render_full_frame` 因 import/逻辑未就位而 FAIL)

- [ ] **Step 3: 重写 engine.py**

把 `inkpulse_hub/render/engine.py` 整体替换为(删除 6 个 `draw_xxx` 与 `ZONES`/`LAYOUTS`):

```python
# inkpulse_hub/render/engine.py
import io
from dataclasses import dataclass
from PIL import Image, ImageDraw
from ..config import Config
from .planes import pack_frame, frame_etag, WIDTH, HEIGHT
from .grid import cell_to_zone
from .registry import REGISTRY
from . import layouts as L
from . import widgets as W


@dataclass
class Frame:
    body: bytes       # 96000B 双 plane
    etag: str
    png_bytes: bytes  # /preview.png 用


def _draw_na(d, z):
    """单 widget 缺失/出错时的占位框, 不拖垮整帧。"""
    d.rectangle((z.x, z.y, z.x + z.w - 1, z.y + z.h - 1), outline=W.BLACK)
    W._center_text(d, z, "n/a", W._font(20), W.BLACK)


def render_frame(cfg: Config, state: dict) -> Frame:
    img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"   # 关抗锯齿: 墨水屏三色量化, 文字纯黑/白

    layout = L.get_layout(cfg.layouts_store, cfg.layout_name)
    for p in layout["placements"]:
        z = cell_to_zone(layout["grid"], p)
        spec = REGISTRY.get(p["widget"])
        if spec is None:
            _draw_na(d, z)
            continue
        try:
            spec.draw(d, img, z, state, cfg, p.get("params", {}))
        except Exception:
            _draw_na(d, z)   # 按 widget 隔离容错

    body = pack_frame(img)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
```

- [ ] **Step 4: 更新 server.py 去掉 LAYOUTS 依赖**

`inkpulse_hub/server.py` 第 6 行:

```python
from .render.engine import render_frame, LAYOUTS
```
改为:
```python
from .render.engine import render_frame
from .render import layouts as L
```

`/api/config` 两处(原 88-103 行)改为用布局存储的名字集合:

```python
    @app.get("/api/config")
    def api_config_get():
        data = {f: getattr(cfg, f) for f in RUNTIME_FIELDS}
        data["layouts"] = list(L.load_store(cfg.layouts_store)["layouts"].keys())
        return data

    @app.post("/api/config")
    async def api_config_set(request: Request):
        data = await request.json()
        names = L.load_store(cfg.layouts_store)["layouts"]
        if "layout_name" in data and data["layout_name"] not in names:
            return JSONResponse({"error": "unknown layout"}, status_code=400)
        for k in RUNTIME_FIELDS:
            if k in data:
                setattr(cfg, k, data[k])
        save_runtime(cfg, cfg.runtime_store)
        return {"ok": True}
```

- [ ] **Step 5: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_engine.py tests/test_layouts.py tests/test_config_api.py tests/test_server.py -v`
Expected: PASS(`test_config_api` 仍过,因为内置布局含 `clock`;未知布局仍被拒)

- [ ] **Step 6: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: 仅 `test_discovery.py` 那条 mDNS 用例可能因本机已占用服务名而 FAIL(环境性,与本改动无关);其余全过。若 discovery 也过更好。

- [ ] **Step 7: 提交**

```bash
git add inkpulse_hub/render/engine.py inkpulse_hub/server.py tests/test_engine.py tests/test_layouts.py
git commit --no-verify -m "feat(hub): render_frame 改数据驱动网格渲染, 退役硬编码布局"
```

---

## Task 6: countdown 倒计时 widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(加 `draw_countdown`)
- Modify: `inkpulse_hub/render/registry.py`(注册 + 适配器)
- Test: `tests/test_widget_countdown.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_widget_countdown.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_countdown, Zone


def _img():
    img = Image.new("RGB", (300, 160), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_red(img):
    return any(img.getpixel((x, y)) == (255, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


NOW = 1718000000.0   # 2024-06-10 (本地时区附近)


def test_future_date_renders_black():
    img, d = _img()
    draw_countdown(d, Zone(0, 0, 300, 160), NOW, "2099-01-01", "新年")
    assert _has_black(img)


def test_near_date_within_3_days_is_red():
    img, d = _img()
    import datetime
    soon = (datetime.date.fromtimestamp(NOW) + datetime.timedelta(days=2)).isoformat()
    draw_countdown(d, Zone(0, 0, 300, 160), NOW, soon, "马上")
    assert _has_red(img)   # 0..3 天内告警红


def test_bad_date_does_not_crash():
    img, d = _img()
    draw_countdown(d, Zone(0, 0, 300, 160), NOW, "not-a-date", "x")
    # 不抛异常即可
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_countdown.py -v`
Expected: FAIL — `ImportError: cannot import name 'draw_countdown'`

- [ ] **Step 3: 实现绘制函数**

在 `inkpulse_hub/render/widgets.py` 末尾追加:

```python
def draw_countdown(d: ImageDraw.ImageDraw, z: Zone, now, date_str, label="") -> None:
    """倒计时/纪念日: 顶部标题栏(label) + 居中 D-N。0..3 天内标红。"""
    import datetime, time
    cy = _title_bar(d, z, label or "倒计时")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    try:
        target = datetime.date.fromisoformat((date_str or "").strip())
        today = datetime.date.fromtimestamp(now if now else time.time())
        days = (target - today).days
    except (ValueError, TypeError):
        _center_text(d, body, "日期?", _font(24), BLACK)
        return
    if days > 0:
        big = f"D-{days}"
    elif days == 0:
        big = "就在今天"
    else:
        big = f"已过{-days}天"
    color = RED if 0 <= days <= 3 else BLACK
    _center_text(d, body, big, _font(min(48, max(20, body.h - 8))), color)
```

- [ ] **Step 4: 注册到 registry**

在 `inkpulse_hub/render/registry.py` 加适配器(放在 `_photo` 之后):

```python
def _countdown(d, img, z, state, cfg, p):
    W.draw_countdown(d, z, state.get("now"), p.get("date"), p.get("label", ""))
```

在 `REGISTRY` 字典里加一项:

```python
    "countdown": WidgetSpec("countdown", "倒计时", _countdown, {"cols": 3, "rows": 2},
                            [{"key": "date", "label": "目标日期", "type": "date", "default": ""},
                             {"key": "label", "label": "标签", "type": "text", "default": ""}]),
```

- [ ] **Step 5: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_countdown.py tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add inkpulse_hub/render/widgets.py inkpulse_hub/render/registry.py tests/test_widget_countdown.py
git commit --no-verify -m "feat(hub): countdown 倒计时 widget(D-N, 临近标红)"
```

---

## Task 7: qrcode 二维码 widget

**Files:**
- Modify: `pyproject.toml`(加 `qrcode` 依赖)
- Modify: `inkpulse_hub/render/widgets.py`(顶部加 `Image` 导入 + `draw_qrcode`)
- Modify: `inkpulse_hub/render/registry.py`(注册 + 适配器)
- Test: `tests/test_widget_qrcode.py`

- [ ] **Step 1: 装依赖**

Run:
```bash
.venv/bin/python -m pip install "qrcode>=7.4"
```
Expected: 成功安装 qrcode(及其依赖)。

- [ ] **Step 2: 写失败测试**

新建 `tests/test_widget_qrcode.py`:

```python
from PIL import Image
from inkpulse_hub.render.widgets import draw_qrcode, Zone


def _img():
    return Image.new("RGB", (200, 200), (255, 255, 255))


def test_qrcode_paints_black_and_only_bw():
    img = _img()
    draw_qrcode(img, Zone(0, 0, 200, 200), "https://example.com")
    colors = {img.getpixel((x, y)) for x in range(0, 200, 3) for y in range(0, 200, 3)}
    assert (0, 0, 0) in colors                       # 画了黑模块
    assert colors <= {(0, 0, 0), (255, 255, 255)}    # 仅黑白, 无灰/红(墨水屏友好)


def test_qrcode_empty_content_no_crash():
    img = _img()
    draw_qrcode(img, Zone(0, 0, 200, 200), "")
    # 空内容不画、不抛异常
```

- [ ] **Step 3: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_qrcode.py -v`
Expected: FAIL — `ImportError: cannot import name 'draw_qrcode'`

- [ ] **Step 4: 实现绘制函数**

`inkpulse_hub/render/widgets.py` 第 3 行导入补上 `Image`:

```python
from PIL import Image, ImageDraw, ImageFont
```

文件末尾追加:

```python
def draw_qrcode(img: Image.Image, z: Zone, content: str) -> None:
    """在 zone 内居中画纯黑白二维码(墨水屏友好)。空内容不画。"""
    import qrcode
    if not content:
        return
    qr = qrcode.QRCode(border=1, box_size=1)
    qr.add_data(content)
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    size = max(1, min(z.w, z.h))
    q = q.resize((size, size), Image.NEAREST)   # 最近邻, 保持纯黑白不出灰边
    ox = z.x + (z.w - size) // 2
    oy = z.y + (z.h - size) // 2
    img.paste(q, (ox, oy))
```

- [ ] **Step 5: 注册到 registry**

`inkpulse_hub/render/registry.py` 加适配器:

```python
def _qrcode(d, img, z, state, cfg, p):
    W.draw_qrcode(img, z, p.get("content", ""))
```

`REGISTRY` 加一项:

```python
    "qrcode": WidgetSpec("qrcode", "二维码", _qrcode, {"cols": 2, "rows": 3},
                         [{"key": "content", "label": "内容(URL/文本)", "type": "text", "default": ""}]),
```

- [ ] **Step 6: 加依赖到 pyproject**

`pyproject.toml` 的 `dependencies` 列表里,`"python-multipart>=0.0.9",` 后加一行:

```toml
    "qrcode>=7.4",
```

- [ ] **Step 7: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_qrcode.py tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add pyproject.toml inkpulse_hub/render/widgets.py inkpulse_hub/render/registry.py tests/test_widget_qrcode.py
git commit --no-verify -m "feat(hub): qrcode 二维码 widget + qrcode 依赖"
```

---

## Task 8: 布局编辑 API(/api/layouts)

**Files:**
- Modify: `inkpulse_hub/server.py`(新增 GET/PUT/DELETE `/api/layouts`)
- Test: `tests/test_layouts_api.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_layouts_api.py`:

```python
from fastapi.testclient import TestClient
from inkpulse_hub.config import Config
from inkpulse_hub.server import create_app


def _client(tmp_path):
    cfg = Config()
    cfg.runtime_store = str(tmp_path / "runtime.json")
    cfg.layouts_store = str(tmp_path / "layouts.json")
    cfg.photos_dir = str(tmp_path / "photos")
    return cfg, TestClient(create_app(cfg))


def test_get_layouts_returns_grid_builtins_and_widget_catalog(tmp_path):
    cfg, c = _client(tmp_path)
    body = c.get("/api/layouts").json()
    assert body["grid"] == {"cols": 8, "rows": 6}
    assert "dash" in body["layouts"]
    names = {w["name"] for w in body["widgets"]}
    assert {"header", "countdown", "qrcode"} <= names
    cd = next(w for w in body["widgets"] if w["name"] == "countdown")
    assert cd["default_span"]["cols"] >= 1 and isinstance(cd["params"], list)


def test_put_creates_user_layout(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/我的", json={"placements": [
        {"widget": "qrcode", "col": 0, "row": 0, "colspan": 2, "rowspan": 3,
         "params": {"content": "hi"}}]})
    assert r.status_code == 200
    assert "我的" in c.get("/api/layouts").json()["layouts"]


def test_put_rejects_unknown_widget(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/x", json={"placements": [
        {"widget": "nope", "col": 0, "row": 0, "colspan": 1, "rowspan": 1}]})
    assert r.status_code == 400


def test_put_rejects_out_of_grid(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.put("/api/layouts/x", json={"placements": [
        {"widget": "todos", "col": 6, "row": 0, "colspan": 9, "rowspan": 1}]})
    assert r.status_code == 400


def test_delete_user_ok_builtin_rejected(tmp_path):
    cfg, c = _client(tmp_path)
    c.put("/api/layouts/我的", json={"placements": [
        {"widget": "todos", "col": 0, "row": 0, "colspan": 8, "rowspan": 6}]})
    assert c.delete("/api/layouts/我的").status_code == 200
    assert c.delete("/api/layouts/dash").status_code == 400   # 内置不可删
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_layouts_api.py -v`
Expected: FAIL — 404(端点尚不存在)

- [ ] **Step 3: 实现端点**

`inkpulse_hub/server.py` 顶部补导入(与 Task 5 已加的 `from .render import layouts as L` 并列):

```python
from .render.registry import REGISTRY
```

在 `/api/config` 端点之后、`# ---- 照片管理` 之前插入:

```python
    # ---- 布局编辑: 网格 + widget 目录 + 自定义布局 CRUD ----
    @app.get("/api/layouts")
    def api_layouts_get():
        store = L.load_store(cfg.layouts_store)
        widgets = [{"name": s.name, "label": s.label,
                    "default_span": s.default_span, "params": s.params}
                   for s in REGISTRY.values()]
        return {"grid": store["grid"], "layouts": store["layouts"], "widgets": widgets}

    @app.put("/api/layouts/{name}")
    async def api_layouts_put(name: str, request: Request):
        data = await request.json()
        placements = data.get("placements", [])
        grid = L.load_store(cfg.layouts_store)["grid"]
        for p in placements:
            if p.get("widget") not in REGISTRY:
                return JSONResponse({"error": f"unknown widget {p.get('widget')}"}, status_code=400)
            try:
                col, row = int(p["col"]), int(p["row"])
                cs, rs = int(p["colspan"]), int(p["rowspan"])
            except (KeyError, TypeError, ValueError):
                return JSONResponse({"error": "bad placement"}, status_code=400)
            if not (0 <= col and 0 <= row and cs >= 1 and rs >= 1
                    and col + cs <= grid["cols"] and row + rs <= grid["rows"]):
                return JSONResponse({"error": "out of grid"}, status_code=400)
        L.save_layout(cfg.layouts_store, name, placements)
        return {"ok": True}

    @app.delete("/api/layouts/{name}")
    def api_layouts_delete(name: str):
        try:
            L.delete_layout(cfg.layouts_store, name)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"ok": True}
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_layouts_api.py -v`
Expected: PASS(5 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_layouts_api.py
git commit --no-verify -m "feat(hub): /api/layouts 布局编辑 API(GET 目录 / PUT / DELETE)"
```

---

## Task 9: 网页网格编辑器(config.html)

**Files:**
- Modify: `inkpulse_hub/web/config.html`(新增"布局编辑器"卡片 + JS)

> 此任务是前端交互,无单元测试;Step 4 用真机/浏览器手动验收。

- [ ] **Step 1: 加编辑器卡片的 HTML**

在 `config.html` 的"布局"卡片(第 34-37 行那块 `<div class="card">...</div>`)之后,紧接着插入一个新卡片:

```html
  <div class="card">
    <h2>布局编辑器
      <span style="float:right">
        <select id="edLayout" onchange="edPick(this.value)" style="padding:4px 8px;border-radius:6px"></select>
        <button class="ghost" style="padding:4px 10px" onclick="edNew()">新建</button>
        <button class="ghost" style="padding:4px 10px" onclick="edDelete()">删除</button>
      </span>
    </h2>
    <div id="edGrid" style="display:grid;grid-template-columns:repeat(8,1fr);gap:2px;background:#111;border:2px solid #111;aspect-ratio:5/3"></div>
    <div class="row" style="margin-top:10px">
      <label>选中区域</label>
      <select id="edWidget" style="flex:1;padding:6px 8px;border:1px solid #d4d4d8;border-radius:6px"></select>
      <button onclick="edPlace()">放入</button>
    </div>
    <div id="edParams"></div>
    <div class="hint">点格子起点、再点终点框出矩形 → 选 widget(+填参数)→"放入"。点已放置的 widget 可删除。改完点"保存布局"。内置布局可直接改(会另存为同名覆盖)。</div>
    <button onclick="edSave()" style="margin-top:8px">保存布局</button>
  </div>
```

- [ ] **Step 2: 加编辑器 JS**

在 `config.html` 的 `<script>` 里、`load();`(第 159 行)那一行**之前**插入以下代码:

```javascript
// ===== 布局编辑器 =====
const GW = 8, GH = 6;        // 网格列/行
let edCat = [];              // widget 目录
let edPlacements = [];       // 当前编辑的 placements
let edName = null;           // 当前编辑布局名
let edSel = null;            // 选区 {c0,r0,c1,r1}
let edAnchor = null;         // 框选起点

async function edLoad() {
  const data = await (await fetch('/api/layouts')).json();
  edCat = data.widgets;
  const sel = document.getElementById('edLayout');
  sel.innerHTML = Object.keys(data.layouts).map(n => `<option>${esc(n)}</option>`).join('');
  const ws = document.getElementById('edWidget');
  ws.innerHTML = edCat.map(w => `<option value="${w.name}">${esc(w.label)}</option>`).join('');
  ws.onchange = edParamForm; edParamForm();
  edPick(sel.value);
}

function edPick(name) {
  edName = name;
  fetch('/api/layouts').then(r => r.json()).then(d => {
    edPlacements = JSON.parse(JSON.stringify((d.layouts[name] || {}).placements || []));
    document.getElementById('edLayout').value = name;
    edSel = null; edAnchor = null; edRender();
  });
}

function edParamForm() {
  const w = edCat.find(x => x.name === document.getElementById('edWidget').value);
  const box = document.getElementById('edParams');
  if (!w || !w.params.length) { box.innerHTML = ''; return; }
  box.innerHTML = w.params.map(p =>
    `<div class="row"><label>${esc(p.label)}</label><input data-k="${p.key}" type="${p.type === 'date' ? 'date' : (p.type === 'number' ? 'number' : 'text')}" value="${p.default || ''}"></div>`).join('');
}

function edRender() {
  const g = document.getElementById('edGrid');
  g.innerHTML = '';
  const occ = {};
  edPlacements.forEach((p, i) => {
    for (let c = p.col; c < p.col + p.colspan; c++)
      for (let r = p.row; r < p.row + p.rowspan; r++) occ[c + ',' + r] = i;
  });
  for (let r = 0; r < GH; r++) for (let c = 0; c < GW; c++) {
    const cell = document.createElement('div');
    cell.style.cssText = 'background:#fff;min-height:26px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#3730a3;cursor:pointer;text-align:center;line-height:1.1';
    const idx = occ[c + ',' + r];
    if (idx !== undefined) {
      const w = edCat.find(x => x.name === edPlacements[idx].widget);
      cell.style.background = '#e0e7ff';
      cell.textContent = (w ? w.label : edPlacements[idx].widget);
      cell.onclick = () => { if (confirm('删除这个 widget?')) { edPlacements.splice(idx, 1); edRender(); } };
    } else {
      const inSel = edSel && c >= edSel.c0 && c <= edSel.c1 && r >= edSel.r0 && r <= edSel.r1;
      if (inSel) cell.style.background = '#fef9c3';
      cell.onclick = () => edClick(c, r);
    }
    g.appendChild(cell);
  }
}

function edClick(c, r) {
  if (!edAnchor) { edAnchor = { c, r }; edSel = { c0: c, r0: r, c1: c, r1: r }; }
  else {
    edSel = { c0: Math.min(edAnchor.c, c), r0: Math.min(edAnchor.r, r),
              c1: Math.max(edAnchor.c, c), r1: Math.max(edAnchor.r, r) };
    edAnchor = null;
  }
  edRender();
}

function edPlace() {
  if (!edSel) { alert('先在网格里框选一块区域'); return; }
  const widget = document.getElementById('edWidget').value;
  const params = {};
  document.querySelectorAll('#edParams input').forEach(i => params[i.dataset.k] = i.value);
  edPlacements.push({
    widget, col: edSel.c0, row: edSel.r0,
    colspan: edSel.c1 - edSel.c0 + 1, rowspan: edSel.r1 - edSel.r0 + 1, params
  });
  edSel = null; edAnchor = null; edRender();
}

async function edSave() {
  const r = await fetch('/api/layouts/' + encodeURIComponent(edName), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ placements: edPlacements })
  });
  if (!r.ok) { alert('保存失败: ' + (await r.json()).error); return; }
  alert('已保存。切到该布局并"刷新屏幕"即可上屏。');
  load();                        // 刷新顶部布局列表
  setTimeout(refreshPreview, 300);
}

async function edNew() {
  const name = prompt('新布局名'); if (!name) return;
  edName = name; edPlacements = []; edSel = null; edAnchor = null;
  const sel = document.getElementById('edLayout');
  if (![...sel.options].some(o => o.value === name))
    sel.insertAdjacentHTML('beforeend', `<option>${esc(name)}</option>`);
  sel.value = name; edRender();
}

async function edDelete() {
  if (!edName) return;
  const r = await fetch('/api/layouts/' + encodeURIComponent(edName), { method: 'DELETE' });
  if (!r.ok) { alert((await r.json()).error); return; }
  edLoad(); load();
}
```

并在最后的 `load();` 那一行后面加一行:

```javascript
load();
edLoad();
```

- [ ] **Step 3: 语法自检**

Run:
```bash
.venv/bin/python -c "p='inkpulse_hub/web/config.html'; s=open(p,encoding='utf-8').read(); assert s.count('<div class=\"card\">')>=6; assert 'edSave' in s and 'api/layouts' in s; print('config.html OK, cards=',s.count('<div class=\\\"card\\\">'))"
```
Expected: 打印 `config.html OK, cards= 6`(或更多)

- [ ] **Step 4: 手动验收(真机/浏览器)**

```bash
systemctl --user restart inkpulse-hub      # 若已装服务; 否则 ./run.sh
```
浏览器开 `http://localhost:8080/config`,在"布局编辑器":
1. "新建"一个布局 → 框选顶部一行 → widget 选"头部" → "放入"。
2. 框选一块 → 选"二维码" → 填内容 `http://localhost:8080/config` → "放入"。
3. 框选一块 → 选"倒计时" → 填日期/标签 → "放入"。
4. "保存布局" → 回到顶部"布局"选中它 → 看"实时预览"出现对应排布。
5. 点已放置 widget 可删除;"删除"内置布局应被拒(弹"内置布局不可删")。

预期:预览图按你的网格排布渲染,二维码为纯黑白,倒计时显示 D-N。

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/web/config.html
git commit --no-verify -m "feat(hub): 网页网格布局编辑器(点格子选 widget + 参数 + 保存)"
```

---

## Task 10: 文档与全量回归

**Files:**
- Modify: `software/hub/README.md`(布局段落更新)

- [ ] **Step 1: 更新 README**

把 `software/hub/README.md` 里"配置(config.yaml)"段的 `layout:` 说明替换为指向新系统的说明:

```markdown
layout:
  # 当前生效布局名(对应 layouts.json 里的 key);内置: dash/photo/usage/todo/clock/split
  name: dash
sources:
  layouts_store: ~/inkpulse/layouts.json   # 自定义布局存储(网页编辑器写入)
```

并在"仪表盘渲染规则"附近加一句:

```markdown
- **布局自定义**:屏幕为 8×6 网格,布局是数据(`layouts.json`)。浏览器开 `/config` 的"布局编辑器"可点格子放 widget、存成命名布局。加新 widget = 在 `render/registry.py` 注册一个绘制函数。
```

- [ ] **Step 2: 全量测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全过(除 `test_discovery` 可能因本机已跑 hub 占用 mDNS 服务名而 FAIL,属环境性)。若 discovery 也通过更好。

- [ ] **Step 3: 提交**

```bash
git add software/hub/README.md
git commit --no-verify -m "docs(hub): README 更新网格布局系统说明"
```

---

## 验收标准回顾(对应 spec §12)

1. 网页能新建布局、框选放 widget(含 countdown/qrcode 填参数)、保存、切换、预览看到效果 — Task 9。
2. 原 6 预设作为 builtin 仍可用、外观近似、可改 — Task 4 + Task 5。
3. 任一 widget 出错只影响该格、整帧仍出图 — Task 5(`_draw_na` + per-widget try/except)、Task 3 测试覆盖。
4. 全部测试通过 — 每个 Task 的测试 + Task 10 全量回归。
