## ADDED Requirements

### Requirement: 侧栏分区导航
配置中心 SHALL 以侧栏分区导航组织内容，取代单页长卷轴。分区 MUST 至少包含：总览、屏幕、待办、习惯、日程、行情、天气、照片、设置。任一时刻 SHALL 仅展示当前选中分区的编辑面板，用户切换分区无需滚动寻找。

#### Scenario: 切换分区
- **WHEN** 用户在侧栏点击「待办」
- **THEN** 主区展示待办编辑面板，且其它分区内容不同时占用滚动空间

#### Scenario: 屏幕分区聚合布局相关功能
- **WHEN** 用户进入「屏幕」分区
- **THEN** 该分区内可见布局选择、布局编辑器(网格框选)与刷新间隔设置

### Requirement: 常驻预览/真机帧切换面板
配置中心 SHALL 提供一块跨分区常驻可见的面板，可在「真机当前」与「改完预览」两种视图间切换，并提供「刷新屏幕」操作。无论用户处于哪个分区，该面板 MUST 保持可见、无需滚动。

#### Scenario: 切到真机当前
- **WHEN** 用户点击「真机当前」
- **THEN** 面板显示设备最后拉走的那一帧，并标注设备拉帧距今的时长

#### Scenario: 切到改完预览
- **WHEN** 用户点击「改完预览」
- **THEN** 面板显示按当前配置渲染的预览图（下次设备拉帧将呈现的内容）

#### Scenario: 请求刷新屏幕
- **WHEN** 用户点击「刷新屏幕」
- **THEN** 网页请求 `/api/refresh`，设备在下一拉帧周期内上屏新内容

### Requirement: Vue 3 + Vite 前端经静态挂载提供
配置中心 SHALL 以 Vue 3 + Vite 工程实现，源码位于 `software/hub/web-ui/`，构建产物 `dist/` 经 FastAPI `StaticFiles` 挂载为网页入口。现有 `/api/*` 业务端点 MUST 保持不变并被该前端消费。

#### Scenario: 访问配置中心根路径
- **WHEN** 用户访问 hub 网页根路径
- **THEN** 返回 Vite 构建的单页应用，而非旧 `config.html`

#### Scenario: 业务端点契约不变
- **WHEN** 新前端调用 `/api/todos`、`/api/habits`、`/api/layouts` 等既有端点
- **THEN** 这些端点的请求/响应契约与改造前一致

### Requirement: 纸墨视觉风格与响应式
配置中心 SHALL 采用纸墨/e-ink 视觉风格（纸白底、墨黑字、红色点缀，对应三色屏），并 SHALL 响应式适配窄屏，使手机上也可操作各分区。

#### Scenario: 窄屏可用
- **WHEN** 用户在手机宽度下打开配置中心
- **THEN** 导航与编辑面板自适应窄屏布局，核心操作均可完成

### Requirement: 退役旧版网页
改造后 SHALL 移除旧的 `config.html`、`todos.html` 及对应的 `/config`、`/todos` HTML 路由。

#### Scenario: 旧路由不再提供旧页面
- **WHEN** 迁移完成后用户访问旧入口
- **THEN** 系统不再返回旧版单页 HTML（由新前端或重定向接管）
