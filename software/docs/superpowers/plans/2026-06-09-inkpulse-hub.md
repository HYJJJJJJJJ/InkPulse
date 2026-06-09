# InkPulse Hub 实现计划（子系统①：开发机侧 Python 服务）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在开发机上构建 InkPulse Hub——采集 Claude 状态/用量、管理待办/照片，按配置把整屏渲染成 800×480 三色 (BWR) 位图，经 HTTP `/frame`(带 ETag/304) 下发给墨水屏设备，并提供待办 Web UI 与 `/preview.png` 调试图。

**Architecture:** 瘦客户端 + 本机 Hub 渲染。采集器各产出类型化数据模型 → 渲染引擎按 `config.yaml` 组合 widget 并量化为 黑/红 双 bitplane → FastAPI 提供 `/frame`、`/preview.png`、`/health`、`/ingest/claude-status`、`/todos`。设备侧固件是另一份计划。

**Tech Stack:** Python 3.11+、FastAPI、uvicorn、Pillow、PyYAML、pytest、httpx(测试用 TestClient)。

**契约（固件计划②依赖，勿改）:**
- `GET /frame`：`Content-Type: application/octet-stream`，body = `黑plane(48000B)` + `红plane(48000B)` = 96000B 固定；行主序，每行 100 字节，MSB=最左像素；**黑plane bit=1→黑，红plane bit=1→红，两者皆 0→白**（若某像素同时被判黑与红，红优先）。
- 响应头 `ETag`：帧内容哈希（强校验，带引号）。请求带 `If-None-Match` 命中 → `304 Not Modified`（无 body）。
- 响应头 `X-Next-Refresh`：建议下次拉取的秒数（整数）。
- 设备取帧时可带温湿度：query `?t=<℃float>&h=<%float>`，缺省则该项渲染为 `n/a`。

---

## 前置：约定与目录

所有路径相对仓库根 `/Users/huangyongjie/Workspace/xmut/InkPulse`。Hub 代码位于 `software/hub/`。

最终文件结构（本计划逐步建立）：
```
software/hub/
  pyproject.toml
  inkpulse_hub/
    __init__.py
    models.py            # 数据模型 dataclasses
    config.py            # config.yaml -> Config
    state.py             # 内存聚合：持有各采集器最新数据模型
    collectors/
      __init__.py
      usage.py           # 解析 ~/.claude JSONL -> Usage
      todos.py           # JSON 文件 CRUD -> list[TodoItem]
      photos.py          # 文件夹扫描选图
    render/
      __init__.py
      planes.py          # 画布像素 -> 黑/红双 bitplane + 打包 + 哈希
      dither.py          # 照片 Floyd–Steinberg 三色抖动
      widgets.py         # 各 widget 绘制函数
      engine.py          # config + state -> Frame(planes,png,etag)
    server.py            # FastAPI 应用
    web/
      todos.html         # 待办 Web UI
  hooks/
    claude_status.sh     # Claude Code hook 上报脚本
  tests/
    conftest.py
    fixtures/
    test_*.py
```

---

## Task 0: 项目脚手架与环境

**Files:**
- Create: `software/hub/pyproject.toml`
- Create: `software/hub/inkpulse_hub/__init__.py`
- Create: `software/hub/inkpulse_hub/collectors/__init__.py`
- Create: `software/hub/inkpulse_hub/render/__init__.py`
- Create: `software/hub/tests/__init__.py`
- Create: `software/hub/tests/conftest.py`

- [ ] **Step 1: 确认 conda 环境（向用户索取）**

向用户询问已配置好的 conda 环境名或路径（全局规范：禁止直接 pip 安装到 base）。后续命令均假设已 `conda activate <env>`。记录该环境名到本任务说明里。

- [ ] **Step 2: 写 `pyproject.toml`**

```toml
[project]
name = "inkpulse-hub"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pillow>=10.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["inkpulse_hub*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 建空包文件**

`inkpulse_hub/__init__.py`、`inkpulse_hub/collectors/__init__.py`、`inkpulse_hub/render/__init__.py`、`tests/__init__.py` 均写入：
```python
```
（空文件即可。）

`tests/conftest.py`：
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 4: 在 conda 环境内开发模式安装（规范允许 `pip install -e .`）**

Run: `cd software/hub && pip install -e ".[dev]"`
Expected: 安装成功，无报错。

- [ ] **Step 5: 跑空测试确认 pytest 可用**

Run: `cd software/hub && pytest -q`
Expected: `no tests ran`（退出码 5）或收集到 0 用例，无导入错误。

- [ ] **Step 6: Commit**

```bash
git add software/hub/pyproject.toml software/hub/inkpulse_hub software/hub/tests
git commit -m "chore(hub): 项目脚手架与 pytest 环境"
```

---

## Task 1: 数据模型

**Files:**
- Create: `software/hub/inkpulse_hub/models.py`
- Test: `software/hub/tests/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_models.py
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem, Photo


def test_claude_status_defaults():
    s = ClaudeStatus()
    assert s.state == "idle"
    assert s.project is None
    assert s.needs_attention() is False


def test_claude_status_attention_states():
    assert ClaudeStatus(state="waiting_for_input").needs_attention() is True
    assert ClaudeStatus(state="error").needs_attention() is True
    assert ClaudeStatus(state="working").needs_attention() is False


def test_usage_and_todo_and_photo():
    u = Usage(input_tokens=10, output_tokens=5, cost_usd=0.0, session_count=1, window_used_ratio=0.5)
    assert u.total_tokens() == 15
    t = TodoItem(id="a1", text="买菜", done=False)
    assert t.text == "买菜" and t.done is False
    p = Photo(path="/x/a.jpg")
    assert p.path.endswith("a.jpg")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_models.py -q`
Expected: FAIL（`ModuleNotFoundError: inkpulse_hub.models`）

- [ ] **Step 3: 实现 `models.py`**

```python
# inkpulse_hub/models.py
from dataclasses import dataclass
from typing import Optional

ATTENTION_STATES = {"waiting_for_input", "error"}
VALID_STATES = {"idle", "working", "waiting_for_input", "done", "error"}


@dataclass
class ClaudeStatus:
    state: str = "idle"
    project: Optional[str] = None
    since: Optional[float] = None  # epoch 秒

    def needs_attention(self) -> bool:
        return self.state in ATTENTION_STATES


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost_usd: float = 0.0
    session_count: int = 0
    window_used_ratio: Optional[float] = None  # 0..1，None 表示 n/a

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TodoItem:
    id: str
    text: str
    done: bool = False


@dataclass
class Photo:
    path: str
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_models.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/models.py software/hub/tests/test_models.py
git commit -m "feat(hub): 数据模型 ClaudeStatus/Usage/TodoItem/Photo"
```

---

## Task 2: 像素→双 bitplane 打包与哈希

**Files:**
- Create: `software/hub/inkpulse_hub/render/planes.py`
- Test: `software/hub/tests/test_planes.py`

约定：输入是 Pillow RGB 图像，仅含三色：白(255,255,255)/黑(0,0,0)/红(255,0,0)。输出两个 plane 字节串。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_planes.py
from PIL import Image
from inkpulse_hub.render.planes import to_planes, pack_frame, frame_etag


def _img(w, h, color):
    return Image.new("RGB", (w, h), color)


def test_plane_sizes_for_full_resolution():
    img = _img(800, 480, (255, 255, 255))
    black, red = to_planes(img)
    assert len(black) == 48000 and len(red) == 48000


def test_black_pixel_sets_black_plane_msb():
    img = _img(8, 1, (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))  # 最左像素=黑
    black, red = to_planes(img)
    assert black[0] == 0b10000000  # MSB=最左
    assert red[0] == 0b00000000


def test_red_pixel_sets_red_plane_only():
    img = _img(8, 1, (255, 255, 255))
    img.putpixel((1, 0), (255, 0, 0))
    black, red = to_planes(img)
    assert black[0] == 0b00000000
    assert red[0] == 0b01000000  # 左数第二像素


def test_pack_and_etag_stable():
    img = _img(800, 480, (255, 255, 255))
    body = pack_frame(img)
    assert len(body) == 96000
    assert frame_etag(body) == frame_etag(pack_frame(_img(800, 480, (255, 255, 255))))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_planes.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `planes.py`**

```python
# inkpulse_hub/render/planes.py
import hashlib
from PIL import Image

WIDTH, HEIGHT = 800, 480
ROW_BYTES = WIDTH // 8          # 100
PLANE_BYTES = ROW_BYTES * HEIGHT  # 48000

_BLACK = (0, 0, 0)
_RED = (255, 0, 0)


def to_planes(img: Image.Image) -> tuple[bytes, bytes]:
    """RGB(仅白/黑/红) -> (黑plane, 红plane)。bit=1 表示该色;红优先。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    row_bytes = (w + 7) // 8
    black = bytearray(row_bytes * h)
    red = bytearray(row_bytes * h)
    px = rgb.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            byte_i = y * row_bytes + (x >> 3)
            bit = 0x80 >> (x & 7)
            if p == _RED:
                red[byte_i] |= bit
            elif p == _BLACK:
                black[byte_i] |= bit
    return bytes(black), bytes(red)


def pack_frame(img: Image.Image) -> bytes:
    black, red = to_planes(img)
    return black + red


def frame_etag(body: bytes) -> str:
    return '"' + hashlib.sha1(body).hexdigest() + '"'
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_planes.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/render/planes.py software/hub/tests/test_planes.py
git commit -m "feat(hub): 像素到黑/红双bitplane打包与ETag哈希"
```

---

## Task 3: 配置加载

**Files:**
- Create: `software/hub/inkpulse_hub/config.py`
- Create: `software/hub/config.example.yaml`
- Test: `software/hub/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
from inkpulse_hub.config import load_config, Config


def test_defaults_when_empty(tmp_path):
    cfg = load_config(None)
    assert isinstance(cfg, Config)
    assert cfg.refresh_min_interval_s == 60
    assert cfg.refresh_periodic_s == 600
    assert cfg.layout == ["header_clock_env", "claude_status", "usage", "todos"]


def test_yaml_override(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "refresh:\n  min_interval_s: 30\n"
        "sources:\n  photos_dir: /tmp/pics\n"
        "layout:\n  widgets: [claude_status]\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.refresh_min_interval_s == 30
    assert cfg.photos_dir == "/tmp/pics"
    assert cfg.layout == ["claude_status"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_config.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `config.py`**

```python
# inkpulse_hub/config.py
import os
from dataclasses import dataclass, field
from typing import Optional
import yaml

DEFAULT_LAYOUT = ["header_clock_env", "claude_status", "usage", "todos"]


@dataclass
class Config:
    refresh_min_interval_s: int = 60
    refresh_periodic_s: int = 600
    claude_logs: str = os.path.expanduser("~/.claude/projects")
    photos_dir: str = os.path.expanduser("~/inkpulse/photos")
    todos_store: str = os.path.expanduser("~/inkpulse/todos.json")
    layout: list[str] = field(default_factory=lambda: list(DEFAULT_LAYOUT))


def load_config(path: Optional[str]) -> Config:
    cfg = Config()
    if not path or not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    refresh = data.get("refresh", {})
    cfg.refresh_min_interval_s = refresh.get("min_interval_s", cfg.refresh_min_interval_s)
    cfg.refresh_periodic_s = refresh.get("periodic_s", cfg.refresh_periodic_s)
    sources = data.get("sources", {})
    cfg.claude_logs = os.path.expanduser(sources.get("claude_logs", cfg.claude_logs))
    cfg.photos_dir = os.path.expanduser(sources.get("photos_dir", cfg.photos_dir))
    cfg.todos_store = os.path.expanduser(sources.get("todos_store", cfg.todos_store))
    layout = data.get("layout", {})
    cfg.layout = layout.get("widgets", cfg.layout)
    return cfg
```

- [ ] **Step 4: 写 `config.example.yaml`**

```yaml
refresh:
  min_interval_s: 60
  periodic_s: 600
sources:
  claude_logs: ~/.claude/projects
  photos_dir: ~/inkpulse/photos
  todos_store: ~/inkpulse/todos.json
layout:
  widgets: [header_clock_env, claude_status, usage, todos]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_config.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add software/hub/inkpulse_hub/config.py software/hub/config.example.yaml software/hub/tests/test_config.py
git commit -m "feat(hub): config.yaml 加载与默认值"
```

---

## Task 4: 待办 JSON 存储（CRUD）

**Files:**
- Create: `software/hub/inkpulse_hub/collectors/todos.py`
- Test: `software/hub/tests/test_todos.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_todos.py
from inkpulse_hub.collectors.todos import TodoStore


def test_add_list_toggle_delete(tmp_path):
    store = TodoStore(str(tmp_path / "todos.json"))
    item = store.add("写固件")
    assert item.text == "写固件" and item.done is False
    assert [t.text for t in store.list()] == ["写固件"]

    store.toggle(item.id)
    assert store.list()[0].done is True

    store.delete(item.id)
    assert store.list() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "todos.json")
    TodoStore(path).add("持久化")
    assert [t.text for t in TodoStore(path).list()] == ["持久化"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_todos.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `collectors/todos.py`**

```python
# inkpulse_hub/collectors/todos.py
import json
import os
import uuid
from ..models import TodoItem


class TodoStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self) -> list[TodoItem]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [TodoItem(**d) for d in raw]

    def _write(self, items: list[TodoItem]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([t.__dict__ for t in items], f, ensure_ascii=False, indent=2)

    def list(self) -> list[TodoItem]:
        return self._read()

    def add(self, text: str) -> TodoItem:
        items = self._read()
        item = TodoItem(id=uuid.uuid4().hex[:8], text=text, done=False)
        items.append(item)
        self._write(items)
        return item

    def toggle(self, item_id: str) -> None:
        items = self._read()
        for t in items:
            if t.id == item_id:
                t.done = not t.done
        self._write(items)

    def delete(self, item_id: str) -> None:
        self._write([t for t in self._read() if t.id != item_id])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_todos.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/collectors/todos.py software/hub/tests/test_todos.py
git commit -m "feat(hub): 待办JSON存储CRUD"
```

---

## Task 5: 用量采集器（解析 Claude 会话日志）

**Files:**
- Create: `software/hub/inkpulse_hub/collectors/usage.py`
- Create: `software/hub/tests/fixtures/session_sample.jsonl`
- Test: `software/hub/tests/test_usage.py`

> 注：订阅日志为每行一个 JSON 的 `.jsonl`，assistant 消息含 `message.usage.{input_tokens,output_tokens,cache_read_input_tokens}`。真实字段在 bring-up 阶段对照 `~/.claude` 核实（见 spec §12）；本任务先按此结构实现并用 fixture 锁定行为，字段缺失须容错。

- [ ] **Step 1: 造 fixture `tests/fixtures/session_sample.jsonl`**

```jsonl
{"type":"user","message":{"role":"user"}}
{"type":"assistant","message":{"role":"assistant","usage":{"input_tokens":100,"output_tokens":40,"cache_read_input_tokens":10}}}
{"type":"assistant","message":{"role":"assistant","usage":{"input_tokens":60,"output_tokens":20}}}
{"broken line not json}
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_usage.py
import shutil
from pathlib import Path
from inkpulse_hub.collectors.usage import collect_usage


def _setup_logs(tmp_path) -> str:
    proj = tmp_path / "proj"
    proj.mkdir()
    src = Path(__file__).parent / "fixtures" / "session_sample.jsonl"
    shutil.copy(src, proj / "session_sample.jsonl")
    return str(tmp_path)


def test_collect_usage_sums_tokens_and_tolerates_garbage(tmp_path):
    u = collect_usage(_setup_logs(tmp_path))
    assert u.input_tokens == 160
    assert u.output_tokens == 60
    assert u.cache_tokens == 10
    assert u.total_tokens() == 220
    assert u.session_count == 1


def test_missing_dir_returns_zero_usage(tmp_path):
    u = collect_usage(str(tmp_path / "nope"))
    assert u.total_tokens() == 0
    assert u.session_count == 0
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_usage.py -q`
Expected: FAIL

- [ ] **Step 4: 实现 `collectors/usage.py`**

```python
# inkpulse_hub/collectors/usage.py
import glob
import json
import os
from ..models import Usage


def collect_usage(logs_dir: str) -> Usage:
    u = Usage()
    if not os.path.isdir(logs_dir):
        return u
    files = glob.glob(os.path.join(logs_dir, "**", "*.jsonl"), recursive=True)
    u.session_count = len(files)
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # 容错：坏行跳过
                    usage = (rec.get("message") or {}).get("usage")
                    if not isinstance(usage, dict):
                        continue
                    u.input_tokens += int(usage.get("input_tokens", 0) or 0)
                    u.output_tokens += int(usage.get("output_tokens", 0) or 0)
                    u.cache_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
        except OSError:
            continue
    return u
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_usage.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add software/hub/inkpulse_hub/collectors/usage.py software/hub/tests/test_usage.py software/hub/tests/fixtures/session_sample.jsonl
git commit -m "feat(hub): 用量采集器解析会话日志(含坏行容错)"
```

---

## Task 6: 照片采集器与三色抖动

**Files:**
- Create: `software/hub/inkpulse_hub/collectors/photos.py`
- Create: `software/hub/inkpulse_hub/render/dither.py`
- Test: `software/hub/tests/test_photos.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_photos.py
from PIL import Image
from inkpulse_hub.collectors.photos import pick_photo
from inkpulse_hub.render.dither import dither_bwr


def test_pick_photo_none_when_empty(tmp_path):
    assert pick_photo(str(tmp_path)) is None


def test_pick_photo_returns_image_file(tmp_path):
    f = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (120, 0, 0)).save(f)
    p = pick_photo(str(tmp_path))
    assert p is not None and p.path.endswith("a.png")


def test_dither_outputs_only_three_colors():
    src = Image.new("RGB", (16, 16), (200, 40, 40))  # 偏红的灰
    out = dither_bwr(src, (16, 16))
    colors = {px for px in out.getdata()}
    assert colors <= {(255, 255, 255), (0, 0, 0), (255, 0, 0)}
    assert out.size == (16, 16)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_photos.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `render/dither.py`**

```python
# inkpulse_hub/render/dither.py
from PIL import Image

# 三色调色板：白/黑/红
_PALETTE_RGB = [(255, 255, 255), (0, 0, 0), (255, 0, 0)]


def _palette_image() -> Image.Image:
    pal = Image.new("P", (1, 1))
    flat = []
    for c in _PALETTE_RGB:
        flat += list(c)
    flat += [0, 0, 0] * (256 - len(_PALETTE_RGB))
    pal.putpalette(flat)
    return pal


def dither_bwr(src: Image.Image, size: tuple[int, int]) -> Image.Image:
    """缩放并以 Floyd–Steinberg 抖动量化到 白/黑/红 三色，返回 RGB 图。"""
    img = src.convert("RGB").resize(size)
    quant = img.quantize(palette=_palette_image(), dither=Image.FLOYDSTEINBERG)
    return quant.convert("RGB")
```

- [ ] **Step 4: 实现 `collectors/photos.py`**

```python
# inkpulse_hub/collectors/photos.py
import glob
import os
from typing import Optional
from ..models import Photo

_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif")


def pick_photo(photos_dir: str) -> Optional[Photo]:
    if not os.path.isdir(photos_dir):
        return None
    files: list[str] = []
    for pat in _EXTS:
        files += glob.glob(os.path.join(photos_dir, pat))
    if not files:
        return None
    files.sort()
    return Photo(path=files[0])  # v1 取首张;轮换策略后续接 refresh tick
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_photos.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add software/hub/inkpulse_hub/collectors/photos.py software/hub/inkpulse_hub/render/dither.py software/hub/tests/test_photos.py
git commit -m "feat(hub): 照片采集器与三色Floyd-Steinberg抖动"
```

---

## Task 7: Widget 绘制函数

**Files:**
- Create: `software/hub/inkpulse_hub/render/widgets.py`
- Test: `software/hub/tests/test_widgets.py`

约定：每个 widget 是纯函数 `draw_xxx(draw: ImageDraw, zone: Zone, data) -> None`，在给定矩形区域内绘制；只用黑(0,0,0)/红(255,0,0)。测试通过"区域内非白像素数 > 0"和"红色仅在预期 widget 出现"来验证，避免脆弱的像素级文字断言。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_widgets.py
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import Zone, draw_claude_status, draw_usage, draw_todos, draw_header
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _canvas():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    return img, ImageDraw.Draw(img)


def _nonwhite_count(img, zone):
    cnt = 0
    for y in range(zone.y, zone.y + zone.h):
        for x in range(zone.x, zone.x + zone.w):
            if img.getpixel((x, y)) != (255, 255, 255):
                cnt += 1
    return cnt


def test_status_draws_something():
    img, d = _canvas()
    z = Zone(0, 60, 480, 200)
    draw_claude_status(d, z, ClaudeStatus(state="working", project="InkPulse"))
    assert _nonwhite_count(img, z) > 0


def test_attention_state_uses_red():
    img, d = _canvas()
    z = Zone(0, 60, 480, 200)
    draw_claude_status(d, z, ClaudeStatus(state="error"))
    reds = sum(1 for p in img.getdata() if p == (255, 0, 0))
    assert reds > 0


def test_idle_state_no_red():
    img, d = _canvas()
    draw_claude_status(d, Zone(0, 60, 480, 200), ClaudeStatus(state="working"))
    assert all(p != (255, 0, 0) for p in img.getdata())


def test_usage_and_todos_and_header_draw():
    img, d = _canvas()
    draw_usage(d, Zone(480, 60, 320, 200), Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.5))
    draw_todos(d, Zone(0, 260, 800, 220), [TodoItem("a", "x", False), TodoItem("b", "y", True)])
    draw_header(d, Zone(0, 0, 800, 60), "6/9 周一 14:32", temp=22.0, humidity=55.0)
    assert _nonwhite_count(img, Zone(480, 60, 320, 200)) > 0
    assert _nonwhite_count(img, Zone(0, 260, 800, 220)) > 0
    assert _nonwhite_count(img, Zone(0, 0, 800, 60)) > 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_widgets.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `render/widgets.py`**

```python
# inkpulse_hub/render/widgets.py
from dataclasses import dataclass
from PIL import ImageDraw, ImageFont
from ..models import ClaudeStatus, Usage, TodoItem

BLACK = (0, 0, 0)
RED = (255, 0, 0)

STATE_LABEL = {
    "idle": "空闲",
    "working": "工作中",
    "waiting_for_input": "等你输入",
    "done": "刚完成",
    "error": "出错",
}


@dataclass
class Zone:
    x: int
    y: int
    w: int
    h: int


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def draw_header(d: ImageDraw.ImageDraw, z: Zone, clock_text: str, temp, humidity) -> None:
    f = _font(22)
    d.text((z.x + 6, z.y + 8), clock_text, fill=BLACK, font=f)
    t = f"{temp:.0f}C" if temp is not None else "n/a"
    h = f"{humidity:.0f}%" if humidity is not None else "n/a"
    d.text((z.x + z.w - 160, z.y + 8), f"{t}  {h}", fill=BLACK, font=f)
    d.line((z.x, z.y + z.h - 1, z.x + z.w, z.y + z.h - 1), fill=BLACK, width=1)


def draw_claude_status(d: ImageDraw.ImageDraw, z: Zone, s: ClaudeStatus) -> None:
    big = _font(48)
    small = _font(22)
    color = RED if s.needs_attention() else BLACK
    # 状态色指示块：不依赖字体字形(默认字体可能缺中文)，保证状态色一定可见
    d.rectangle((z.x + 12, z.y + 24, z.x + 36, z.y + 48), fill=color)
    label = STATE_LABEL.get(s.state, s.state)
    d.text((z.x + 48, z.y + 20), label, fill=color, font=big)
    proj = f"project: {s.project}" if s.project else "-"
    d.text((z.x + 12, z.y + 90), proj, fill=BLACK, font=small)


def draw_usage(d: ImageDraw.ImageDraw, z: Zone, u: Usage) -> None:
    f = _font(22)
    d.text((z.x + 8, z.y + 8), "今日用量", fill=BLACK, font=f)
    d.text((z.x + 8, z.y + 40), f"{u.total_tokens()} tok", fill=BLACK, font=f)
    d.text((z.x + 8, z.y + 72), f"≈ ${u.cost_usd:.2f}", fill=BLACK, font=f)
    if u.window_used_ratio is not None:
        bx, by, bw, bh = z.x + 8, z.y + 110, z.w - 24, 18
        d.rectangle((bx, by, bx + bw, by + bh), outline=BLACK, width=1)
        fillw = int(bw * max(0.0, min(1.0, u.window_used_ratio)))
        d.rectangle((bx, by, bx + fillw, by + bh), fill=BLACK)
    else:
        d.text((z.x + 8, z.y + 110), "窗口 n/a", fill=BLACK, font=f)


def draw_todos(d: ImageDraw.ImageDraw, z: Zone, items: list[TodoItem]) -> None:
    f = _font(22)
    y = z.y + 6
    for t in items[:4]:
        box = "[x]" if t.done else "[ ]"
        d.text((z.x + 8, y), f"{box} {t.text}", fill=BLACK, font=f)
        y += 34
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_widgets.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/render/widgets.py software/hub/tests/test_widgets.py
git commit -m "feat(hub): widget绘制函数(状态/用量/待办/顶栏)"
```

---

## Task 8: 渲染引擎（config + 数据 → Frame）

**Files:**
- Create: `software/hub/inkpulse_hub/render/engine.py`
- Test: `software/hub/tests/test_engine.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_engine.py
from inkpulse_hub.render.engine import render_frame, Frame
from inkpulse_hub.config import Config
from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem


def _state():
    return {
        "claude": ClaudeStatus(state="working", project="InkPulse"),
        "usage": Usage(input_tokens=1000, output_tokens=200, window_used_ratio=0.4),
        "todos": [TodoItem("a", "写固件", False)],
        "photo": None,
        "env": {"temp": 22.0, "humidity": 55.0},
        "clock": "6/9 14:32",
    }


def test_render_produces_full_frame():
    f = render_frame(Config(), _state())
    assert isinstance(f, Frame)
    assert len(f.body) == 96000
    assert f.etag.startswith('"')
    assert f.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_same_input_same_etag():
    a = render_frame(Config(), _state())
    b = render_frame(Config(), _state())
    assert a.etag == b.etag


def test_missing_data_falls_back_not_crash():
    state = _state()
    state["usage"] = Usage()          # 空用量
    state["env"] = {"temp": None, "humidity": None}
    f = render_frame(Config(), state)  # 不应抛异常
    assert len(f.body) == 96000
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_engine.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `render/engine.py`**

```python
# inkpulse_hub/render/engine.py
import io
from dataclasses import dataclass
from PIL import Image
from ..config import Config
from .planes import pack_frame, frame_etag, WIDTH, HEIGHT
from .dither import dither_bwr
from . import widgets as W


@dataclass
class Frame:
    body: bytes       # 96000B 双 plane
    etag: str
    png_bytes: bytes  # /preview.png 用


# 默认布局各 widget 的固定分区
ZONES = {
    "header_clock_env": W.Zone(0, 0, WIDTH, 60),
    "claude_status": W.Zone(0, 60, 480, 200),
    "usage": W.Zone(480, 60, 320, 200),
    "todos": W.Zone(0, 260, WIDTH, 220),
    "photo": W.Zone(0, 0, WIDTH, HEIGHT),  # 全屏照片布局
}


def render_frame(cfg: Config, state: dict) -> Frame:
    img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))

    if cfg.layout == ["photo"] and state.get("photo") is not None:
        photo = dither_bwr(Image.open(state["photo"].path), (WIDTH, HEIGHT))
        img.paste(photo, (0, 0))
    else:
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        for name in cfg.layout:
            z = ZONES.get(name)
            if z is None:
                continue
            if name == "header_clock_env":
                env = state.get("env", {})
                W.draw_header(d, z, state.get("clock", ""), env.get("temp"), env.get("humidity"))
            elif name == "claude_status":
                W.draw_claude_status(d, z, state["claude"])
            elif name == "usage":
                W.draw_usage(d, z, state["usage"])
            elif name == "todos":
                W.draw_todos(d, z, state.get("todos", []))

    body = pack_frame(img)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    return Frame(body=body, etag=frame_etag(body), png_bytes=png_buf.getvalue())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_engine.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/render/engine.py software/hub/tests/test_engine.py
git commit -m "feat(hub): 渲染引擎(config驱动布局->Frame)"
```

---

## Task 9: 内存状态聚合 + 时钟

**Files:**
- Create: `software/hub/inkpulse_hub/state.py`
- Test: `software/hub/tests/test_state.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_state.py
import time
from inkpulse_hub.state import HubState
from inkpulse_hub.config import Config


def test_state_builds_render_dict(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "nolog"),
                 photos_dir=str(tmp_path / "nopics"),
                 todos_store=str(tmp_path / "todos.json"))
    st = HubState(cfg)
    st.set_claude_status("working", project="InkPulse")
    st.add_todo("买菜")
    d = st.build_render_state(now=time.mktime((2026, 6, 9, 14, 32, 0, 0, 0, -1)))
    assert d["claude"].state == "working"
    assert d["claude"].project == "InkPulse"
    assert [t.text for t in d["todos"]] == ["买菜"]
    assert "14:32" in d["clock"]
    assert d["usage"].total_tokens() == 0  # 无日志 -> 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_state.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `state.py`**

```python
# inkpulse_hub/state.py
import time
from typing import Optional
from .config import Config
from .models import ClaudeStatus
from .collectors.todos import TodoStore
from .collectors.usage import collect_usage
from .collectors.photos import pick_photo

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class HubState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.claude = ClaudeStatus()
        self.todos = TodoStore(cfg.todos_store)
        self.env = {"temp": None, "humidity": None}

    def set_claude_status(self, state: str, project: Optional[str] = None) -> None:
        self.claude = ClaudeStatus(state=state, project=project, since=time.time())

    def set_env(self, temp, humidity) -> None:
        self.env = {"temp": temp, "humidity": humidity}

    def add_todo(self, text: str):
        return self.todos.add(text)

    def _clock(self, now: float) -> str:
        lt = time.localtime(now)
        return f"{lt.tm_mon}/{lt.tm_mday} {_WEEKDAYS[lt.tm_wday]} {lt.tm_hour:02d}:{lt.tm_min:02d}"

    def build_render_state(self, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        return {
            "claude": self.claude,
            "usage": collect_usage(self.cfg.claude_logs),
            "todos": self.todos.list(),
            "photo": pick_photo(self.cfg.photos_dir),
            "env": dict(self.env),
            "clock": self._clock(now),
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_state.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/state.py software/hub/tests/test_state.py
git commit -m "feat(hub): 内存状态聚合HubState + 时钟格式化"
```

---

## Task 10: FastAPI 服务（/frame、/preview.png、/health、/ingest）

**Files:**
- Create: `software/hub/inkpulse_hub/server.py`
- Test: `software/hub/tests/test_server.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_server.py
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"))
    return TestClient(create_app(cfg))


def test_health(tmp_path):
    assert _client(tmp_path).get("/health").json() == {"ok": True}


def test_frame_returns_binary_with_etag_and_next_refresh(tmp_path):
    c = _client(tmp_path)
    r = c.get("/frame")
    assert r.status_code == 200
    assert len(r.content) == 96000
    assert r.headers["etag"].startswith('"')
    assert int(r.headers["x-next-refresh"]) > 0


def test_frame_304_when_if_none_match(tmp_path):
    c = _client(tmp_path)
    etag = c.get("/frame").headers["etag"]
    r = c.get("/frame", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.content == b""


def test_frame_accepts_env_query(tmp_path):
    c = _client(tmp_path)
    r = c.get("/frame", params={"t": 22.5, "h": 60})
    assert r.status_code == 200


def test_ingest_claude_status_updates_frame(tmp_path):
    c = _client(tmp_path)
    before = c.get("/frame").headers["etag"]
    assert c.post("/ingest/claude-status", json={"state": "error", "project": "X"}).json()["ok"]
    after = c.get("/frame").headers["etag"]
    assert before != after
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_server.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `server.py`（含 /frame、/preview.png、/health、/ingest；/todos 在 Task 11 补）**

```python
# inkpulse_hub/server.py
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from .config import Config
from .state import HubState
from .render.engine import render_frame


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="InkPulse Hub")
    state = HubState(cfg)
    app.state.hub = state
    app.state.cfg = cfg

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/frame")
    def frame(request: Request, t: float | None = None, h: float | None = None):
        if t is not None or h is not None:
            state.set_env(t, h)
        f = render_frame(cfg, state.build_render_state())
        if request.headers.get("if-none-match") == f.etag:
            return Response(status_code=304)
        return Response(
            content=f.body,
            media_type="application/octet-stream",
            headers={"ETag": f.etag, "X-Next-Refresh": str(cfg.refresh_periodic_s)},
        )

    @app.get("/preview.png")
    def preview():
        f = render_frame(cfg, state.build_render_state())
        return Response(content=f.png_bytes, media_type="image/png")

    @app.post("/ingest/claude-status")
    async def ingest(request: Request):
        data = await request.json()
        state.set_claude_status(data.get("state", "idle"), data.get("project"))
        return JSONResponse({"ok": True})

    return app
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_server.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add software/hub/inkpulse_hub/server.py software/hub/tests/test_server.py
git commit -m "feat(hub): FastAPI服务/frame(ETag+304)//preview.png//health//ingest"
```

---

## Task 11: 待办 Web UI（页面 + CRUD 端点）

**Files:**
- Create: `software/hub/inkpulse_hub/web/todos.html`
- Modify: `software/hub/inkpulse_hub/server.py`（追加 `/todos` 路由）
- Test: `software/hub/tests/test_todos_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_todos_api.py
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"))
    return TestClient(create_app(cfg))


def test_todos_page_served(tmp_path):
    r = _client(tmp_path).get("/todos")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_todos_crud_api(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/todos").json() == []
    created = c.post("/api/todos", json={"text": "写计划"}).json()
    tid = created["id"]
    assert [x["text"] for x in c.get("/api/todos").json()] == ["写计划"]
    c.post(f"/api/todos/{tid}/toggle")
    assert c.get("/api/todos").json()[0]["done"] is True
    c.delete(f"/api/todos/{tid}")
    assert c.get("/api/todos").json() == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_todos_api.py -q`
Expected: FAIL

- [ ] **Step 3: 写 `web/todos.html`**

```html
<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>InkPulse 待办</title>
<style>body{font-family:sans-serif;max-width:480px;margin:2rem auto;padding:0 1rem}
li{display:flex;align-items:center;gap:.5rem;margin:.4rem 0}.done span{text-decoration:line-through;color:#999}
input[type=text]{flex:1;padding:.5rem}button{padding:.4rem .6rem}</style></head>
<body><h2>待办</h2>
<form id="f"><input type="text" id="t" placeholder="添加待办…" autofocus><button>加</button></form>
<ul id="list"></ul>
<script>
async function load(){const r=await fetch('/api/todos');const items=await r.json();
const ul=document.getElementById('list');ul.innerHTML='';
for(const it of items){const li=document.createElement('li');if(it.done)li.className='done';
li.innerHTML=`<input type=checkbox ${it.done?'checked':''}><span>${it.text}</span><button>×</button>`;
li.querySelector('input').onclick=async()=>{await fetch(`/api/todos/${it.id}/toggle`,{method:'POST'});load();};
li.querySelector('button').onclick=async()=>{await fetch(`/api/todos/${it.id}`,{method:'DELETE'});load();};
ul.appendChild(li);}}
document.getElementById('f').onsubmit=async(e)=>{e.preventDefault();const t=document.getElementById('t');
if(!t.value.trim())return;await fetch('/api/todos',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({text:t.value.trim()})});t.value='';load();};
load();
</script></body></html>
```

- [ ] **Step 4: 在 `server.py` 的 `create_app` 内、`return app` 之前追加路由**

```python
    # ---- 待办 Web UI 与 API ----
    import os
    from fastapi.responses import HTMLResponse

    _html_path = os.path.join(os.path.dirname(__file__), "web", "todos.html")

    @app.get("/todos", response_class=HTMLResponse)
    def todos_page():
        with open(_html_path, "r", encoding="utf-8") as fh:
            return HTMLResponse(fh.read())

    @app.get("/api/todos")
    def api_list():
        return [t.__dict__ for t in state.todos.list()]

    @app.post("/api/todos")
    async def api_add(request: Request):
        data = await request.json()
        return state.todos.add(data["text"]).__dict__

    @app.post("/api/todos/{tid}/toggle")
    def api_toggle(tid: str):
        state.todos.toggle(tid)
        return {"ok": True}

    @app.delete("/api/todos/{tid}")
    def api_delete(tid: str):
        state.todos.delete(tid)
        return {"ok": True}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_todos_api.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add software/hub/inkpulse_hub/web/todos.html software/hub/inkpulse_hub/server.py software/hub/tests/test_todos_api.py
git commit -m "feat(hub): 待办Web UI与CRUD API"
```

---

## Task 12: 入口、Hook 脚本、运行说明

**Files:**
- Create: `software/hub/inkpulse_hub/__main__.py`
- Create: `software/hub/hooks/claude_status.sh`
- Create: `software/hub/README.md`
- Test: `software/hub/tests/test_main.py`

- [ ] **Step 1: 写失败测试（入口可构建 app）**

```python
# tests/test_main.py
from inkpulse_hub.__main__ import build
from fastapi import FastAPI


def test_build_returns_app(tmp_path, monkeypatch):
    monkeypatch.setenv("INKPULSE_CONFIG", str(tmp_path / "noexist.yaml"))
    app = build()
    assert isinstance(app, FastAPI)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd software/hub && pytest tests/test_main.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 `__main__.py`**

```python
# inkpulse_hub/__main__.py
import os
from .config import load_config
from .server import create_app


def build():
    cfg = load_config(os.environ.get("INKPULSE_CONFIG"))
    return create_app(cfg)


def main():
    import uvicorn
    uvicorn.run(build(), host="0.0.0.0", port=int(os.environ.get("INKPULSE_PORT", "8080")))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd software/hub && pytest tests/test_main.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 写 Hook 脚本 `hooks/claude_status.sh`**

```bash
#!/usr/bin/env bash
# Claude Code hook：把状态上报给 InkPulse Hub。
# 用法：在 ~/.claude/settings.json 的 hooks 中调用，传入状态名作为 $1。
# 例：claude_status.sh working / waiting_for_input / done / error
HUB="${INKPULSE_HUB:-http://127.0.0.1:8080}"
STATE="${1:-idle}"
PROJECT="$(basename "$PWD")"
curl -s -m 2 -X POST "$HUB/ingest/claude-status" \
  -H 'Content-Type: application/json' \
  -d "{\"state\":\"$STATE\",\"project\":\"$PROJECT\"}" >/dev/null 2>&1 || true
```

- [ ] **Step 6: 写 `README.md`**

````markdown
# InkPulse Hub

开发机侧服务：采集 Claude 状态/用量、管理待办/照片，渲染 800×480 三色位图供墨水屏拉取。

## 运行
```bash
conda activate <你的环境>
cd software/hub
pip install -e ".[dev]"
cp config.example.yaml ~/inkpulse-config.yaml   # 按需修改
INKPULSE_CONFIG=~/inkpulse-config.yaml python -m inkpulse_hub
```
- 调布局：浏览器打开 `http://<本机IP>:8080/preview.png`
- 待办：`http://<本机IP>:8080/todos`（手机连同一局域网也能加）
- 设备取帧：`GET /frame`

## 接 Claude Code 状态（hooks）
把 `hooks/claude_status.sh` 接到 `~/.claude/settings.json` 的相应 hook，
在 SessionStart→working、Stop→done、Notification→waiting_for_input 等时机调用并传入状态名。
设 `INKPULSE_HUB` 指向 Hub 地址（默认 `http://127.0.0.1:8080`）。

## 测试
```bash
pytest -q
```
````

- [ ] **Step 7: 跑全量测试**

Run: `cd software/hub && pytest -q`
Expected: 全部 PASS。

- [ ] **Step 8: 手工冒烟（可选但建议）**

Run: `cd software/hub && INKPULSE_CONFIG=/tmp/none.yaml python -m inkpulse_hub &` 然后浏览器开 `http://127.0.0.1:8080/preview.png`
Expected: 看到默认仪表盘（状态/用量/待办/顶栏占位）。看完 `kill %1`。

- [ ] **Step 9: Commit**

```bash
git add software/hub/inkpulse_hub/__main__.py software/hub/hooks/claude_status.sh software/hub/README.md software/hub/tests/test_main.py
git commit -m "feat(hub): 入口/Hook脚本/运行说明"
```

---

## 自检对照（spec → task 覆盖）

- Claude 状态(A) → Task 1(模型)/9(聚合)/10(/ingest) + Hook 脚本(Task 12) ✅
- 用量(B) → Task 5(解析日志) + widget(Task 7) ✅
- 待办(C) → Task 4(JSON存储) + Task 11(Web UI/API) + widget(Task 7) ✅
- 照片(D) → Task 6(采集+抖动) + engine photo 布局(Task 8) ✅
- 温湿度/时钟 → Task 9(时钟) + Task 10(/frame env query) + widget(Task 7) ✅
- 渲染→双 bitplane → Task 2 ✅
- /frame 契约(ETag/304/X-Next-Refresh) → Task 10 ✅
- /preview.png 调试 → Task 10 ✅
- 配置驱动布局(YAML) → Task 3 + Task 8 ✅
- 每 widget 缺失数据 n/a 容错 → Task 7(header n/a)/8(test_missing_data) ✅

**字体说明：** `_font()` 默认用 DejaVuSans，**无中文字形**——状态/用量/待办里的中文会渲染为空白方块，但状态色指示块、ASCII 文本(project/token/$)、待办勾选框、进度条均正常。要正常显示中文，在 Task 7 的 `_font()` 里把字体换成系统已装的 CJK 字体（如 macOS 的 `/System/Library/Fonts/PingFang.ttc` 或 Noto Sans CJK），属一行配置，不阻塞功能与测试。建议实现时顺手改掉。

**未覆盖项（属固件计划②或后续）：** 刷新事件驱动/防抖的精细策略（v1 仅 `X-Next-Refresh`=periodic，事件驱动留计划②或迭代）；照片轮换随 refresh tick；SoftAP 配网（固件侧）。这些不阻塞 Hub 可用。
