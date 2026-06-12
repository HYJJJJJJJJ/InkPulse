# dashboard-rendering Specification

## Purpose
TBD - created by archiving change enrich-dashboard-layout. Update Purpose after archive.
## Requirements
### Requirement: 头部显示完整日期时间与农历行
头部 SHALL 显示两行:第一行为完整公历日期时间 `YYYY-MM-DD HH:MM 周X`,第二行为农历信息。header 区高度 SHALL 增加以容纳两行,且下方各 widget 不被遮挡。

#### Scenario: 渲染完整日期时间
- **WHEN** 以本地时间 2026-06-12 11:23(周四)渲染头部
- **THEN** 第一行显示 `2026-06-12 11:23 周四`(年-月-日 时:分 周几)

#### Scenario: 头部新增农历行不挤压下方内容
- **WHEN** 渲染整帧
- **THEN** header 占据顶部约 76px 两行,`claude_status`/`usage`/`todos` 三区完整可见、无重叠

### Requirement: 农历信息显示
农历行 SHALL 由 `cnlunar` 纯算法计算(不联网),内容包含农历日期、生肖年与节气;字段缺失(如当日无节气)时 SHALL 省略该段而不留空分隔符。遇节日(如端午、春节)SHALL 显示节日名并用红色标记。

#### Scenario: 普通日农历
- **WHEN** 渲染一个非节日、含节气信息的农历日期
- **THEN** 农历行形如 `农历五月初七 · 乙巳蛇年 · 芒种`(各段以 ` · ` 分隔,无空段)

#### Scenario: 节日标红
- **WHEN** 渲染当日为传统节日(如端午)
- **THEN** 农历行包含节日名且节日名以红色 `(255,0,0)` 渲染

### Requirement: 红色仅用于强调与告警(克制版哲学 B)
渲染 SHALL 把红色限定于:固定强调(日期)、告警(claude 等输入/出错、窗口占用 >90%、超预算、节日)。分区标题栏 SHALL 用黑底白字、不用红。其余正文、待办文本、温湿度 SHALL 为黑色。

#### Scenario: 常态无多余红
- **WHEN** claude 状态为 `working`、窗口占用 ≤90%、未超预算、当日非节日
- **THEN** 帧中红色像素仅出现在日期处(标题栏、状态块、正文均为黑/白)

#### Scenario: 状态告警转红
- **WHEN** claude 状态为 `waiting_for_input` 或 `error`
- **THEN** 状态区(色块与标签)以红色渲染

#### Scenario: 窗口占用告警
- **WHEN** `window_used_ratio` > 0.90
- **THEN** 窗口占用的百分比数字以红色渲染

#### Scenario: 超预算告警
- **WHEN** 配置了 `usage.budget_usd` 且 `cost_usd` 超过该值
- **THEN** 放大的花费 hero 数字以红色渲染
- **WHEN** 未配置 `usage.budget_usd` 或未超预算
- **THEN** 花费 hero 数字以黑色渲染

### Requirement: 露出现有数据丰富信息
渲染 SHALL 显示已在数据模型中但当前未呈现的字段:claude 状态持续时长(由 `since` 算)、今日会话数(`session_count`)、窗口占用百分比(`window_used_ratio`)。不得为此引入新的数据采集来源。

#### Scenario: 状态持续时长
- **WHEN** `claude.since` 有值且距当前 12 分钟
- **THEN** 状态区显示形如 `已 12 分钟` 的持续时长

#### Scenario: 今日会话数
- **WHEN** `usage.session_count` 为 13
- **THEN** 用量区显示形如 `今日 13 会话`

#### Scenario: 窗口占用百分比
- **WHEN** `window_used_ratio` 为 0.86
- **THEN** 窗口区在进度条旁显示 `86%`

### Requirement: 待办使用真复选框并弱化完成项
待办项 SHALL 用复选框字形(☑ 已完成 / ☐ 未完成)替代 ASCII `[x]`/`[ ]`,已完成项的文本 SHALL 以删除线弱化。

#### Scenario: 完成与未完成区分
- **WHEN** 渲染一个 `done=True` 和一个 `done=False` 的待办
- **THEN** 前者显示 ☑ 且文本带删除线,后者显示 ☐ 且文本正常

### Requirement: 三色量化契约不变
丰富化后渲染产物 SHALL 仍只含黑/白/红三色、红色文字为纯 `(255,0,0)`、抗锯齿保持关闭,打包帧 SHALL 仍为 96000B 双 plane,`/frame` 协议不变。

#### Scenario: 量化与帧格式不变
- **WHEN** 渲染任意仪表盘帧并打包
- **THEN** 像素集合 ⊆ {(255,255,255),(0,0,0),(255,0,0)},且打包帧为 96000 字节

