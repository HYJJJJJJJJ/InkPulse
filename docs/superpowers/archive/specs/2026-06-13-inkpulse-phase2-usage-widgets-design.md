# InkPulse 第二期(只读批):用量趋势 + 项目分布(设计文档)

> 日期:2026-06-13 · 状态:已通过设计评审,待写实现计划
> 关联:[网格布局系统设计(第一期)](2026-06-13-inkpulse-grid-layout-system-design.md) · 实现计划见 `docs/superpowers/plans/`

## 1. 背景与目标

第一期把布局变成了数据驱动的网格系统:加新功能 = 写一个 `draw_xxx` + 注册一行,不再碰布局引擎。本设计是 **第二期的第一批**——按第一期 spec §9 规划的"本地数据 widget"中**零外部 API 风险、零新存储**的两个:

- **用量趋势**:近 N 天用量柱状图。
- **项目分布**:今日各项目用量占比(横向条)。

二者的数据都来自现有 Claude Code 会话日志(`~/.claude/projects/**/*.jsonl`),只需扩展现有 `collectors/usage.py` 的聚合维度,**不引入任何新数据管线或存储**。

第二期剩余两个 widget(习惯打卡、温湿度曲线)各自需要新存储/交互,**另开 spec**,不在本期范围。

## 2. 范围

### 本期做(In Scope)
- 扩展 `collectors/usage.py`:把现有 jsonl 解析抽成共享迭代器,新增**按日聚合**与**按项目聚合**两个函数。
- `state` 新增 `usage_daily`、`usage_projects` 两键(在 `build_render_state` 预算)。
- 两个新 widget:`usage_trend`(竖直柱状)、`project_dist`(横向条),注册进 REGISTRY。
- 新增参数类型 **`select`**(下拉),让"度量(tokens/cost)"在网页编辑器里可选。
- 配套测试(collector 聚合 + widget 绘制 + 参数行为)。

### 本期不做(Out of Scope / YAGNI)
- 习惯打卡、温湿度曲线(各自另开 spec,需新存储/交互/采集器)。
- 第三期联网 widget(天气/日程/行情)。
- 单遍扫描优化(三个聚合函数各自扫一遍日志,见 §7)。
- sparkline / 图表库(纯 Pillow 画)。
- 度量值的服务端校验(PUT API 不校验 params 值,沿用现状)。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 本期范围 | **只做两个只读 widget** | 零外部 API、零新存储,快且低风险;打卡/温度曲线各自要新存储,另开 spec |
| 数据放置 | **预算进 `state`,widget 按参数切片** | 沿用现有"collector→state,adapter 只读 state"模式;registry 测试可注入数据,确定性好;IO 集中 |
| 度量(纵轴) | **做成 widget 参数 `metric`(select)** | 用户在编辑器里选 tokens/cost,无需为两套度量各做一个 widget |
| token 口径 | **净 input+output(不含缓存)** | 与现有 5h 窗口口径一致;缓存量级极大(可上亿)会压扁所有柱子,失去趋势意义 |
| 项目识别 | **`project = basename(cwd)`** | 每条日志记录都带 `cwd` 字段,稳健,无需解码目录名 |
| 颜色 | **纯黑,无红色告警** | 趋势/占比无"告警"语义;红色在本系统专留给"需注意"(超预算/临近等) |
| 默认网格跨度 | **均 4×3 格** | 与 usage/calendar 同档,放得下柱状/条形 + 标题栏 |

## 4. 架构总览

```
build_render_state(now)
  ├─ usage         = collect_usage(...)              # 现有, 不变
  ├─ usage_daily   = collect_daily_usage(logs, 14)   # 新: 近14天每日桶
  └─ usage_projects= collect_project_usage(logs)     # 新: 今日每项目桶

render_frame → placement(widget="usage_trend", params={days,metric})
  └─ adapter 读 state["usage_daily"] → 取末 days 天 → 按 metric 取值 → draw_usage_trend
     placement(widget="project_dist", params={top_n,metric})
  └─ adapter 读 state["usage_projects"] → 按 metric 排序取 top_n + 其他 → draw_project_dist
```

要点:数据层算"全量"(近 14 天 / 所有项目),widget 在绘制时按自己的参数(days/top_n/metric)切片。这样 `state` 与参数解耦,adapter 保持纯函数(只读 state + params),测试可注入数据。

### 模块划分(单一职责)
- `collectors/usage.py`(改):抽出 `_iter_usage_records()` 共享迭代器;`collect_usage` 改用它(行为不变);新增 `collect_daily_usage`、`collect_project_usage`。
- `state.py`(改):`build_render_state` 增 `usage_daily`、`usage_projects` 两键。
- `render/widgets.py`(改):新增 `draw_usage_trend`、`draw_project_dist`。
- `render/registry.py`(改):注册两个 widget + 适配器;`metric` 参数用新类型 `select`。
- `web/config.html`(改):参数表单支持 `type: "select"`(渲染下拉框)。

## 5. 数据模型

### 5.1 共享迭代器(`collectors/usage.py`)
```python
@dataclass
class UsageRecord:
    dt: datetime          # 本地时区
    project: str          # basename(cwd), 缺失记 "?"
    input: int
    output: int
    cache_read: int
    cache_create: int
    model: str | None

def _iter_usage_records(logs_dir) -> Iterator[UsageRecord]:
    # 遍历 **/*.jsonl, 逐条 yield 带 usage 的记录(坏行/无时间戳/无 usage 跳过)
```
现有 `collect_usage` 改为消费此迭代器重建"今日累计 + 5h 窗口"(口径、字段完全不变)。

### 5.2 按日聚合
```python
def collect_daily_usage(logs_dir, days=14, now=None) -> list[dict]:
    # 返回近 days 天(含今天)每日桶, 旧→新, 无数据的天补零:
    # [{"date": date, "tokens": int, "cost": float}, ...]   长度恒 = days
```
- `tokens = input + output`(净),`cost` 按现有 `_PRICING` 估算。
- 缺数据的日期补零桶(保证柱状图 X 轴连续)。

### 5.3 按项目聚合(今日)
```python
def collect_project_usage(logs_dir, today=None, now=None) -> list[dict]:
    # 今日每个项目一桶, 按 tokens 降序:
    # [{"project": str, "tokens": int, "cost": float}, ...]
```
- 仅统计今日记录;空 → 空列表。

### 5.4 注入 state
`build_render_state` 新增:
```python
"usage_daily":    collect_daily_usage(self.cfg.claude_logs),
"usage_projects": collect_project_usage(self.cfg.claude_logs),
```

## 6. Widget 与参数

### 6.1 `usage_trend`(竖直柱状,近 N 天)
```
┌ 用量趋势 · 近7天 ────────────┐
│                  ▆           │
│        ▃    ▅    █    ▆      │
│   ▂    █    █    █    █   ▃  │
│ 6/07 6/08 6/09 6/10 6/11 …  │
└──────────────────────────────┘
```
- 顶部标题栏(复用 `_title_bar`);其下等宽柱;X 轴标 `M/D`。
- 柱高按区间内最大值归一化;全零时画基线 + "无数据"。
- 参数:`days`(number, 默认 7,绘制时 clamp 到 1..14)、`metric`(select: tokens/cost,默认 tokens)。

### 6.2 `project_dist`(横向条,今日 Top-N 占比)
```
┌ 项目分布 · 今日 ─────────────┐
│ InkPulse  ▓▓▓▓▓▓▓▓▓▓  62%   │
│ webapp    ▓▓▓▓▓        28%   │
│ 其他      ▓▓            10%   │
└──────────────────────────────┘
```
- 按 `metric` 降序;取前 `top_n`,其余合并为"其他"行。
- 每行:项目名(截断)+ 横条(长度∝占比)+ 百分比。
- 空数据 → 居中"无数据"。
- 参数:`top_n`(number, 默认 5)、`metric`(select,默认 tokens)。

### 6.3 适配器(`registry.py`)
```python
def _usage_trend(d, img, z, state, cfg, p):
    W.draw_usage_trend(d, z, state.get("usage_daily", []),
                       days=int(p.get("days", 7)), metric=p.get("metric", "tokens"))

def _project_dist(d, img, z, state, cfg, p):
    W.draw_project_dist(d, z, state.get("usage_projects", []),
                        top_n=int(p.get("top_n", 5)), metric=p.get("metric", "tokens"))
```
注册项(`default_span` 均 `{cols:4, rows:3}`):
```python
"usage_trend": WidgetSpec("usage_trend", "用量趋势", _usage_trend, {"cols":4,"rows":3},
    [{"key":"days","label":"天数","type":"number","default":7},
     {"key":"metric","label":"度量","type":"select","default":"tokens",
      "options":[{"value":"tokens","label":"Token数"},{"value":"cost","label":"花费$"}]}]),
"project_dist": WidgetSpec("project_dist", "项目分布", _project_dist, {"cols":4,"rows":3},
    [{"key":"top_n","label":"显示前N项","type":"number","default":5},
     {"key":"metric","label":"度量","type":"select","default":"tokens",
      "options":[{"value":"tokens","label":"Token数"},{"value":"cost","label":"花费$"}]}]),
```

### 6.4 新参数类型 `select`
- 数据约定:params 项 `{"key","label","type":"select","default","options":[{"value","label"}]}`。
- `config.html` 编辑器:`type==="select"` 时渲染 `<select>`(选项取 `options`),否则沿用现有 text/date/number 输入框。
- 后端 `PUT /api/layouts` 不校验 params 值(沿用现状),故无 API 改动。

## 7. 错误处理与性能

- **日志目录不存在 / 空**:聚合返回空(daily 仍返回长度 = days 的全零桶);widget 画"无数据"。
- **坏行 / 无时间戳 / 无 usage**:迭代器跳过(沿用现有容错)。
- **未知 metric**:回退 tokens。
- **widget 内异常**:被 engine 的 per-widget 隔离捕获,画 `n/a`(第一期已有)。
- **性能**:三个聚合各扫一遍日志(每次渲染)。现有 `collect_usage` 本就每次渲染扫一遍;新增两个 widget 仅在出现在当前布局时其数据才被用到,但 `build_render_state` 当前对所有 widget 一律预算。渲染非高频(设备 ~10s 轮询、变化才出图),**本期接受三遍扫描,不做单遍优化**(YAGNI;日志规模过大再议)。

## 8. 测试计划(pytest,沿用现有风格)

合成数据:测试写若干 tmp `.jsonl`(含 `timestamp` / `cwd` / `message.usage` / `message.model`),指向 `cfg.claude_logs = tmp_dir`。
- `_iter_usage_records`:产出条数、字段、坏行跳过。
- `collect_daily_usage`:桶数恒 = days、日期连续、缺日补零、tokens/cost 求和正确、空目录全零。
- `collect_project_usage`:按 cwd basename 分组、今日过滤、降序、空目录空列表。
- `collect_usage` **回归**:重构后今日/窗口口径不变(现有测试必须仍绿)。
- `draw_usage_trend`:有数据画黑像素;全零画"无数据"不崩;`days` clamp;`metric` 切换改变柱高来源。
- `draw_project_dist`:画黑像素;`top_n` 截断 + "其他"合并;空数据"无数据";`metric` 切换。
- `registry`:两 widget 已注册、能在注入 state 下绘制不抛错;`metric` 参数 `type=="select"` 且带 `options`。
- `/api/layouts` GET:widget 目录含 `usage_trend`/`project_dist`,其 params 含 select 项(契约测试)。

## 9. 新增依赖

无。纯复用现有 Pillow / 标准库。

## 10. 验收标准

1. 网页编辑器里能放入"用量趋势""项目分布",并通过下拉选择度量(tokens/cost);保存、切换、在预览/设备上看到图。
2. 用量趋势按 `days` 显示对应天数柱子;项目分布按 `top_n` 显示前 N 项 + 其他,占比正确。
3. 无日志/空数据时两 widget 画"无数据",整帧不崩。
4. `collect_usage` 现有行为不变,全部测试通过。
