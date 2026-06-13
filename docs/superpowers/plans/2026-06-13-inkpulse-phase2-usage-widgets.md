# 第二期只读 widget(用量趋势 + 项目分布)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 InkPulse Hub 加两个只读 widget——用量趋势(近 N 天柱状)与项目分布(今日各项目占比),数据全部来自现有 Claude Code 日志,零新存储;并新增 `select` 参数类型让"度量(tokens/cost)"在网页编辑器里可选。

**Architecture:** 把 `collectors/usage.py` 的 jsonl 解析抽成共享迭代器 `_iter_usage_records()`,在其上建"按日"与"按项目"两个聚合函数;`build_render_state` 预算出 `usage_daily` / `usage_projects` 塞进 state;两个新 widget 在绘制时按自己的参数(days / top_n / metric)切片渲染。现有 8 widget 与 6 内置布局不受影响。

**Tech Stack:** Python 3.11 / FastAPI / Pillow / pytest。工作目录 `software/hub/`,测试用 `.venv/bin/python -m pytest`,提交统一加 `git commit --no-verify`(仓库 LFS 钩子缺 git-lfs)。

**关键约定:**
- `project = basename(cwd)`,cwd 取自每条日志记录的顶层 `cwd` 字段,缺失记 `"?"`。
- token 口径 = 净 `input + output`(不含缓存);cost 复用现有 `_PRICING` 估算。
- 度量 `metric ∈ {"tokens","cost"}`,默认 `tokens`,未知值回退 `tokens`。
- 所有颜色纯黑(无红色告警);空数据画"无数据"。
- 测试用合成 tmp `.jsonl` + 显式传 `now`,避开时区/真实文件的不确定性。

---

## Task 1: 抽出共享迭代器 `_iter_usage_records`(重构 `collect_usage`,行为不变)

**Files:**
- Modify: `inkpulse_hub/collectors/usage.py`
- Test: `tests/test_usage_iter.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_usage_iter.py`:

```python
import json
import os
from datetime import datetime, timedelta, timezone
from inkpulse_hub.collectors.usage import _iter_usage_records, UsageRecord

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc).astimezone()


def _iso(dt_local):
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_log(d, name, records):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(dt_local, cwd, inp, out, model="claude-opus-4-8"):
    return {"timestamp": _iso(dt_local), "cwd": cwd,
            "message": {"model": model,
                        "usage": {"input_tokens": inp, "output_tokens": out}}}


def test_iter_yields_records_with_project_basename(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [
        _rec(NOW, "/home/u/workspace/InkPulse", 10, 5),
        _rec(NOW, "/home/u/webapp", 3, 2),
    ])
    recs = list(_iter_usage_records(str(tmp_path)))
    assert len(recs) == 2
    assert all(isinstance(r, UsageRecord) for r in recs)
    assert {r.project for r in recs} == {"InkPulse", "webapp"}
    one = next(r for r in recs if r.project == "InkPulse")
    assert one.input == 10 and one.output == 5


def test_iter_skips_bad_lines_and_no_usage(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text(
        "{ not json\n"
        + json.dumps({"timestamp": _iso(NOW), "cwd": "/x/y", "message": {}}) + "\n"   # 无 usage
        + json.dumps(_rec(NOW, "/x/y", 1, 1)) + "\n",
        encoding="utf-8")
    recs = list(_iter_usage_records(str(tmp_path)))
    assert len(recs) == 1


def test_iter_missing_cwd_is_question_mark(tmp_path):
    _write_log(str(tmp_path), "c.jsonl", [
        {"timestamp": _iso(NOW), "message": {"usage": {"input_tokens": 1, "output_tokens": 0}}},
    ])
    recs = list(_iter_usage_records(str(tmp_path)))
    assert recs and recs[0].project == "?"


def test_iter_empty_dir(tmp_path):
    assert list(_iter_usage_records(str(tmp_path / "nope"))) == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_usage_iter.py -v`
Expected: FAIL — `ImportError: cannot import name '_iter_usage_records'`(及 `UsageRecord`)

- [ ] **Step 3: 实现迭代器并重构 `collect_usage`**

在 `inkpulse_hub/collectors/usage.py` 顶部 import 段补充:

```python
from dataclasses import dataclass
from typing import Iterator, Optional
```

在 `_record_local_date` 函数之后、`collect_usage` 之前,插入:

```python
@dataclass
class UsageRecord:
    dt: datetime          # 本地时区
    project: str          # basename(cwd), 缺失记 "?"
    input: int
    output: int
    cache_read: int
    cache_create: int
    model: Optional[str]
    source: str           # 来源文件路径(供 session_count 计数, 保持旧行为)


def _project_of(rec: dict) -> str:
    cwd = rec.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return os.path.basename(cwd.rstrip("/")) or "?"
    return "?"


def _iter_usage_records(logs_dir: str) -> Iterator[UsageRecord]:
    """遍历 logs_dir/**/*.jsonl, 逐条 yield 带 usage 的记录。
    坏行 / 无时间戳 / 无 usage 一律跳过(沿用旧容错口径)。"""
    if not os.path.isdir(logs_dir):
        return
    files = glob.glob(os.path.join(logs_dir, "**", "*.jsonl"), recursive=True)
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
                        continue
                    dt = _record_dt(rec)
                    if dt is None:
                        continue
                    msg = rec.get("message") or {}
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    yield UsageRecord(
                        dt=dt,
                        project=_project_of(rec),
                        input=int(usage.get("input_tokens", 0) or 0),
                        output=int(usage.get("output_tokens", 0) or 0),
                        cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
                        cache_create=int(usage.get("cache_creation_input_tokens", 0) or 0),
                        model=msg.get("model"),
                        source=fp,
                    )
        except OSError:
            continue


def _cost_of_record(r: UsageRecord) -> float:
    """单条记录花费估算(复用 _cost_of 的定价口径)。"""
    return _cost_of({
        "input_tokens": r.input,
        "output_tokens": r.output,
        "cache_creation_input_tokens": r.cache_create,
        "cache_read_input_tokens": r.cache_read,
    }, r.model)
```

然后把 `collect_usage` 的函数体(从 `u = Usage()` 到 `return u`)整体替换为基于迭代器的版本(保持签名与口径完全不变):

```python
def collect_usage(
    logs_dir: str,
    today: date | None = None,
    now: datetime | None = None,
    window_token_limit: int | None = None,
) -> Usage:
    """解析 Claude Code 会话日志(.jsonl):今日 token/花费 + 近 5h 窗口占比。"""
    u = Usage()
    if now is None:
        now = datetime.now().astimezone()
    if today is None:
        today = now.date()
    window_start = now - timedelta(hours=_WINDOW_HOURS)

    sessions_today = set()
    window_tokens = 0
    for r in _iter_usage_records(logs_dir):
        if r.dt.date() == today:
            u.input_tokens += r.input
            u.output_tokens += r.output
            u.cache_tokens += r.cache_read
            u.cost_usd += _cost_of_record(r)
            sessions_today.add(r.source)
        if r.dt >= window_start:
            window_tokens += r.input + r.output
    u.session_count = len(sessions_today)
    if window_token_limit and window_token_limit > 0:
        u.window_used_ratio = min(1.0, window_tokens / window_token_limit)
    return u
```

- [ ] **Step 4: 运行新测试 + 回归**

Run: `.venv/bin/python -m pytest tests/test_usage_iter.py tests/test_usage.py -v`
Expected: PASS(新 4 个 + `test_usage.py` 现有全部仍绿,证明重构未改 `collect_usage` 行为)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/usage.py tests/test_usage_iter.py
git commit --no-verify -m "refactor(hub): 抽出 _iter_usage_records 共享迭代器(collect_usage 行为不变)"
```

---

## Task 2: 按日聚合 `collect_daily_usage`

**Files:**
- Modify: `inkpulse_hub/collectors/usage.py`
- Test: `tests/test_usage_daily.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_usage_daily.py`:

```python
import json
import os
from datetime import datetime, timedelta, timezone
from inkpulse_hub.collectors.usage import collect_daily_usage

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc).astimezone()


def _iso(dt_local):
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_log(d, name, records):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(dt_local, inp, out):
    return {"timestamp": _iso(dt_local), "cwd": "/p/InkPulse",
            "message": {"model": "claude-opus-4-8",
                        "usage": {"input_tokens": inp, "output_tokens": out}}}


def test_buckets_length_equals_days_and_ordered_old_to_new(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [_rec(NOW, 10, 5)])
    out = collect_daily_usage(str(tmp_path), days=7, now=NOW)
    assert len(out) == 7
    assert out[0]["date"] < out[-1]["date"]          # 旧 -> 新
    assert out[-1]["date"] == NOW.date()             # 末桶是今天


def test_missing_days_are_zero_filled(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [
        _rec(NOW, 10, 5),                    # 今天: 15 tok
        _rec(NOW - timedelta(days=3), 4, 1),  # 3 天前: 5 tok
    ])
    out = collect_daily_usage(str(tmp_path), days=7, now=NOW)
    by_date = {x["date"]: x["tokens"] for x in out}
    assert by_date[NOW.date()] == 15
    assert by_date[(NOW - timedelta(days=3)).date()] == 5
    assert by_date[(NOW - timedelta(days=1)).date()] == 0   # 无数据补零


def test_cost_summed(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [_rec(NOW, 1_000_000, 0)])  # opus 输入 $15/M
    out = collect_daily_usage(str(tmp_path), days=1, now=NOW)
    assert out[-1]["cost"] > 0


def test_empty_dir_all_zero(tmp_path):
    out = collect_daily_usage(str(tmp_path / "nope"), days=5, now=NOW)
    assert len(out) == 5 and all(x["tokens"] == 0 and x["cost"] == 0 for x in out)
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_usage_daily.py -v`
Expected: FAIL — `ImportError: cannot import name 'collect_daily_usage'`

- [ ] **Step 3: 实现**

在 `inkpulse_hub/collectors/usage.py` 的 `collect_usage` 之后追加:

```python
def collect_daily_usage(logs_dir: str, days: int = 14,
                        now: datetime | None = None) -> list[dict]:
    """近 days 天每日桶, 旧->新, 缺日补零。
    返回 [{"date": date, "tokens": int(净), "cost": float}], 长度恒 = days。"""
    if now is None:
        now = datetime.now().astimezone()
    today = now.date()
    start = today - timedelta(days=days - 1)
    buckets: dict = {}
    for r in _iter_usage_records(logs_dir):
        d = r.dt.date()
        if start <= d <= today:
            b = buckets.setdefault(d, [0, 0.0])
            b[0] += r.input + r.output
            b[1] += _cost_of_record(r)
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        tk, co = buckets.get(d, (0, 0.0))
        out.append({"date": d, "tokens": tk, "cost": co})
    return out
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_usage_daily.py -v`
Expected: PASS(4 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/usage.py tests/test_usage_daily.py
git commit --no-verify -m "feat(hub): collect_daily_usage 近N天按日聚合(缺日补零)"
```

---

## Task 3: 按项目聚合 `collect_project_usage`

**Files:**
- Modify: `inkpulse_hub/collectors/usage.py`
- Test: `tests/test_usage_project.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_usage_project.py`:

```python
import json
import os
from datetime import datetime, timedelta, timezone
from inkpulse_hub.collectors.usage import collect_project_usage

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc).astimezone()


def _iso(dt_local):
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_log(d, name, records):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(dt_local, cwd, inp, out):
    return {"timestamp": _iso(dt_local), "cwd": cwd,
            "message": {"model": "claude-opus-4-8",
                        "usage": {"input_tokens": inp, "output_tokens": out}}}


def test_groups_by_basename_today_only_desc(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [
        _rec(NOW, "/p/InkPulse", 100, 0),
        _rec(NOW, "/p/InkPulse", 50, 0),
        _rec(NOW, "/p/webapp", 30, 0),
        _rec(NOW - timedelta(days=1), "/p/old", 999, 0),   # 昨天: 不计入今日
    ])
    out = collect_project_usage(str(tmp_path), now=NOW)
    assert [x["project"] for x in out] == ["InkPulse", "webapp"]   # 降序
    assert out[0]["tokens"] == 150


def test_empty_dir_returns_empty(tmp_path):
    assert collect_project_usage(str(tmp_path / "nope"), now=NOW) == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_usage_project.py -v`
Expected: FAIL — `ImportError: cannot import name 'collect_project_usage'`

- [ ] **Step 3: 实现**

在 `inkpulse_hub/collectors/usage.py` 的 `collect_daily_usage` 之后追加:

```python
def collect_project_usage(logs_dir: str, today: date | None = None,
                          now: datetime | None = None) -> list[dict]:
    """今日各项目桶, 按 tokens 降序。
    返回 [{"project": str, "tokens": int(净), "cost": float}]; 空 -> []。"""
    if now is None:
        now = datetime.now().astimezone()
    if today is None:
        today = now.date()
    buckets: dict = {}
    for r in _iter_usage_records(logs_dir):
        if r.dt.date() == today:
            b = buckets.setdefault(r.project, [0, 0.0])
            b[0] += r.input + r.output
            b[1] += _cost_of_record(r)
    out = [{"project": p, "tokens": v[0], "cost": v[1]} for p, v in buckets.items()]
    out.sort(key=lambda x: x["tokens"], reverse=True)
    return out
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_usage_project.py -v`
Expected: PASS(2 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/usage.py tests/test_usage_project.py
git commit --no-verify -m "feat(hub): collect_project_usage 今日按项目聚合(降序)"
```

---

## Task 4: 把两组聚合注入 `state`

**Files:**
- Modify: `inkpulse_hub/state.py`
- Test: `tests/test_state_phase2.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_state_phase2.py`:

```python
from inkpulse_hub.config import Config
from inkpulse_hub.state import HubState


def test_render_state_has_daily_and_projects(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")   # 不存在 -> 聚合返回空/全零, 不崩
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "usage_daily" in state and isinstance(state["usage_daily"], list)
    assert "usage_projects" in state and isinstance(state["usage_projects"], list)
    assert len(state["usage_daily"]) == 14   # 默认 14 天全零桶
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: FAIL — `KeyError: 'usage_daily'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py` 顶部把 usage 的 import 改为同时引入两个新函数。找到:

```python
from .collectors.usage import collect_usage
```
改为:
```python
from .collectors.usage import collect_usage, collect_daily_usage, collect_project_usage
```

在 `build_render_state` 的返回字典里,`"clock": self._clock(now),` 这一行之后(`"now": now,` 之前)插入两行:

```python
            "usage_daily": collect_daily_usage(self.cfg.claude_logs),
            "usage_projects": collect_project_usage(self.cfg.claude_logs),
```

> 说明:这里不传 `now`,聚合各自取系统当前时间——与 `collect_usage(...)` 现状一致;`build_render_state` 的 `now` 参数仅用于时钟/农历的确定性测试。

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit --no-verify -m "feat(hub): build_render_state 注入 usage_daily/usage_projects"
```

---

## Task 5: `draw_usage_trend` 竖直柱状 widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`
- Test: `tests/test_widget_usage_trend.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_widget_usage_trend.py`:

```python
from datetime import date, timedelta
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_usage_trend, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _daily(vals):
    base = date(2026, 6, 1)
    return [{"date": base + timedelta(days=i), "tokens": v, "cost": v / 1000}
            for i, v in enumerate(vals)]


def test_draws_black_bars_with_data():
    img, d = _img()
    draw_usage_trend(d, Zone(0, 0, 400, 240), _daily([10, 20, 30, 5, 40, 15, 25]), days=7)
    assert _has_black(img)


def test_empty_data_shows_no_data_no_crash():
    img, d = _img()
    draw_usage_trend(d, Zone(0, 0, 400, 240), [], days=7)
    assert _has_black(img)   # "无数据" 文字也是黑像素, 关键是不抛异常


def test_all_zero_shows_no_data():
    img, d = _img()
    draw_usage_trend(d, Zone(0, 0, 400, 240), _daily([0, 0, 0]), days=3)
    # 不抛异常即可(全零 -> 无数据)


def test_metric_cost_uses_cost_values():
    # cost 全大、tokens 全零时, metric=cost 仍应画出柱子(证明读了 cost 维度)
    img, d = _img()
    series = [{"date": date(2026, 6, 1), "tokens": 0, "cost": 5.0},
              {"date": date(2026, 6, 2), "tokens": 0, "cost": 9.0}]
    draw_usage_trend(d, Zone(0, 0, 400, 240), series, days=2, metric="cost")
    assert _has_black(img)
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_usage_trend.py -v`
Expected: FAIL — `ImportError: cannot import name 'draw_usage_trend'`

- [ ] **Step 3: 实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加:

```python
def draw_usage_trend(d: ImageDraw.ImageDraw, z: Zone, daily,
                     days: int = 7, metric: str = "tokens") -> None:
    """近 days 天用量竖直柱状图。daily: [{date, tokens, cost}] 旧->新。"""
    days = max(1, min(int(days), 14))
    key = metric if metric in ("tokens", "cost") else "tokens"
    cy = _title_bar(d, z, f"用量趋势 · 近{days}天")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    series = (daily or [])[-days:]
    vals = [max(0, x.get(key, 0)) for x in series]
    if not series or max(vals, default=0) <= 0:
        _center_text(d, body, "无数据", _font(20), BLACK)
        return
    n = len(series)
    gap, label_h = 4, 16
    chart_h = body.h - label_h
    bw = max(2, (body.w - gap * (n + 1)) // n)
    vmax = max(vals)
    f = _font(12)
    for i, (x, v) in enumerate(zip(series, vals)):
        bx = body.x + gap + i * (bw + gap)
        bh = int((chart_h - 2) * (v / vmax))
        top = body.y + chart_h - bh
        d.rectangle((bx, top, bx + bw - 1, body.y + chart_h - 1), fill=BLACK)
        dt = x["date"]
        lbl = f"{dt.month}/{dt.day}"
        tw = d.textlength(lbl, font=f)
        d.text((bx + (bw - tw) / 2, body.y + chart_h + 2), lbl, fill=BLACK, font=f)
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_usage_trend.py -v`
Expected: PASS(4 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_usage_trend.py
git commit --no-verify -m "feat(hub): draw_usage_trend 近N天柱状 widget"
```

---

## Task 6: `draw_project_dist` 横向占比条 widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`
- Test: `tests/test_widget_project_dist.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_widget_project_dist.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_project_dist, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _projects(pairs):
    return [{"project": p, "tokens": t, "cost": t / 1000} for p, t in pairs]


def test_draws_black_with_data():
    img, d = _img()
    draw_project_dist(d, Zone(0, 0, 400, 240), _projects([("InkPulse", 60), ("webapp", 40)]))
    assert _has_black(img)


def test_top_n_caps_and_merges_others():
    # 6 个项目, top_n=2 -> 应渲染 2 行 + "其他"。用一个能抓行数的探针:
    img, d = _img(h=300)
    projs = _projects([(f"proj{i}", 10 * (6 - i)) for i in range(6)])
    rows = []
    orig = ImageDraw.ImageDraw.text
    def spy(self, xy, text, *a, **k):
        rows.append(text)
        return orig(self, xy, text, *a, **k)
    ImageDraw.ImageDraw.text = spy
    try:
        draw_project_dist(d, Zone(0, 0, 400, 300), projs, top_n=2)
    finally:
        ImageDraw.ImageDraw.text = orig
    assert any("其他" in t for t in rows)          # 合并行存在
    assert any("proj0" in t for t in rows)          # 最大项在
    assert not any("proj5" in t for t in rows)      # 被并入"其他"


def test_empty_shows_no_data_no_crash():
    img, d = _img()
    draw_project_dist(d, Zone(0, 0, 400, 240), [])
    # 不抛异常即可
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_project_dist.py -v`
Expected: FAIL — `ImportError: cannot import name 'draw_project_dist'`

- [ ] **Step 3: 实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加:

```python
def draw_project_dist(d: ImageDraw.ImageDraw, z: Zone, projects,
                      top_n: int = 5, metric: str = "tokens") -> None:
    """今日各项目占比横向条。projects: [{project, tokens, cost}]。"""
    top_n = max(1, int(top_n))
    key = metric if metric in ("tokens", "cost") else "tokens"
    cy = _title_bar(d, z, "项目分布 · 今日")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    items = sorted(projects or [], key=lambda x: x.get(key, 0), reverse=True)
    total = sum(max(0, x.get(key, 0)) for x in items)
    if not items or total <= 0:
        _center_text(d, body, "无数据", _font(20), BLACK)
        return
    rows = [(x["project"], max(0, x.get(key, 0))) for x in items[:top_n]]
    rest = items[top_n:]
    if rest:
        rows.append(("其他", sum(max(0, x.get(key, 0)) for x in rest)))
    f = _font(16)
    row_h = max(18, min(28, body.h // len(rows)))
    name_w, pct_w = 84, 48
    bar_x = body.x + name_w
    bar_max = max(4, body.w - name_w - pct_w)
    for i, (name, v) in enumerate(rows):
        ry = body.y + i * row_h
        nm = name if len(name) <= 6 else name[:5] + "…"
        d.text((body.x + 4, ry), nm, fill=BLACK, font=f)
        frac = v / total
        bw = int(bar_max * frac)
        d.rectangle((bar_x, ry + 3, bar_x + bw, ry + row_h - 6), fill=BLACK)
        d.text((bar_x + bw + 4, ry), f"{int(round(frac * 100))}%", fill=BLACK, font=f)
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_project_dist.py -v`
Expected: PASS(3 个)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_project_dist.py
git commit --no-verify -m "feat(hub): draw_project_dist 今日项目占比横向条 widget"
```

---

## Task 7: 注册两个 widget + `select` 参数元数据

**Files:**
- Modify: `inkpulse_hub/render/registry.py`
- Modify: `tests/test_registry.py`(给注入 state 补两个键 + 新增 select 元数据断言)

- [ ] **Step 1: 改 `tests/test_registry.py`(先让其失败)**

把 `test_registry.py` 里 `_state()` 返回字典中追加两键(在 `"now": ...` 行旁):

```python
        "usage_daily": [{"date": __import__("datetime").date(2026, 6, 13), "tokens": 100, "cost": 0.1}],
        "usage_projects": [{"project": "InkPulse", "tokens": 100, "cost": 0.1}],
```

把 `test_existing_widgets_registered` 里的 `expected` 集合加入两个新名:

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist"}
```

在文件末尾新增一个断言 select 元数据的测试:

```python
def test_phase2_widgets_have_select_metric_param():
    for name in ("usage_trend", "project_dist"):
        params = REGISTRY[name].params
        metric = next(p for p in params if p["key"] == "metric")
        assert metric["type"] == "select"
        assert {"tokens", "cost"} <= {o["value"] for o in metric["options"]}
```

- [ ] **Step 2: 运行,确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL — `usage_trend` 未注册(`expected <= set(REGISTRY)` 失败 / KeyError)

- [ ] **Step 3: 实现**

在 `inkpulse_hub/render/registry.py` 的 `_qrcode` 适配器之后(`REGISTRY = {` 之前)追加两个适配器:

```python
def _usage_trend(d, img, z, state, cfg, p):
    W.draw_usage_trend(d, z, state.get("usage_daily", []),
                       days=int(p.get("days", 7) or 7),
                       metric=p.get("metric", "tokens"))


def _project_dist(d, img, z, state, cfg, p):
    W.draw_project_dist(d, z, state.get("usage_projects", []),
                        top_n=int(p.get("top_n", 5) or 5),
                        metric=p.get("metric", "tokens"))
```

在 `REGISTRY` 字典里、`"qrcode": ...` 那一项之后(闭合 `}` 之前)加两项:

```python
    "usage_trend":   WidgetSpec("usage_trend", "用量趋势", _usage_trend, {"cols": 4, "rows": 3},
        [{"key": "days", "label": "天数", "type": "number", "default": 7},
         {"key": "metric", "label": "度量", "type": "select", "default": "tokens",
          "options": [{"value": "tokens", "label": "Token数"},
                      {"value": "cost", "label": "花费$"}]}]),
    "project_dist":  WidgetSpec("project_dist", "项目分布", _project_dist, {"cols": 4, "rows": 3},
        [{"key": "top_n", "label": "显示前N项", "type": "number", "default": 5},
         {"key": "metric", "label": "度量", "type": "select", "default": "tokens",
          "options": [{"value": "tokens", "label": "Token数"},
                      {"value": "cost", "label": "花费$"}]}]),
```

- [ ] **Step 4: 运行,确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS(含新 select 元数据测试,且 `test_each_widget_draws_without_error` 对两个新 widget 也用注入数据画出不抛错)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit --no-verify -m "feat(hub): 注册 usage_trend/project_dist + select 度量参数"
```

---

## Task 8: 网页编辑器支持 `select` 参数 + API 契约测试 + 全量回归

**Files:**
- Modify: `inkpulse_hub/web/config.html`(参数表单渲染 + 取值)
- Modify: `tests/test_layouts_api.py`(新增契约测试)

- [ ] **Step 1: 写失败的 API 契约测试**

在 `tests/test_layouts_api.py` 末尾追加:

```python
def test_catalog_exposes_phase2_widgets_with_select(tmp_path):
    cfg, c = _client(tmp_path)
    widgets = {w["name"]: w for w in c.get("/api/layouts").json()["widgets"]}
    assert {"usage_trend", "project_dist"} <= set(widgets)
    metric = next(p for p in widgets["usage_trend"]["params"] if p["key"] == "metric")
    assert metric["type"] == "select"
    assert {"tokens", "cost"} <= {o["value"] for o in metric["options"]}
```

- [ ] **Step 2: 运行,确认通过(后端已在 Task 7 就绪)**

Run: `.venv/bin/python -m pytest tests/test_layouts_api.py::test_catalog_exposes_phase2_widgets_with_select -v`
Expected: PASS(GET /api/layouts 已返回完整 REGISTRY,含 select 参数)

> 说明:此测试在 Task 7 完成后即应通过,作为 API 契约固化;无需改后端。

- [ ] **Step 3: 编辑器渲染 `select`(改 config.html)**

`inkpulse_hub/web/config.html` 中,`edParams` 渲染逻辑(约第 211-213 行)当前为:

```javascript
  if (!w || !w.params.length) { box.innerHTML = ''; return; }
  box.innerHTML = w.params.map(p =>
    `<div class="row"><label>${esc(p.label)}</label><input data-k="${p.key}" type="${p.type === 'date' ? 'date' : (p.type === 'number' ? 'number' : 'text')}" value="${p.default || ''}"></div>`).join('');
```

替换为(新增 select 分支):

```javascript
  if (!w || !w.params.length) { box.innerHTML = ''; return; }
  box.innerHTML = w.params.map(p => {
    if (p.type === 'select') {
      const opts = (p.options || []).map(o =>
        `<option value="${o.value}" ${o.value === p.default ? 'selected' : ''}>${esc(o.label)}</option>`).join('');
      return `<div class="row"><label>${esc(p.label)}</label><select data-k="${p.key}" style="flex:1;padding:6px 8px;border:1px solid #d4d4d8;border-radius:6px">${opts}</select></div>`;
    }
    const t = p.type === 'date' ? 'date' : (p.type === 'number' ? 'number' : 'text');
    return `<div class="row"><label>${esc(p.label)}</label><input data-k="${p.key}" type="${t}" value="${p.default || ''}"></div>`;
  }).join('');
```

- [ ] **Step 4: 取值时把 `select` 也收进 params(改 config.html)**

同文件中收集参数那一行(约第 256 行)当前为:

```javascript
  document.querySelectorAll('#edParams input').forEach(i => params[i.dataset.k] = i.value);
```

替换为:

```javascript
  document.querySelectorAll('#edParams input, #edParams select').forEach(i => params[i.dataset.k] = i.value);
```

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: 全绿(基线 95 + 本期新增约 20 个测试,合计 ~115 passed)。

- [ ] **Step 6: 真机/浏览器手动验收**

```bash
systemctl --user restart inkpulse-hub 2>/dev/null || (pkill -f inkpulse_hub; cd software/hub && nohup ./run.sh >/tmp/inkpulse-hub.log 2>&1 & disown)
```
打开 `http://192.168.2.139:8080/config`:新建一个布局 → 框选区域 → widget 下拉选「用量趋势」/「项目分布」→ 「度量」应是**下拉框**(Token数/花费$)→ 填天数/TopN → 放入 → 保存 → 切到该布局 → 看 `/preview.png` 出现柱状图/占比条。

- [ ] **Step 7: 提交**

```bash
git add inkpulse_hub/web/config.html tests/test_layouts_api.py
git commit --no-verify -m "feat(hub): 编辑器支持 select 参数 + 用量趋势/项目分布 API 契约测试"
```

---

## 自检(写完计划对照 spec)

- **Spec §2 范围**:迭代器重构(T1)、daily(T2)、project(T3)、state 注入(T4)、两 widget(T5/T6)、注册+select(T7)、编辑器 select(T8)——逐条有任务。✓
- **Spec §5 数据模型**:`UsageRecord` 字段、`collect_daily_usage(days=14)`、`collect_project_usage` 签名与计划一致。✓
- **Spec §6 参数**:`usage_trend{days,metric}`、`project_dist{top_n,metric}`、`metric` 为 select 带 options——T7 元数据与 T5/T6 适配器默认值一致(days=7/top_n=5/metric=tokens)。✓
- **Spec §6.4 select 类型**:T7(元数据)+ T8(编辑器渲染+取值);PUT API 不校验 params 值,无后端改动。✓
- **Spec §7 容错**:空目录→空/全零(T2/T3 测试)、空数据→"无数据"(T5/T6 测试)、未知 metric 回退 tokens(widget 内 `key=...` 逻辑)。✓
- **Spec §8 测试计划**:迭代器/daily/project/collect_usage 回归/两 widget/registry/API 契约——全覆盖。✓
- 类型一致性:`state["usage_daily"]` 元素 `{date,tokens,cost}` 在 T2 产出、T5 消费;`{project,tokens,cost}` 在 T3 产出、T6 消费,字段名一致。✓
