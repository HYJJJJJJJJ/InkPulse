# 工作任务桥(Claude Code ↔ Hub)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code 会话的 TodoWrite 任务经 PostToolUse hook 实时推到 hub,屏上 `agent_tasks` widget 显示当前项目的任务(状态标记)+ 焦点(skill 提炼)+ 新鲜度;与手工待办解耦。

**Architecture:** hub 新增 `AgentTaskStore`(`~/inkpulse/agent_tasks.json`,单一"最近活跃"快照,按 project 合并)+ `POST /ingest/agent-tasks` + `draw_agent_tasks` widget。客户端:PostToolUse(TodoWrite) shell hook(A 实时镜像)+ `/inkpulse-sync` skill(B 按需提炼)。先做 Claude Code,无新依赖。

**Tech Stack:** Python 3.11 · Pillow · FastAPI · pytest · 客户端 bash + python3 + curl。

设计来源:`docs/superpowers/specs/2026-06-14-inkpulse-agent-tasks-design.md`。hub 路径相对 `software/hub/`。

---

## 关键约定(全任务通用,先读)

- **测试命令**:`.venv/bin/python -m pytest`(系统 python3 是 3.10 缺 cnlunar;venv 是 3.11)。
- **已知预存失败**:`tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`(WSL2 mDNS/网络),忽略;除它之外必须全绿。
- **存储格式**(`agent_tasks.json`)单一快照:`{"project":str, "updated_at":float, "tasks":[{"content","status"}], "highlights":[str]}`。坏/缺文件 → `current` 返回 None。
- **status** ∈ `{pending,in_progress,completed}`;未知值规范化为 `pending`;空 content 的 task 丢弃。
- **合并规则**:`ingest(now, project, tasks=None, highlights=None)` —— 同 project 只覆盖传入的非 None 字段(另一字段保留);不同 project 整体替换(传入字段 + 另一字段置 `[]`);统一写 `updated_at=now`。
- **STALE_S = 7200**(2 小时);widget 超过则标「会话可能已结束」。
- 每个任务结束 `commit`,运行目录 `software/hub/`。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `inkpulse_hub/collectors/agent_tasks.py` | 新增 | `AgentTaskStore` + `STALE_S` |
| `inkpulse_hub/config.py` | 改 | `agent_tasks_store` 字段 + sources 覆盖 |
| `inkpulse_hub/state.py` | 改 | `HubState` 持 store;注入 `agent_tasks` |
| `inkpulse_hub/server.py` | 改 | `POST /ingest/agent-tasks` |
| `inkpulse_hub/render/widgets.py` | 改 | `draw_agent_tasks` |
| `inkpulse_hub/render/registry.py` | 改 | 注册 `agent_tasks` |
| `hooks/inkpulse_agent_tasks.sh` | 新增 | A:PostToolUse(TodoWrite) 上报脚本 |
| `skills/inkpulse-sync/SKILL.md` | 新增 | B:提炼焦点-推送技能 |
| `deploy/claude-code.md` | 新增 | 客户端安装说明 |
| `tests/test_agent_tasks.py` / `test_agent_tasks_api.py` / `test_widget_agent_tasks.py` | 新增 | 单测 |
| `tests/test_state_phase2.py` / `test_registry.py` | 改 | 追加断言 |

---

## Task 1: AgentTaskStore —— 存储 + ingest(合并) + current

**Files:**
- Create: `inkpulse_hub/collectors/agent_tasks.py`
- Test: `tests/test_agent_tasks.py`

- [ ] **Step 1: 写失败测试**

`tests/test_agent_tasks.py`:

```python
from inkpulse_hub.collectors.agent_tasks import AgentTaskStore, STALE_S


def test_ingest_tasks_then_current(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "InkPulse", tasks=[{"content": "写端点", "status": "in_progress"}])
    c = s.current(1000.0)
    assert c["project"] == "InkPulse" and c["age_s"] == 0
    assert c["tasks"] == [{"content": "写端点", "status": "in_progress"}]
    assert c["highlights"] == []


def test_same_project_merges_fields(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "InkPulse", tasks=[{"content": "A", "status": "pending"}])
    s.ingest(1100.0, "InkPulse", highlights=["记得加测试"])   # 只更 highlights
    c = s.current(1100.0)
    assert [t["content"] for t in c["tasks"]] == ["A"]        # tasks 保留
    assert c["highlights"] == ["记得加测试"]


def test_different_project_replaces(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "InkPulse", tasks=[{"content": "A", "status": "pending"}],
             highlights=["h1"])
    s.ingest(1200.0, "Other", tasks=[{"content": "B", "status": "pending"}])
    c = s.current(1200.0)
    assert c["project"] == "Other"
    assert [t["content"] for t in c["tasks"]] == ["B"]
    assert c["highlights"] == []                              # 旧项目 highlights 清空


def test_tasks_normalized(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "P", tasks=[
        {"content": "ok", "status": "weird"},   # 未知 status -> pending
        {"content": "", "status": "pending"},   # 空 content -> 丢弃
        {"status": "pending"},                   # 无 content -> 丢弃
    ])
    assert s.current(1000.0)["tasks"] == [{"content": "ok", "status": "pending"}]


def test_age_and_corrupt(tmp_path):
    p = tmp_path / "a.json"
    s = AgentTaskStore(str(p))
    s.ingest(1000.0, "P", tasks=[{"content": "x", "status": "pending"}])
    assert s.current(1000.0 + 5)["age_s"] == 5
    p.write_text("{bad", encoding="utf-8")
    assert AgentTaskStore(str(p)).current(0.0) is None        # 坏文件 -> None
    assert STALE_S == 7200
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_agent_tasks.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'inkpulse_hub.collectors.agent_tasks'`

- [ ] **Step 3: 写实现**

`inkpulse_hub/collectors/agent_tasks.py`:

```python
# inkpulse_hub/collectors/agent_tasks.py
import json
import os

STALE_S = 7200   # 2 小时未更新视为会话可能已结束

_STATUSES = ("pending", "in_progress", "completed")


def _norm_tasks(tasks):
    out = []
    for t in tasks or []:
        if not isinstance(t, dict):
            continue
        content = str(t.get("content", "")).strip()
        if not content:
            continue
        status = t.get("status")
        out.append({"content": content,
                    "status": status if status in _STATUSES else "pending"})
    return out


class AgentTaskStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    def _write(self, snap):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)

    def ingest(self, now, project, tasks=None, highlights=None):
        old = self._read()
        if old and old.get("project") == project:
            snap = old
        else:
            snap = {"project": project, "tasks": [], "highlights": []}
        if tasks is not None:
            snap["tasks"] = _norm_tasks(tasks)
        if highlights is not None:
            snap["highlights"] = [str(h) for h in highlights]
        snap["project"] = project
        snap["updated_at"] = now
        self._write(snap)

    def current(self, now):
        snap = self._read()
        if not snap or "updated_at" not in snap:
            return None
        return {"project": snap.get("project", ""),
                "tasks": snap.get("tasks", []),
                "highlights": snap.get("highlights", []),
                "age_s": now - snap["updated_at"]}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_agent_tasks.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/agent_tasks.py tests/test_agent_tasks.py
git commit -m "feat(agent): AgentTaskStore 存储 + ingest(按项目合并) + current"
```

---

## Task 2: config.py —— agent_tasks_store 字段

**Files:**
- Modify: `inkpulse_hub/config.py`
- Test: `tests/test_config.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加:

```python
def test_agent_tasks_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().agent_tasks_store.endswith("inkpulse/agent_tasks.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  agent_tasks_store: /tmp/at.json\n", encoding="utf-8")
    assert load_config(str(p)).agent_tasks_store == "/tmp/at.json"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_agent_tasks_store_default_and_override -v`
Expected: FAIL —— `AttributeError: 'Config' object has no attribute 'agent_tasks_store'`

- [ ] **Step 3: 实现**

`inkpulse_hub/config.py`:在 `Config` 数据类里、`market_cache` 字段下一行加(`market_symbols` 字段在其后,插在 `market_cache` 之后、`market_symbols` 之前或之后均可——放 `market_symbols` 之后更稳):

定位 `market_symbols: list = field(default_factory=list)` 那行,在其**下一行**加:
```python
    agent_tasks_store: str = os.path.expanduser("~/inkpulse/agent_tasks.json")
```

在 `load_config` 内、`cfg.market_cache = ...` 那行下一行加:
```python
    cfg.agent_tasks_store = os.path.expanduser(sources.get("agent_tasks_store", cfg.agent_tasks_store))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit -m "feat(config): 新增 agent_tasks_store 路径字段与 sources 覆盖"
```

---

## Task 3: state.py —— 注入 agent_tasks

**Files:**
- Modify: `inkpulse_hub/state.py`
- Test: `tests/test_state_phase2.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_state_phase2.py` 末尾追加:

```python
def test_render_state_agent_tasks_none_by_default(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    cfg.market_cache = str(tmp_path / "m.json")
    cfg.agent_tasks_store = str(tmp_path / "at.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "agent_tasks" in state and state["agent_tasks"] is None


def test_render_state_agent_tasks_present(tmp_path):
    cfg = Config()
    for attr, fn in [("claude_logs","logs"),("todos_store","todos.json"),
                     ("photos_dir","photos"),("habits_store","habits.json"),
                     ("env_history_store","env.json"),("weather_cache","w.json"),
                     ("events_store","events.json"),("market_cache","m.json"),
                     ("agent_tasks_store","at.json")]:
        setattr(cfg, attr, str(tmp_path / fn))
    st = HubState(cfg)
    st.agent_tasks.ingest(1718000000.0, "P", tasks=[{"content":"x","status":"pending"}])
    state = st.build_render_state(now=1718000000.0)
    assert state["agent_tasks"]["project"] == "P"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py::test_render_state_agent_tasks_none_by_default -v`
Expected: FAIL —— `KeyError: 'agent_tasks'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py`:

1. import 区,在 `from .collectors.market import MarketService` 下一行加:
```python
from .collectors.agent_tasks import AgentTaskStore
```

2. `HubState.__init__`,在 `self.market = MarketService(cfg.market_cache)` 下一行加:
```python
        self.agent_tasks = AgentTaskStore(cfg.agent_tasks_store)
```

3. `build_render_state` 返回 dict 里加一个键(放在 `"market": market,` 之后):
```python
            "agent_tasks": self.agent_tasks.current(now),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit -m "feat(state): build_render_state 注入 agent_tasks"
```

---

## Task 4: server.py —— POST /ingest/agent-tasks

**Files:**
- Modify: `inkpulse_hub/server.py`
- Test: `tests/test_agent_tasks_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_agent_tasks_api.py`:

```python
import time
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 agent_tasks_store=str(tmp_path / "at.json"))
    return create_app(cfg)


def test_ingest_tasks(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    r = c.post("/ingest/agent-tasks",
               json={"project": "P", "tasks": [{"content": "x", "status": "pending"}]})
    assert r.status_code == 200
    cur = app.state.hub.agent_tasks.current(time.time())
    assert cur["project"] == "P" and cur["tasks"][0]["content"] == "x"


def test_ingest_blank_project_400(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.post("/ingest/agent-tasks", json={"project": "  ", "tasks": []}).status_code == 400


def test_ingest_highlights_only_keeps_tasks(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    c.post("/ingest/agent-tasks", json={"project": "P", "tasks": [{"content": "x", "status": "pending"}]})
    c.post("/ingest/agent-tasks", json={"project": "P", "highlights": ["h"]})
    cur = app.state.hub.agent_tasks.current(time.time())
    assert [t["content"] for t in cur["tasks"]] == ["x"] and cur["highlights"] == ["h"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_agent_tasks_api.py -v`
Expected: FAIL —— `/ingest/agent-tasks` 返回 404

- [ ] **Step 3: 实现**

`inkpulse_hub/server.py`:在 `@app.post("/ingest/claude-status")` 那个 ingest 处理函数之后(约第 56 行后),插入:

```python
    @app.post("/ingest/agent-tasks")
    async def ingest_agent_tasks(request: Request):
        data = await request.json()
        project = (data.get("project") or "").strip()
        if not project:
            return JSONResponse({"error": "project required"}, status_code=400)
        state.agent_tasks.ingest(time.time(), project,
                                 tasks=data.get("tasks"),
                                 highlights=data.get("highlights"))
        return JSONResponse({"ok": True})
```
(`Request`/`JSONResponse`/`import time` 均已在 server.py 顶部——确认后复用,勿重复导入。)

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_agent_tasks_api.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_agent_tasks_api.py
git commit -m "feat(api): POST /ingest/agent-tasks(校验 project + 合并入库)"
```

---

## Task 5: draw_agent_tasks widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(末尾新增)
- Test: `tests/test_widget_agent_tasks.py`

- [ ] **Step 1: 写失败测试**

`tests/test_widget_agent_tasks.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_agent_tasks, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _data(age_s=120, highlights=None):
    return {"project": "InkPulse", "age_s": age_s,
            "tasks": [{"content": "写端点", "status": "in_progress"},
                      {"content": "做 widget", "status": "pending"},
                      {"content": "探索 hook", "status": "completed"}],
            "highlights": highlights or []}


def test_draws_with_data():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), _data())
    assert _has_black(img)


def test_none_shows_hint_no_crash():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), None)
    assert _has_black(img)   # "无活动会话" 提示


def test_highlights_rendered_no_crash():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), _data(highlights=["记得加测试"]))
    assert _has_black(img)


def test_stale_no_crash():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), _data(age_s=99999))   # >2h
    assert _has_black(img)


def test_long_content_truncated_no_crash():
    img, d = _img(280, 120)
    data = {"project": "X" * 40, "age_s": 60, "highlights": [],
            "tasks": [{"content": "超长任务" * 12, "status": "pending"}]}
    draw_agent_tasks(d, Zone(0, 0, 280, 120), data)
    assert _has_black(img)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_agent_tasks.py -v`
Expected: FAIL —— `ImportError: cannot import name 'draw_agent_tasks'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加(复用 `_title_bar`/`_center_text`/`_font`/`Zone`/`BLACK`;从 collectors 取 `STALE_S`):

```python
def draw_agent_tasks(d: ImageDraw.ImageDraw, z: Zone, data) -> None:
    """Claude Code 会话任务镜像。data=current() 返回(含 age_s)或 None。纯黑。"""
    from ..collectors.agent_tasks import STALE_S
    project = (data or {}).get("project") or ""
    cy = _title_bar(d, z, f"工作中 · {project}" if project else "工作中")
    if not data:
        _center_text(d, z, "无活动会话", _font(18), BLACK)
        return
    f = _font(18)
    row_h = 28
    avail_bottom = z.y + z.h - 18           # 给底部新鲜度留行
    y = cy
    for t in data.get("tasks", []):
        if y + row_h > avail_bottom:
            break
        st = t.get("status")
        mark = "■" if st == "in_progress" else ("✓" if st == "completed" else "□")
        line = f"{mark} {t.get('content','')}"
        while line and d.textlength(line, font=f) > z.w - 12:
            line = line[:-1]
        d.text((z.x + 8, y), line, fill=BLACK, font=f)
        if st == "completed":                # 完成项删除线
            w = d.textlength(line, font=f)
            d.line((z.x + 8, y + 13, z.x + 8 + w, y + 13), fill=BLACK, width=1)
        y += row_h
    # highlights(焦点)
    hs = data.get("highlights", [])
    if hs and y + row_h <= avail_bottom:
        for h in hs:
            if y + row_h > avail_bottom:
                break
            line = f"· {h}"
            while line and d.textlength(line, font=f) > z.w - 12:
                line = line[:-1]
            d.text((z.x + 8, y), line, fill=BLACK, font=f)
            y += row_h
    # 底部新鲜度
    age = int((data.get("age_s") or 0))
    foot = "会话可能已结束" if age > STALE_S else f"活跃于 {age // 60} 分钟前"
    fw = d.textlength(foot, font=_font(12))
    d.text((z.x + z.w - fw - 6, z.y + z.h - 14), foot, fill=BLACK, font=_font(12))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_agent_tasks.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_agent_tasks.py
git commit -m "feat(widget): draw_agent_tasks(状态标记■/□/✓ + 焦点 + 新鲜度/过期)"
```

---

## Task 6: registry —— 注册 agent_tasks widget

**Files:**
- Modify: `inkpulse_hub/render/registry.py`
- Test: `tests/test_registry.py`(`_state()` 补字段 + 断言)

- [ ] **Step 1: 改测试(先让其失败)**

`tests/test_registry.py` 的 `_state()` 返回 dict 内追加一键:

```python
        "agent_tasks": {"project": "InkPulse", "age_s": 60, "highlights": [],
                        "tasks": [{"content": "写端点", "status": "in_progress"}]},
```

把 `test_existing_widgets_registered` 的 `expected` 集合加入 `"agent_tasks"`(读当前集合后追加):

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist", "habits", "temp_trend", "weather",
                "agenda", "market", "agent_tasks"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL —— `agent_tasks` 不在 REGISTRY

- [ ] **Step 3: 实现**

`inkpulse_hub/render/registry.py`:

1. 在 `_market` 适配器之后加:
```python
def _agent_tasks(d, img, z, state, cfg, p):
    W.draw_agent_tasks(d, z, state.get("agent_tasks"))
```

2. `REGISTRY` 字典里(`"market": ...` 之后)加一条:
```python
    "agent_tasks":   WidgetSpec("agent_tasks", "工作任务", _agent_tasks, {"cols": 4, "rows": 3}),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit -m "feat(registry): 注册 agent_tasks widget 与适配器"
```

---

## Task 7: 客户端 hook(A 实时镜像)+ 解析逻辑测试

**Files:**
- Create: `hooks/inkpulse_agent_tasks.sh`
- Test: `tests/test_hook_parse.py`(测脚本内嵌的 python 解析逻辑)

- [ ] **Step 1: 写失败测试**

`tests/test_hook_parse.py`(把 hook 用到的 stdin→POST body 解析逻辑做成可测的独立 python 片段,验证它对样例 TodoWrite stdin 的产出):

```python
import json
import subprocess
import sys
import textwrap

# 与 hooks/inkpulse_agent_tasks.sh 内嵌的 python 解析等价的独立脚本(单一真相: 见下方实现步骤,
# 二者必须一致)。本测试直接执行该解析脚本, 喂样例 stdin, 断言输出 JSON body。
PARSE = textwrap.dedent(r'''
import sys, json, os
d = json.load(sys.stdin)
todos = (d.get("tool_input") or {}).get("todos") or []
tasks = [{"content": t.get("content",""), "status": t.get("status","pending")}
         for t in todos if t.get("content")]
project = os.path.basename((d.get("cwd") or "").rstrip("/")) or "?"
print(json.dumps({"project": project, "tasks": tasks}, ensure_ascii=False))
''')


def _run(stdin_obj):
    r = subprocess.run([sys.executable, "-c", PARSE],
                       input=json.dumps(stdin_obj), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_parse_extracts_tasks_and_project():
    out = _run({"cwd": "/home/u/work/InkPulse",
                "tool_input": {"todos": [
                    {"content": "写端点", "status": "in_progress"},
                    {"content": "做 widget", "status": "pending"},
                    {"content": "", "status": "pending"}]}})
    assert out["project"] == "InkPulse"
    assert [t["content"] for t in out["tasks"]] == ["写端点", "做 widget"]


def test_parse_empty_todos():
    out = _run({"cwd": "/x/y", "tool_input": {"todos": []}})
    assert out == {"project": "y", "tasks": []}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_hook_parse.py -v`
Expected: PASS 实际上会**直接通过**(PARSE 是自包含的)——本任务的"失败先行"体现在:先确认 `hooks/inkpulse_agent_tasks.sh` 不存在(`test -f hooks/inkpulse_agent_tasks.sh` 为假),再创建它并保证其内嵌解析与 `PARSE` 字节一致。
> 说明:hook 是 shell,无 pytest 直测;此测试锁定"解析逻辑契约"。实现步骤要求把同一段 python 内嵌进 .sh,二者保持一致。

- [ ] **Step 3: 写实现**

`hooks/inkpulse_agent_tasks.sh`:

```bash
#!/usr/bin/env bash
# Claude Code PostToolUse(TodoWrite) hook: 把当前会话任务镜像到 InkPulse Hub。
# 配置: ~/.claude/settings.json 的 hooks.PostToolUse, matcher "TodoWrite", command 指向本脚本。
# stdin 收到 PostToolUse JSON(含 tool_input.todos 与 cwd)。失败绝不阻塞会话。
HUB="${INKPULSE_HUB:-http://127.0.0.1:8080}"
BODY="$(python3 -c '
import sys, json, os
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
todos = (d.get("tool_input") or {}).get("todos") or []
tasks = [{"content": t.get("content",""), "status": t.get("status","pending")}
         for t in todos if t.get("content")]
project = os.path.basename((d.get("cwd") or "").rstrip("/")) or "?"
print(json.dumps({"project": project, "tasks": tasks}, ensure_ascii=False))
' 2>/dev/null)"
[ -z "$BODY" ] && exit 0
curl -s -m 2 -X POST "$HUB/ingest/agent-tasks" \
  -H 'Content-Type: application/json' -d "$BODY" >/dev/null 2>&1 || true
exit 0
```

确保脚本可执行:`chmod +x hooks/inkpulse_agent_tasks.sh`。
**校验内嵌 python 与测试 PARSE 一致**(逐字符核对解析三行:todos 取值、tasks 过滤、project basename)。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_hook_parse.py -v`
Expected: PASS(2 passed)。再手动验证脚本本身:
```bash
echo '{"cwd":"/a/b/InkPulse","tool_input":{"todos":[{"content":"t1","status":"in_progress"}]}}' | INKPULSE_HUB=http://127.0.0.1:1 ./hooks/inkpulse_agent_tasks.sh; echo "exit=$?"
```
Expected: `exit=0`(hub 不可达也 exit 0,不阻塞)。

- [ ] **Step 5: 提交**

```bash
git add hooks/inkpulse_agent_tasks.sh tests/test_hook_parse.py
git commit -m "feat(hook): PostToolUse(TodoWrite) 上报脚本 + 解析契约测试"
```

---

## Task 8: 客户端 skill(B 提炼)+ 安装说明

**Files:**
- Create: `skills/inkpulse-sync/SKILL.md`
- Create: `deploy/claude-code.md`
- 验证:文件存在 + 内容自洽(无单测)

- [ ] **Step 1: 写 skill**

`skills/inkpulse-sync/SKILL.md`:

```markdown
---
name: inkpulse-sync
description: 用户想把当前会话的"工作焦点/关键行动项"推到 InkPulse 墨水屏时使用。提炼 2~5 条简短中文要点并上报 hub。
---

# inkpulse-sync

当用户调用本 skill 时:

1. 回顾当前会话与代码上下文,提炼出 **2~5 条**简短中文"工作焦点/持久行动项"(比如"给 parse 加边界测试""等 CI 通过后合并")。每条尽量短(≤20 字),只留真正值得在屏上长期提醒的。
2. 取当前项目名:`basename "$PWD"`。
3. 用 `curl` POST 到 hub 的 `/ingest/agent-tasks`,只带 `highlights`(不要带 `tasks`,以免覆盖 TodoWrite 的实时镜像):

   ```bash
   HUB="${INKPULSE_HUB:-http://127.0.0.1:8080}"
   curl -s -m 3 -X POST "$HUB/ingest/agent-tasks" \
     -H 'Content-Type: application/json' \
     -d "$(python3 -c 'import json,os,sys; print(json.dumps({"project":os.path.basename(os.getcwd()),"highlights":sys.argv[1:]}, ensure_ascii=False))' "焦点1" "焦点2")"
   ```
   把 `"焦点1" "焦点2"` 换成你提炼的要点(每条作为一个参数)。
4. 告诉用户已推送了哪几条焦点。

注意:hub 不可达时 curl 会失败,如实告知即可,不要重试纠缠。
```

- [ ] **Step 2: 写安装说明**

`deploy/claude-code.md`:

```markdown
# Claude Code ↔ InkPulse 工作任务桥:安装

让 Claude Code 会话自动把任务/焦点推到墨水屏。需 hub 已运行(见 deploy/README.md)。

## 1. A:实时镜像 TodoWrite(hook)

把 `software/hub/hooks/inkpulse_agent_tasks.sh` 配成 PostToolUse(TodoWrite) hook。
在 `~/.claude/settings.json` 的 `hooks` 中加(路径换成你的绝对路径):

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "TodoWrite",
        "hooks": [ { "type": "command",
          "command": "/home/zqx/workspace/InkPulse/software/hub/hooks/inkpulse_agent_tasks.sh" } ] }
    ]
  }
}
```

确保脚本可执行:`chmod +x .../hooks/inkpulse_agent_tasks.sh`。
hub 地址非默认时设环境变量 `INKPULSE_HUB=http://<ip>:8080`。

## 2. B:按需提炼焦点(skill)

把 `software/hub/skills/inkpulse-sync/` 放到 Claude Code 能发现 skill 的位置
(如 `~/.claude/skills/inkpulse-sync/SKILL.md`)。会话里调用该 skill 即把焦点推上屏。

## 3. 上屏

把 `agent_tasks`(标签"工作任务")widget 加进某个布局(`/config` 布局编辑器)。
之后:你让 Claude Code 干活、它更新 TodoWrite → 屏上自动出现当前项目任务。
```

- [ ] **Step 3: 验证**

```bash
test -f skills/inkpulse-sync/SKILL.md && test -f deploy/claude-code.md && echo OK
head -3 skills/inkpulse-sync/SKILL.md   # 确认 frontmatter name/description 在
```
Expected: `OK` + 看到 frontmatter。

- [ ] **Step 4: 提交**

```bash
git add skills/inkpulse-sync/SKILL.md deploy/claude-code.md
git commit -m "feat(skill): inkpulse-sync 提炼焦点技能 + 客户端安装说明"
```

---

## Task 9: 全量验证 + 预览 + spec 验收

**Files:** 无改动(纯验证)

- [ ] **Step 1: 跑全部测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全绿,唯一允许失败是预存的 `tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`。

- [ ] **Step 2: 渲染 agent_tasks 预览**

```bash
.venv/bin/python -c "
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_agent_tasks, Zone
data={'project':'InkPulse','age_s':120,'highlights':['记得给解析加测试'],
      'tasks':[{'content':'写 ingest 端点','status':'in_progress'},
               {'content':'实现 agent_tasks widget','status':'pending'},
               {'content':'探索 hook 机制','status':'completed'}]}
img=Image.new('RGB',(360,200),(255,255,255)); d=ImageDraw.Draw(img); d.fontmode='1'
draw_agent_tasks(d, Zone(0,0,360,200), data); img.save('/tmp/agent_tasks_preview.png'); print('saved')
"
```
打开 `/tmp/agent_tasks_preview.png` 目视:标题「工作中 · InkPulse」、■/□/✓ 三态任务(完成项删除线)、焦点行、右下「活跃于 2 分钟前」。

- [ ] **Step 3: 端到端冒烟(可选, 起临时实例)**

```bash
# 起临时 app(参考 tests/test_agent_tasks_api.py), curl 模拟 hook:
# curl -X POST localhost:PORT/ingest/agent-tasks -d '{"project":"P","tasks":[{"content":"x","status":"in_progress"}]}'
# 再 GET /preview.png(布局含 agent_tasks)看是否出现。
```

- [ ] **Step 4: 对照 spec 第 12 节验收逐条打勾**

1. TodoWrite 变化→屏显任务+项目+新鲜度 —— Task 1/3/5/6/7。
2. skill 推 highlights 不动 tasks —— Task 4(highlights-only 合并)/8。
3. 多会话最近活跃胜出;无活动/坏文件不崩;过期标注;hook 失败不阻塞 —— Task 1/5/7。
4. 全部测试通过 —— Step 1。

- [ ] **Step 5: 归档提示**

合并后可把本期 spec+plan 移入 `docs/superpowers/archive/`。仅提示。

---

## 自检(写计划后已核对)

- **Spec 覆盖**:§5.2 AgentTaskStore(ingest 合并/规范化/current/坏文件)→ T1;§4 config → T2;§4 state 注入 → T3;§7 API(POST/空 project 400/highlights-only)→ T4;§6 widget(■/□/✓+删除线+highlights+新鲜度+过期+空提示+截断)→ T5;§4 registry → T6;§8.1 hook(A,stdin 解析+不阻塞)→ T7;§8.2 skill(B)+ §8.3 安装说明 → T8;§9 错误处理(坏文件 None、空 project 400、hook||true exit0、过期标注)→ T1/T4/T5/T7;§10 测试 → 各任务;§11 无新依赖 → 确认;§12 验收 → T9。无遗漏。
- **签名/命名一致**:`AgentTaskStore.ingest(now,project,tasks=None,highlights=None)`/`current(now)→{project,tasks,highlights,age_s}|None`、`STALE_S`、`draw_agent_tasks(d,z,data)`、state 键 `agent_tasks`、registry `agent_tasks`、config `agent_tasks_store`、端点 `/ingest/agent-tasks` —— 全计划统一。hook 解析契约与 `tests/test_hook_parse.py` 的 PARSE 一致(实现步骤强制核对)。
- **无占位符**:每个改码步骤均给出完整代码与确切路径/命令/预期输出。
```
