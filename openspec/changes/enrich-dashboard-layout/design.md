## Context

仪表盘渲染全在 Hub 端(`software/hub/inkpulse_hub/render/`):`engine.py` 在 800x480 RGB 画布上按 `ZONES` 调各 `draw_*`(`widgets.py`),再由 `planes.py` 严格量化(像素恰等 `(0,0,0)`/`(255,0,0)` 才进黑/红 plane)成 96000B 双 plane;`engine.py` 已设 `d.fontmode="1"` 关抗锯齿(否则灰边在三色量化时丢失)。时钟由 `state.py:_clock(now)` 生成。设备是瘦客户端,只 blit,**本次完全不动固件与帧协议**。

约束:面板只有黑/白/红、无灰阶;全刷约 20s;红色刷新更慢、残影更顽固(项目早期踩过红残影,靠开机 `epd_clear` 压住);中文需 CJK 字体(`_CJK_FONT_PATHS` 已有兜底)。

## Goals / Non-Goals

**Goals:**
- 头部显示完整日期时间 `2026-06-12 11:23 周四` + 农历行(农历日期 + 生肖年 + 节气,节日标红)。
- 红色变为"强调 + 告警"(哲学 B),但克制使用,让红有意义地常态出现又不伤刷新/残影。
- 用现有数据丰富视觉:分区标题栏、hero 数字、露出 `since`/`session_count`/窗口百分比、真复选框。

**Non-Goals:**
- 不改帧协议/固件/设备端;不改 todo 数据结构(due/priority);不动 components 抽象;不引入联网类数据源。

## Decisions

- **农历库选 `cnlunar`(纯 Python 查表)**,而非 `zhdate`(太朴素,只农历日期+干支)或 `lunar_python`/`sxtwl`(更重/含 C 扩展)。`cnlunar` 纯算法、跨平台好装,且能给"农历日期 + 生肖年 + 节气 + 节日"刚好一行的信息量,节气对桌面屏是有味道的点缀。
- **农历在 `state.py` 内与 `_clock` 一起算**,不新建 collector。理由:它是 `now` 的纯函数、无 I/O,放进 `build_render_state` 的 `clock`/新增 `lunar` 字段即可,符合"采集器各有数据源"的现有结构最小化原则。
- **红色策略:克制版哲学 B**。固定强调红 = **日期**(始终红,给屏一个稳定的红存在);告警红 = 状态(等输入/出错,保留)、窗口占用 >90%、超预算 hero 数字、节日。**分区标题栏用黑底反白(结构),不用红** —— 三条红标题栏会显著增加红面积→残影/刷新代价,而结构性分区不需要"告警含义"。这样红始终对应"日期 + 需要注意的事",语义干净。备选(红标题栏)因红残影代价被否。
- **hero 数字红 = 超预算告警**,而非永远红。`config.yaml` 增加可选 `usage.budget_usd`(默认 null);设了且 `cost_usd > budget_usd` 才把放大的花费数字标红,否则黑(靠字号强调)。保持红=告警语义。
- **分区标题栏**:黑色填充矩形 + 白字(Pillow 先 `rectangle(fill=BLACK)` 再 `text(fill=WHITE)`),替代当前细下划线,结构清晰且零红。
- **免费数据露出**:`claude.since`(epoch)→ 渲染时算 `now-since` 成"已 N 分钟/小时";`usage.session_count`→"今日 N 会话";`window_used_ratio`→ 百分比数字附在窗口条旁。均已在模型里,无数据管线改动。
- **header Zone 60→约 76px** 容两行;`engine.py` 中 `claude_status`/`usage` 的 y 起点与高度顺移(整体仍 480 高),`todos` 区相应微调。布局参数集中在 `ZONES`。

## Risks / Trade-offs

- [红色用多了→刷新变慢 + 残影累积] → 克制:固定红仅"日期",其余红都是告警(低频);标题栏走黑色;真机回归看残影。
- [`cnlunar` 实际 API/输出格式与设想不符(字段名、节气/节日取法)] → 实现首步先写一个小 spike 确认 API,再封装 `state.py` 的农历函数;农历字符串组装加单测(给定固定日期断言输出)。
- [节气/节日并非每天都有,空值处理] → 农历行按"有则拼上、无则省略"组装,避免出现空的 ` · `。
- [反白标题栏白字依赖背景为红/黑填充] → 必须先画填充矩形再画白字;在三色量化下白字=不进任何 plane(留白),需确保矩形为纯黑、字为纯白,`fontmode="1"` 下无灰边。
- [header 增高导致与下方 Zone 重叠/错位] → 所有 y 偏移集中在 `engine.py:ZONES`,改完用 `/preview.png` 在电脑端逐项核对,不依赖真机。
- [`budget_usd` 是新配置项] → 可选、默认 null(不启用即行为=花费数字永远黑),向后兼容。
