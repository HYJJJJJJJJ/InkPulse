# 阶段①：hub 多布局渲染

日期：2026-06-13
状态：待评审
所属：可视化配置多布局系统（整体 3 阶段之一）

## 背景与目标

hub 当前只渲染 2 种布局（dash 仪表盘 / photo 相框），`engine.render_frame` 按 `cfg.layout`(widget 列表) 顺序画 widget。

本阶段把 mockup-explorer 里的另外 4 种布局做进 hub，并把 engine 重构成**布局注册表**结构，让加布局变成"加一个函数"。布局本阶段先由 config 指定（web 选布局留阶段②）。目标尺寸只做当前设备的 **800×480**。

最终支持 6 种布局：

| 布局 | 组成 |
|---|---|
| dash（已有） | header + claude 状态 + usage + todos 环绕 |
| photo（已有） | 整屏三色照片 + 角标 |
| usage（新） | 巨号 token + 5h 进度环为主，状态/待办压小 |
| todo（新） | 大号待办清单为主 + 万年历/状态侧栏 |
| clock（新） | 巨型时钟 + 农历/节气 + 月历，信息为页脚 |
| split（新） | 左(状态+用量) / 右(万年历+待办) 四模块等权 |

## 设计

### 1. 布局注册表（engine 重构）

- 定义 `LAYOUTS: dict[str, Callable]`，每个布局一个渲染函数：
  `draw_dash / draw_photo / draw_usage / draw_todo / draw_clock / draw_split`，
  签名统一 `def draw_xxx(d, img, state, cfg) -> None`（photo 需要 img 贴图，故传 img）。
- `render_frame` 改为：取当前布局名 → `LAYOUTS[name](d, img, state, cfg)`；未知名回退 `dash`。
- 现有 dash/photo 渲染逻辑封装进 `draw_dash` / `draw_photo`（行为不变）。

### 2. config 指定布局

- `config.py` 新增 `layout_name: str = "dash"`（从 `config.yaml` 的 `layout.name` 读）。
- 保留旧 `layout.widgets` 兼容（dash 内部仍可用其顺序），但布局选择以 `layout_name` 为准。

### 3. 新 widget（widgets 扩展）

- `draw_big_clock(d, z, now)`：巨型 `HH:MM`（字号按 zone 自适应，黑色，冒号可红）。
- `draw_month_calendar(d, z, now)`：当月 7×6 网格 + 今日高亮(红) + 表头周几；农历用 cnlunar 算当月（格内小字可选）。
- `draw_usage_ring(d, z, usage)`：5h 窗口占用百分比画圆环进度（Pillow `arc`，满则红）。
- usage/todo/split 大量复用现有 `draw_header / draw_usage / draw_todos / draw_claude_status`，只是 zone 重排。

### 4. 各新布局组成（800×480，具体坐标实现时参照 mockup-explorer）

- **usage**：上半巨号 token + 进度环；下半状态/待办压缩成小条。
- **todo**：左 2/3 大号待办清单；右 1/3 侧栏(万年历 + 状态)。
- **clock**：上部巨型时钟 + 农历/节气；下部月历；最底信息页脚。
- **split**：竖分两栏，左(header+状态+用量)，右(万年历+待办)。

## 数据流

- 复用 `state.build_render_state`（已有 clock/lunar/usage/todos/claude/env）。
- 月历需要"当月各日 + 今日"：由 widget 内用 `now` + `cnlunar`/`calendar` 现算，不进 state。

## 错误处理

- 未知 layout_name → 回退 dash + log warning。
- photo 布局无图 → 回退 dash（沿用现有逻辑）。
- 新 widget 数据缺失（如 usage 无数据）→ 画占位，不崩。

## 测试（TDD，hub 侧 pytest）

- 新 widget：`draw_big_clock / draw_month_calendar / draw_usage_ring` 各渲染不崩 + 关键像素断言（如今日格有红像素、进度环高占用有红）。
- 各布局：`render_frame` 在每个 layout_name 下产出 800×480 帧不崩、字节数正确。
- config：`layout_name` 默认/yaml 覆盖。

## 落地顺序

1. engine：抽 `LAYOUTS` 注册表 + 把现有 dash/photo 封装成 `draw_dash/draw_photo`（保持行为，回归测试绿）。
2. config：加 `layout_name`。
3. 新 widget：`draw_big_clock` → `draw_usage_ring` → `draw_month_calendar`（TDD）。
4. 新布局：`draw_usage` → `draw_split` → `draw_todo` → `draw_clock`（组合 widget，TDD 渲染不崩）。
5. 本地 preview 逐布局看效果 + 真机抽验。

## 风险

- 月历 + 农历每格小字在 800×480 下可能偏挤，必要时只标今日农历 + 节气。
- 巨型时钟/进度环字号与圆弧需按 zone 调试，先粗后细。
- 坐标移植自 mockup-explorer(canvas) → Pillow，需逐布局比对预览。

## 非目标（留后续阶段）

- web 选布局 / 实时预览（阶段②）。
- 参数配置 / 照片管理（阶段③）。
- 400×300、240×416 小屏尺寸（当前单一 800×480 设备）。
