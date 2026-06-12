## Why

当前仪表盘是四块纯文本(header / claude_status / usage / todos),没有分区结构、图标或视觉层级,像一张终端打印,信息密度低、不耐看。更关键的是,这块墨水屏是**黑/白/红三色**面板,但红色只绑在 `claude_status` 的"等你输入 / 出错"一个条件上——常态(working)下整屏纯黑白,红色 90% 时间闲置,等于白付了三色面板的成本。此外用户希望头部时间显示完整日期并增加农历信息。

## What Changes

- **头部重设计**:时钟从简写 `6/11 周四 14:32` 改为完整 `2026-06-12 11:23 周四`;新增第二行**农历信息**(农历日期 + 生肖年 + 节气,遇节日自动标红),header 区高度相应增加。
- **红色策略改为"强调 + 告警"(哲学 B)**:红色不再只表告警,也用于视觉强调(日期、分区标题栏、hero 主数字);告警面扩展到 窗口占用 >90%、超预算、节日。其余正文保持克制,护刷新、防红残影。
- **视觉丰富化(全用现有数据,零数据管线改动)**:反白/红**分区标题栏**替代细下划线;`usage` 花费做成放大的 **hero 数字**(超预算变红);露出已算出但没显示的**免费数据**(`claude.since`→状态持续时长、`usage.session_count`→今日会话数、窗口占用百分比);`todos` 用真复选框字形 + 完成项删除线。
- **新增依赖**:Python 农历库 `cnlunar`(纯算法查表,不联网)。

非目标:不改帧协议(仍 96000B 双 plane)、不碰固件(设备只 blit)、不改 todo 数据结构(due/priority 暂不做)、不动换屏/换数据源的 components 抽象。

## Capabilities

### New Capabilities
- `dashboard-rendering`: 仪表盘渲染契约——各 widget 的视觉规则、红色使用规则(强调+告警)、头部日期/农历格式、用 Pillow 在 800x480 三色画布上排版并量化为双 plane 的约束。

### Modified Capabilities
<!-- openspec/specs/ 当前为空,无既有 spec 需要改 requirement,留空 -->

## Impact

- **代码**:`software/hub/inkpulse_hub/state.py`(时钟格式 + 农历计算)、`render/widgets.py`(各 `draw_*` 函数 + 红色规则)、`render/engine.py`(header Zone 高度/布局反流)。
- **依赖**:`software/hub/pyproject.toml` 新增 `cnlunar`。
- **测试**:`software/hub/tests/` 增/改渲染与农历相关用例(三色量化不变、红色出现条件、农历字符串)。
- **不受影响**:固件、`/frame` 帧协议(仍 96000B)、设备端(瘦客户端无感)、todo 数据结构、components 抽象。
