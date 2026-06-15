# InkPulse Hub 多屏 Profile 实现计划(Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 hub 渲染由 `ScreenProfile` 驱动,新增 4.2 寸 `bw_426`(480×800 竖屏、纯黑白单 plane、旋转 90°、4×8 网格)profile 与同名竖版内置布局,设备通过 `GET /frame?...&panel=<id>` 选屏;缺省/未知回退现有 `bwr_750`,7.5 寸行为零回归。

**Architecture:** 新增 `render/profiles.py` 定义 `ScreenProfile` 表。`planes.py` 增加 BW 单 plane 打包 + 旋转感知的 `pack_frame_for(img, profile)`;`grid.py` 的 `cell_to_zone` 参数化画布尺寸;`layouts.py` 内置布局按 profile 分组(新增 `bw_426` 4×8 六布局)、API 带 profile 命名空间;`engine.py` 的 `render_frame(cfg, state, profile)` 按 profile 建画布/选布局集/打包;`server.py` 的 `/frame` 解析 `panel` 参数解析 profile。颜色降级:渲染态注入 `color`,日历"今天"/行情/照片在 BW 下红→黑并用加框/反色/单色抖动替代。

**Tech Stack:** Python 3.11、Pillow(PIL)、FastAPI、pytest。所有验证用 `pytest` + `/preview.png`,**不依赖硬件**。

**运行测试:** 在 `software/hub/` 下用 `./.venv/bin/pytest`(venv 已含 PIL/fastapi/pytest)。

---

## 文件结构

- **新建** `software/hub/inkpulse_hub/render/profiles.py` — `ScreenProfile` 数据类 + `PROFILES` 表 + `get_profile()`。
- **新建** `software/hub/tests/test_profiles.py`
- **改** `software/hub/inkpulse_hub/render/planes.py` — 加 `to_plane_bw`、`pack_frame_for`;保留 `to_planes`/`pack_frame`(BWR)向后兼容。
- **改** `software/hub/inkpulse_hub/render/grid.py` — `cell_to_zone(grid, p, w=800, h=480)`。
- **改** `software/hub/inkpulse_hub/render/layouts.py` — 内置布局按 profile 分组 + profile 命名空间 API。
- **改** `software/hub/inkpulse_hub/render/engine.py` — `render_frame(cfg, state, profile=None)`。
- **改** `software/hub/inkpulse_hub/render/widgets.py` — `accent_for(state)` + 日历今天加框 + `dither` 单色。
- **改** `software/hub/inkpulse_hub/render/registry.py` — 受影响 widget 适配器传 accent / color。
- **改** `software/hub/inkpulse_hub/render/dither.py` — 加 `dither_mono`。
- **改** `software/hub/inkpulse_hub/server.py` — `/frame` 与 `/preview.png` 解析 `panel`。
- **扩展** 现有测试:`test_planes.py`、`test_grid.py`、`test_engine.py`、`test_layouts*.py`、`test_server.py`(保持原断言为 `bwr_750` 默认行为)。

向后兼容原则:所有改动函数对旧调用保留默认参数 = `bwr_750` 行为,现有测试不改断言即应继续通过。

---

## Task 1: ScreenProfile 表

**Files:**
- Create: `software/hub/inkpulse_hub/render/profiles.py`
- Test: `software/hub/tests/test_profiles.py`

- [ ] **Step 1: 写失败测试**

```python
# software/hub/tests/test_profiles.py
from inkpulse_hub.render.profiles import get_profile, PROFILES, DEFAULT_PROFILE


def test_known_profiles_exist():
    assert set(PROFILES) >= {"bwr_750", "bw_426"}


def test_bwr_750_shape():
    p = PROFILES["bwr_750"]
    assert (p.w, p.h, p.color, p.rotate) == (800, 480, "bwr", 0)
    assert (p.cols, p.rows, p.frame_bytes) == (8, 6, 96000)


def test_bw_426_shape():
    p = PROFILES["bw_426"]
    assert (p.w, p.h, p.color, p.rotate) == (480, 800, "bw", 90)
    assert (p.cols, p.rows, p.frame_bytes) == (4, 8, 48000)


def test_unknown_panel_falls_back_to_default():
    assert get_profile("nope") is DEFAULT_PROFILE
    assert get_profile(None) is DEFAULT_PROFILE
    assert DEFAULT_PROFILE.id == "bwr_750"


def test_known_panel_resolves():
    assert get_profile("bw_426").id == "bw_426"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/test_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'inkpulse_hub.render.profiles'`

- [ ] **Step 3: 写最小实现**

```python
# software/hub/inkpulse_hub/render/profiles.py
# 屏幕 profile: 把"尺寸/颜色/旋转/网格/帧字节"集中, 由设备上报的 panel id 选取。
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenProfile:
    id: str
    w: int           # 渲染画布宽(竖屏=逻辑宽)
    h: int           # 渲染画布高
    color: str       # "bwr"(双plane) | "bw"(单plane)
    rotate: int      # 渲染画布 -> 面板 的顺时针旋转角(0/90/180/270)
    cols: int        # 默认网格列
    rows: int        # 默认网格行
    frame_bytes: int # 期望帧字节(校验/文档用)


PROFILES: dict[str, ScreenProfile] = {
    "bwr_750": ScreenProfile("bwr_750", 800, 480, "bwr", 0, 8, 6, 96000),
    "bw_426":  ScreenProfile("bw_426",  480, 800, "bw",  90, 4, 8, 48000),
}

DEFAULT_PROFILE = PROFILES["bwr_750"]


def get_profile(panel_id: str | None) -> ScreenProfile:
    """按设备上报的 panel id 选 profile; 缺省/未知回退默认(bwr_750), 保证零回归。"""
    return PROFILES.get(panel_id or "", DEFAULT_PROFILE)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `./.venv/bin/pytest tests/test_profiles.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/render/profiles.py software/hub/tests/test_profiles.py
git commit -m "feat(render): ScreenProfile 表(bwr_750/bw_426)与 get_profile 回退"
```

---

## Task 2: BW 单 plane 打包 + 旋转感知 pack_frame_for

**Files:**
- Modify: `software/hub/inkpulse_hub/render/planes.py`
- Test: `software/hub/tests/test_planes.py`(追加,不改原有断言)

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 software/hub/tests/test_planes.py 末尾
from inkpulse_hub.render.planes import to_plane_bw, pack_frame_for
from inkpulse_hub.render.profiles import PROFILES


def test_bw_plane_size_and_black_bit():
    img = _img(8, 1, (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))      # 最左像素=黑
    plane = to_plane_bw(img)
    assert plane[0] == 0b10000000        # bit=1 表示黑, MSB=最左


def test_pack_frame_for_bwr_matches_legacy():
    img = _img(800, 480, (255, 255, 255))
    assert pack_frame_for(img, PROFILES["bwr_750"]) == pack_frame(img)
    assert len(pack_frame_for(img, PROFILES["bwr_750"])) == 96000


def test_pack_frame_for_bw_rotates_to_48000():
    # bw_426 渲染画布 480x800, 旋转 90 -> 800x480 -> 单 plane 48000B
    img = _img(480, 800, (255, 255, 255))
    body = pack_frame_for(img, PROFILES["bw_426"])
    assert len(body) == 48000


def test_pack_frame_for_bw_black_canvas_all_ones():
    img = _img(480, 800, (0, 0, 0))      # 全黑
    body = pack_frame_for(img, PROFILES["bw_426"])
    assert set(body) == {0xFF}           # 每 bit=1
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/bin/pytest tests/test_planes.py -v`
Expected: FAIL — `ImportError: cannot import name 'to_plane_bw'`

- [ ] **Step 3: 实现(在 planes.py 追加, 不动现有 to_planes/pack_frame)**

```python
# 追加到 software/hub/inkpulse_hub/render/planes.py
# 顶部已有: from PIL import Image; WIDTH/HEIGHT/ROW_BYTES/_BLACK/_RED 等

def to_plane_bw(img: Image.Image) -> bytes:
    """RGB(白/黑) -> 单 plane。bit=1 表示黑(非纯白即视为黑)。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    row_bytes = (w + 7) // 8
    plane = bytearray(row_bytes * h)
    px = rgb.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] != (255, 255, 255):     # 非白 -> 黑
                plane[y * row_bytes + (x >> 3)] |= 0x80 >> (x & 7)
    return bytes(plane)


def pack_frame_for(img, profile) -> bytes:
    """按 profile 旋转并打包: bwr -> black+red 双 plane; bw -> 单 plane。
    旋转方向(顺时针 profile.rotate)是面板贴装约定, 真机 bring-up 可改符号。"""
    if profile.rotate:
        img = img.rotate(-profile.rotate, expand=True)   # 负角=顺时针
    if profile.color == "bw":
        return to_plane_bw(img)
    black, red = to_planes(img)
    return black + red
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/bin/pytest tests/test_planes.py -v`
Expected: PASS(原 4 + 新 4 全过)

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/render/planes.py software/hub/tests/test_planes.py
git commit -m "feat(render): BW 单plane 打包 + 旋转感知 pack_frame_for"
```

---

## Task 3: grid.py 画布尺寸参数化

**Files:**
- Modify: `software/hub/inkpulse_hub/render/grid.py`
- Test: `software/hub/tests/test_grid.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 software/hub/tests/test_grid.py 末尾
def test_portrait_dims_4x8():
    g = {"cols": 4, "rows": 8}
    z = cell_to_zone(g, {"col": 0, "row": 0, "colspan": 4, "rowspan": 1}, 480, 800)
    assert (z.x, z.y, z.w, z.h) == (0, 0, 480, 100)
    z2 = cell_to_zone(g, {"col": 0, "row": 0, "colspan": 4, "rowspan": 8}, 480, 800)
    assert (z2.x, z2.y, z2.w, z2.h) == (0, 0, 480, 800)
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/bin/pytest tests/test_grid.py -v`
Expected: FAIL — `cell_to_zone() takes 2 positional arguments but 4 were given`

- [ ] **Step 3: 实现(改 grid.py)**

```python
# software/hub/inkpulse_hub/render/grid.py 完整替换
# 网格坐标(col/row/colspan/rowspan) -> 像素 Zone。
# 用累计 round 保证相邻格无缝相接, 即使尺寸/cols 不整除。
from .widgets import Zone


def cell_to_zone(grid: dict, p: dict, w: int = 800, h: int = 800 * 0 + 480) -> Zone:
    cols = grid["cols"]
    rows = grid["rows"]
    cw = w / cols
    ch = h / rows
    x = round(p["col"] * cw)
    y = round(p["row"] * ch)
    x2 = round((p["col"] + p["colspan"]) * cw)
    y2 = round((p["row"] + p["rowspan"]) * ch)
    return Zone(x, y, x2 - x, y2 - y)
```

> 注:默认 `w=800, h=480` 保留旧 2 参调用(test_grid 原 4 例)行为不变;`800*0+480` 仅为显式写出 480,可直接写 `h: int = 480`。

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/bin/pytest tests/test_grid.py -v`
Expected: PASS(原 4 + 新 1)

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/render/grid.py software/hub/tests/test_grid.py
git commit -m "feat(render): cell_to_zone 画布尺寸参数化(默认兼容 800x480)"
```

---

## Task 4: 内置布局按 profile 分组 + bw_426 竖版布局

**Files:**
- Modify: `software/hub/inkpulse_hub/render/layouts.py`
- Test: `software/hub/tests/test_layouts_store.py`(追加)

设计:`BUILTIN_LAYOUTS` 与 `GRIDS` 按 profile id 分组。对外 API 加可选 `profile` 参数,默认 `"bwr_750"`,使现有调用(`load_store("")`、`get_layout(path, name)`)行为不变。用户布局文件按 profile 命名空间:新格式 `{"version":2, "profiles": {pid: {"layouts": {...}}}}`;读旧扁平格式时归入 `bwr_750`。

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 software/hub/tests/test_layouts_store.py 末尾
from inkpulse_hub.render import layouts as L


def test_bw426_builtin_set_exists():
    store = L.load_store("", "bw_426")
    assert store["grid"] == {"cols": 4, "rows": 8}
    assert {"dash", "photo", "clock", "usage", "split", "todo"} <= set(store["layouts"])


def test_bw426_placements_fit_4x8():
    store = L.load_store("", "bw_426")
    for name, lay in store["layouts"].items():
        for p in lay["placements"]:
            assert p["col"] + p["colspan"] <= 4, f"{name} 越列"
            assert p["row"] + p["rowspan"] <= 8, f"{name} 越行"


def test_default_profile_still_bwr_750():
    # 旧调用签名不变: 仍返回 8x6 内置集
    store = L.load_store("")
    assert store["grid"] == {"cols": 8, "rows": 6}
    assert "dash" in store["layouts"]


def test_user_layout_namespaced_by_profile(tmp_path):
    lp = str(tmp_path / "layouts.json")
    L.save_layout(lp, "我的426", [{"widget": "todos", "col": 0, "row": 0,
                                  "colspan": 4, "rowspan": 8, "params": {}}], "bw_426")
    assert "我的426" in L.load_store(lp, "bw_426")["layouts"]
    assert "我的426" not in L.load_store(lp, "bwr_750")["layouts"]
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/bin/pytest tests/test_layouts_store.py -v`
Expected: FAIL — `load_store() takes 1 positional argument but 2 were given`

- [ ] **Step 3: 实现(改 layouts.py)**

```python
# software/hub/inkpulse_hub/render/layouts.py 完整替换
import json
import os
from copy import deepcopy

GRIDS = {
    "bwr_750": {"cols": 8, "rows": 6},
    "bw_426":  {"cols": 4, "rows": 8},
}
DEFAULT_PID = "bwr_750"


def _p(widget, col, row, colspan, rowspan, **params):
    return {"widget": widget, "col": col, "row": row,
            "colspan": colspan, "rowspan": rowspan, "params": params}


# 7.5 寸 8x6(原内置, 保持不变)
_BWR_750 = {
    "dash": {"builtin": True, "placements": [
        _p("header", 0, 0, 8, 1), _p("claude_status", 0, 1, 4, 3),
        _p("usage", 4, 1, 4, 3), _p("todos", 0, 4, 8, 2)]},
    "photo": {"builtin": True, "placements": [_p("photo", 0, 0, 8, 6)]},
    "clock": {"builtin": True, "placements": [
        _p("big_clock", 0, 0, 8, 4), _p("calendar", 1, 4, 6, 2)]},
    "usage": {"builtin": True, "placements": [
        _p("usage", 0, 0, 5, 4), _p("usage_ring", 5, 0, 3, 4),
        _p("claude_status", 0, 4, 4, 2), _p("todos", 4, 4, 4, 2)]},
    "split": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1), _p("claude_status", 0, 1, 4, 2),
        _p("usage", 0, 3, 4, 3), _p("calendar", 4, 0, 4, 3),
        _p("todos", 4, 3, 4, 3)]},
    "todo": {"builtin": True, "placements": [
        _p("todos", 0, 0, 5, 6), _p("calendar", 5, 0, 3, 3),
        _p("claude_status", 5, 3, 3, 3)]},
}

# 4.2 寸 4x8 竖版(同名, 行数合计=8)
_BW_426 = {
    "dash": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1), _p("claude_status", 0, 1, 4, 2),
        _p("usage", 0, 3, 4, 2), _p("todos", 0, 5, 4, 3)]},
    "photo": {"builtin": True, "placements": [_p("photo", 0, 0, 4, 8)]},
    "clock": {"builtin": True, "placements": [
        _p("big_clock", 0, 0, 4, 3), _p("calendar", 0, 3, 4, 3),
        _p("todos", 0, 6, 4, 2)]},
    "usage": {"builtin": True, "placements": [
        _p("usage", 0, 0, 4, 3), _p("usage_ring", 0, 3, 4, 2),
        _p("claude_status", 0, 5, 2, 3), _p("todos", 2, 5, 2, 3)]},
    "split": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1), _p("claude_status", 0, 1, 4, 2),
        _p("calendar", 0, 3, 4, 2), _p("todos", 0, 5, 4, 3)]},
    "todo": {"builtin": True, "placements": [
        _p("todos", 0, 0, 4, 5), _p("calendar", 0, 5, 4, 3)]},
}

BUILTIN_LAYOUTS = {"bwr_750": _BWR_750, "bw_426": _BW_426}


def _builtin(pid: str) -> dict:
    return BUILTIN_LAYOUTS.get(pid, _BWR_750)


def _grid(pid: str) -> dict:
    return dict(GRIDS.get(pid, GRIDS[DEFAULT_PID]))


def _load_raw(path: str) -> dict:
    """读用户文件 -> {profiles: {pid: {layouts:{...}}}}。兼容旧扁平格式(归入 bwr_750)。"""
    empty = {"version": 2, "profiles": {}}
    if not path or not os.path.exists(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return empty
    if "profiles" in data:
        return {"version": 2, "profiles": data.get("profiles") or {}}
    # 旧扁平格式 {version, grid, layouts} -> 归 bwr_750
    return {"version": 2, "profiles": {DEFAULT_PID: {"layouts": data.get("layouts", {})}}}


def load_store(path: str, profile: str = DEFAULT_PID) -> dict:
    """对外读取: 该 profile 的内置 + 用户文件合并(同名用户覆盖)。"""
    raw = _load_raw(path)
    user = (raw["profiles"].get(profile) or {}).get("layouts", {})
    merged = deepcopy(_builtin(profile))
    merged.update(user)
    return {"version": 2, "grid": _grid(profile), "layouts": merged}


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


def get_layout(path: str, name: str, profile: str = DEFAULT_PID) -> dict:
    """取某布局(含 clamp); 未知名回退 dash。返回 {grid, placements}。"""
    store = load_store(path, profile)
    lay = store["layouts"].get(name) or store["layouts"]["dash"]
    return {"grid": store["grid"], "placements": _clamp(lay["placements"], store["grid"])}


def save_layout(path: str, name: str, placements: list, profile: str = DEFAULT_PID) -> None:
    if name in _builtin(profile):
        raise ValueError("内置布局只读, 请另存为新名")
    raw = _load_raw(path)
    raw["profiles"].setdefault(profile, {}).setdefault("layouts", {})[name] = {"placements": placements}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)


def delete_layout(path: str, name: str, profile: str = DEFAULT_PID) -> None:
    if name in _builtin(profile):
        raise ValueError("内置布局不可删")
    raw = _load_raw(path)
    (raw["profiles"].get(profile) or {}).get("layouts", {}).pop(name, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 运行确认通过(含旧测试不回归)**

Run: `./.venv/bin/pytest tests/test_layouts_store.py tests/test_layouts.py tests/test_layouts_api.py -v`
Expected: PASS(若 `test_layouts_api.py` 调用 `save_layout/delete_layout` 旧签名,默认参数保证兼容;如有断言读旧文件扁平字段则按需在该测试内适配——仅当出现失败时)

> 若 `test_layouts_api.py` 因文件格式断言失败:这些断言验证的是"用户布局可存取",改为通过 `load_store(path, profile)` 验证存在性即可,不改变行为语义。

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/render/layouts.py software/hub/tests/test_layouts_store.py
git commit -m "feat(render): 内置布局按 profile 分组 + bw_426 竖版6布局 + profile 命名空间存储"
```

---

## Task 5: engine.render_frame 接受 profile

**Files:**
- Modify: `software/hub/inkpulse_hub/render/engine.py`
- Test: `software/hub/tests/test_engine.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 software/hub/tests/test_engine.py 末尾
from inkpulse_hub.render.profiles import PROFILES


def test_render_bw_426_produces_48000():
    f = render_frame(_cfg(), _state(), PROFILES["bw_426"])
    assert len(f.body) == 48000
    assert f.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_default_profile_unchanged():
    # 不传 profile = bwr_750 = 96000(零回归)
    assert len(render_frame(_cfg(), _state()).body) == 96000
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/bin/pytest tests/test_engine.py -v`
Expected: FAIL — `render_frame() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: 实现(改 engine.py)**

```python
# software/hub/inkpulse_hub/render/engine.py 完整替换
import io
import logging
from dataclasses import dataclass
from PIL import Image, ImageDraw
from ..config import Config
from .planes import pack_frame_for, frame_etag
from .grid import cell_to_zone
from .registry import REGISTRY
from . import layouts as L
from .profiles import ScreenProfile, DEFAULT_PROFILE
from .widgets import draw_na


@dataclass
class Frame:
    body: bytes
    etag: str
    png_bytes: bytes


def render_frame(cfg: Config, state: dict, profile: ScreenProfile = DEFAULT_PROFILE) -> Frame:
    img = Image.new("RGB", (profile.w, profile.h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"

    state = {**state, "color": profile.color}   # 注入颜色模型, 供 widget 降级
    layout = L.get_layout(cfg.layouts_store, cfg.layout_name, profile.id)
    for p in layout["placements"]:
        z = cell_to_zone(layout["grid"], p, profile.w, profile.h)
        spec = REGISTRY.get(p["widget"])
        if spec is None:
            draw_na(d, z)
            continue
        try:
            spec.draw(d, img, z, state, cfg, p.get("params", {}))
        except Exception as e:
            logging.getLogger("inkpulse").warning("widget %s 渲染失败: %s", p.get("widget"), e)
            draw_na(d, z)

    body = pack_frame_for(img, profile)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/bin/pytest tests/test_engine.py tests/test_layouts.py -v`
Expected: PASS(原 test_engine 4 例 + 新 2;test_layouts 的 `test_all_builtin_layouts_render_full_frame` 仍按默认 bwr_750 = 96000)

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/render/engine.py software/hub/tests/test_engine.py
git commit -m "feat(render): render_frame 接受 ScreenProfile, 默认 bwr_750 零回归"
```

---

## Task 6: /frame & /preview.png 解析 panel 参数

**Files:**
- Modify: `software/hub/inkpulse_hub/server.py`(约 25-44 行的 `frame`/`preview`)
- Test: `software/hub/tests/test_server.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 software/hub/tests/test_server.py 末尾(沿用文件已有的 TestClient 构造方式)
def test_frame_bw_426_returns_48000(client):
    r = client.get("/frame?panel=bw_426")
    assert r.status_code == 200
    assert len(r.content) == 48000


def test_frame_default_panel_returns_96000(client):
    r = client.get("/frame")
    assert r.status_code == 200
    assert len(r.content) == 96000


def test_frame_unknown_panel_falls_back(client):
    r = client.get("/frame?panel=zzz")
    assert len(r.content) == 96000


def test_preview_png_accepts_panel(client):
    r = client.get("/preview.png?panel=bw_426")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
```

> 若 `test_server.py` 现无 `client` fixture:在文件顶部加
> ```python
> import pytest
> from fastapi.testclient import TestClient
> from inkpulse_hub.server import create_app
> from inkpulse_hub.config import Config
>
> @pytest.fixture
> def client(tmp_path):
>     cfg = Config(); cfg.layouts_store = str(tmp_path / "l.json")
>     return TestClient(create_app(cfg))
> ```
> (与现有 fixture 同名则复用,不重复定义。)

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/bin/pytest tests/test_server.py -k "panel or 48000 or 96000 or preview" -v`
Expected: FAIL — 返回体长度不符 / 参数未识别

- [ ] **Step 3: 实现(改 server.py 的 frame/preview)**

在 `server.py` 顶部 import 区加:
```python
from .render.profiles import get_profile
```
把 `frame` 与 `preview` 改为:
```python
    @app.get("/frame")
    def frame(request: Request, t: float | None = None, h: float | None = None,
              rssi: int | None = None, panel: str | None = None):
        if t is not None or h is not None or rssi is not None:
            state.set_env(t, h, rssi)
        if t is not None:
            state.env_history.append(time.time(), t)
        f = render_frame(cfg, state.build_render_state(), get_profile(panel))
        if request.headers.get("if-none-match") == f.etag:
            return Response(status_code=304)
        return Response(
            content=f.body,
            media_type="application/octet-stream",
            headers={"ETag": f.etag, "X-Next-Refresh": str(cfg.refresh_periodic_s)},
        )

    @app.get("/preview.png")
    def preview(panel: str | None = None):
        f = render_frame(cfg, state.build_render_state(), get_profile(panel))
        return Response(content=f.png_bytes, media_type="image/png")
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/bin/pytest tests/test_server.py -v`
Expected: PASS(原有 + 新 4)

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/server.py software/hub/tests/test_server.py
git commit -m "feat(server): /frame 与 /preview.png 解析 panel 参数选 profile"
```

---

## Task 7: 颜色降级(BW 下红→黑 + 替代强调 + 单色照片)

**Files:**
- Modify: `software/hub/inkpulse_hub/render/widgets.py`(`draw_month_calendar`)
- Modify: `software/hub/inkpulse_hub/render/dither.py`(加 `dither_mono`)
- Modify: `software/hub/inkpulse_hub/render/registry.py`(`_calendar`、`_photo` 传 color)
- Test: `software/hub/tests/test_color_degrade.py`(新建)

设计:不改 widget 统一签名。颜色取自渲染态 `state["color"]`(engine 已注入)。新增 `widgets.accent_for(state)` 返回 `RED`(非 bw)或 `BLACK`(bw)。日历当 accent 为黑时给"今天"加方框以保留区分。照片在 bw 下用 `dither_mono`。

- [ ] **Step 1: 写失败测试**

```python
# software/hub/tests/test_color_degrade.py
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_month_calendar, accent_for, Zone, RED, BLACK
from inkpulse_hub.render.dither import dither_mono


def _img(w, h):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img); d.fontmode = "1"
    return img, d


def test_accent_for_bw_is_black():
    assert accent_for({"color": "bw"}) == BLACK
    assert accent_for({"color": "bwr"}) == RED
    assert accent_for({}) == RED          # 缺省=彩色


def test_calendar_bw_has_no_red_pixel():
    img, d = _img(400, 260)
    draw_month_calendar(d, Zone(0, 0, 400, 260), 1718000000.0, accent=BLACK)
    red = any(img.getpixel((x, y)) == (255, 0, 0)
              for x in range(400) for y in range(260))
    assert not red                         # BW 下不得出现红像素


def test_calendar_bwr_keeps_red_today():
    img, d = _img(400, 260)
    draw_month_calendar(d, Zone(0, 0, 400, 260), 1718000000.0, accent=RED)
    red = any(img.getpixel((x, y)) == (255, 0, 0)
              for x in range(400) for y in range(260))
    assert red                             # 彩色下今天仍标红


def test_dither_mono_only_bw():
    src = Image.new("RGB", (40, 40), (200, 30, 30))   # 红
    out = dither_mono(src, (40, 40))
    colors = {out.getpixel((x, y)) for x in range(40) for y in range(40)}
    assert colors <= {(0, 0, 0), (255, 255, 255)}      # 只有黑白
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/bin/pytest tests/test_color_degrade.py -v`
Expected: FAIL — `cannot import name 'accent_for'` / `dither_mono`

- [ ] **Step 3a: widgets.py 加 accent_for 并改日历**

在 `widgets.py`(`RED`/`BLACK` 常量之后)加:
```python
def accent_for(state) -> tuple:
    """渲染态颜色模型 -> 强调色。bw 用黑(配合形状区分), 否则用红。"""
    return BLACK if (state or {}).get("color") == "bw" else RED
```
找到 `draw_month_calendar` 定义,签名末尾加 `accent=RED`;把内部画"今天"用到 `RED` 的地方改用 `accent`,并在 `accent == BLACK` 时给今天格子加描边方框。示例(按现有实现微调,保持其余不变):
```python
def draw_month_calendar(d, z, now, accent=RED):
    ...
    # 原本: fill=(RED if day == today else BLACK)
    is_today = (day == today)
    fill = accent if is_today else BLACK
    d.text((tx, ty), str(day), fill=fill, font=f)
    if is_today and accent == BLACK:                 # 黑白屏: 加框替代红色
        d.rectangle((cellx + 1, celly + 1, cellx + cw - 2, celly + ch - 2), outline=BLACK)
```
> 实现者:打开 `draw_month_calendar` 现有代码,把唯一的 `RED if day == today` 三元里的 `RED` 换成参数 `accent`,并在该格补一条上面的 `rectangle` 描边(用该函数里已算出的格子坐标变量名,变量名以现有代码为准)。

- [ ] **Step 3b: dither.py 加 dither_mono**

```python
# 追加到 software/hub/inkpulse_hub/render/dither.py
def dither_mono(src: Image.Image, size: tuple[int, int]) -> Image.Image:
    """等比缩放 + Floyd–Steinberg 抖动到纯黑白, 返回 RGB。BW 屏照片用。"""
    fitted = ImageOps.contain(src.convert("RGB"), size)
    img = Image.new("RGB", size, (255, 255, 255))
    img.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return img.convert("L").convert("1").convert("RGB")
```

- [ ] **Step 3c: registry.py 适配器传 color**

```python
# _calendar 改为:
def _calendar(d, img, z, state, cfg, p):
    W.draw_month_calendar(d, z, state.get("now"), accent=W.accent_for(state))

# _photo 改为(bw 用单色抖动):
def _photo(d, img, z, state, cfg, p):
    photo = state.get("photo")
    if photo is None:
        W._center_text(d, z, "无照片", W._font(24), W.BLACK)
        return
    from .dither import dither_mono
    fn = dither_mono if state.get("color") == "bw" else dither_bwr
    im = fn(Image.open(photo.path), (z.w, z.h))
    img.paste(im, (z.x, z.y))
```
> 若 `draw_market` 等其他 widget 也用 RED 区分涨跌:同法在其适配器传 `accent=W.accent_for(state)` 并在该 draw 函数加 `accent` 参数(可选,后续按需;本任务最小集为日历+照片)。

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/bin/pytest tests/test_color_degrade.py tests/test_widgets.py tests/test_widget_*.py -v`
Expected: PASS(新测试全过;现有 widget 测试因默认 `accent=RED`/默认彩色路径不回归)

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/render/widgets.py software/hub/inkpulse_hub/render/dither.py software/hub/inkpulse_hub/render/registry.py software/hub/tests/test_color_degrade.py
git commit -m "feat(render): BW 颜色降级(日历今天加框/单色照片/accent_for)"
```

---

## Task 8: 集成校验 — bw_426 全布局出 48000B 帧

**Files:**
- Test: `software/hub/tests/test_bw426_integration.py`(新建)

- [ ] **Step 1: 写测试**

```python
# software/hub/tests/test_bw426_integration.py
from inkpulse_hub.render.engine import render_frame
from inkpulse_hub.render import layouts as L
from inkpulse_hub.render.profiles import PROFILES
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0, "rssi": -55},
        "clock": "2026-06-15 14:32 周一",
        "lunar": {"text": "农历五月初一", "festival": ""},
        "now": 1718000000.0,
    }


def test_all_bw426_layouts_render_48000_and_no_red():
    names = {"dash", "photo", "clock", "usage", "split", "todo"}
    assert names <= set(L.load_store("", "bw_426")["layouts"])
    for name in names:
        cfg = Config(); cfg.layouts_store = ""; cfg.layout_name = name
        f = render_frame(cfg, _state(), PROFILES["bw_426"])
        assert len(f.body) == 48000, f"{name} 帧大小错"
        # png 预览里不应有红(BW 降级)
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(f.png_bytes)).convert("RGB")
        assert (255, 0, 0) not in im.getcolors(maxcolors=100000) and \
            all(px != (255, 0, 0) for px in im.getdata())
```

- [ ] **Step 2: 运行**

Run: `./.venv/bin/pytest tests/test_bw426_integration.py -v`
Expected: PASS

- [ ] **Step 3: 全量回归**

Run: `./.venv/bin/pytest`
Expected: 全绿(新增用例 + 现有用例零回归)

- [ ] **Step 4: 人眼核对预览(可选但推荐)**

启动 hub 后浏览器访问 `/preview.png?panel=bw_426`(或用脚本存图),确认 480×800 竖屏六布局排版合理、无红色、文字不溢出。

- [ ] **Step 5: 提交**

```bash
git add software/hub/tests/test_bw426_integration.py
git commit -m "test(render): bw_426 全内置布局 48000B 帧 + 无红 集成校验"
```

---

## Self-Review(对照 spec)

**Spec 覆盖:**
- spec 第 3 节 ScreenProfile → Task 1 ✓
- 单/双 plane 打包 + 旋转 → Task 2 ✓
- grid 尺寸参数化 → Task 3 ✓
- 内置布局按 profile 分组 + bw_426 竖版六布局(同名)→ Task 4 ✓
- engine 按 profile 渲染 → Task 5 ✓
- /frame `&panel=` 解析 + 缺省回退 bwr_750 → Task 6 ✓
- 颜色降级(红→黑 + 加框 + 单色照片)→ Task 7 ✓
- 测试:profile/网格/打包/旋转/降级/全布局 48000B → Task 1-8 ✓
- spec 第 4 节 零回归 → 各任务保留默认参数 + 全量回归(Task 8 Step 3)✓

**占位符扫描:** 无 TBD/TODO;Task 7 Step 3a 因需就地改现有 `draw_month_calendar`,已给出改法与示例代码,变量名以现有实现为准(已标注)。

**类型一致性:** `pack_frame_for(img, profile)`、`get_layout(path,name,profile)`、`load_store(path,profile)`、`render_frame(cfg,state,profile)`、`cell_to_zone(grid,p,w,h)`、`accent_for(state)`、`get_profile(panel)` 全计划一致。

**非目标:** 不引入新 widget、不参数化控制器时序、固件运行时自动探测(见 spec 非目标)。

---

## 完成后

Plan A 全绿后进入 **Plan B(固件 ssd1677 驱动)**:Kconfig 选屏 + `ssd1677.c` 实现 `display_if_t` + URL 追加 `&panel=` + BW `mark_offline` + `ssd1677_selftest` + 真机 bring-up 校准(旋转方向/bit 极性/升压)。Plan B 含硬件核对清单(升压电容、pin6/7、结构件)。
