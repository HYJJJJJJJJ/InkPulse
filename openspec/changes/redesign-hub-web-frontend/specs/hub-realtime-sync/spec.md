## ADDED Requirements

### Requirement: 独立的 web 同步令牌
hub SHALL 维护一个**独立于设备刷新令牌**的 web 同步令牌(`web_token`)，在以下任一事件发生时严格递增(bump)：配置变更、业务数据变更（待办/习惯/日程/行情/天气/照片等）、以及设备拉取新帧。该令牌 MUST NOT 影响设备侧 `/api/refresh-token` 的语义——设备刷新令牌仅由 `/api/refresh` 触发，设备拉帧或数据变更 MUST NOT 改变设备刷新令牌（避免设备死循环与无谓强刷）。

#### Scenario: 数据变更触发 web 令牌递增
- **WHEN** 用户通过任一 `/api/*` 写端点新增/修改/删除数据
- **THEN** web 同步令牌递增

#### Scenario: 设备拉帧触发 web 令牌递增
- **WHEN** 设备通过 `/frame` 取得新帧体
- **THEN** web 同步令牌递增

#### Scenario: 设备刷新令牌语义不变
- **WHEN** 仅发生数据变更或设备拉帧、而用户未点「刷新屏幕」
- **THEN** `/api/refresh-token` 返回的设备令牌保持不变

### Requirement: SSE 实时推送流
hub SHALL 提供 `GET /api/stream`（`text/event-stream`），在 token 变化时向已连接的网页客户端推送事件，事件载荷 MUST 至少包含当前 `token` 与设备最近拉帧时间。客户端断线后 SHALL 能自动重连。

#### Scenario: 订阅后收到更新
- **WHEN** 网页建立 `/api/stream` 连接，随后发生一次数据变更
- **THEN** 该连接收到一条携带新 `token` 的事件

#### Scenario: 多端同步
- **WHEN** 两个网页同时订阅 `/api/stream`，其中一个修改了数据
- **THEN** 两个网页都收到带新 `token` 的事件

### Requirement: 网页自动刷新替代定时轮询
新前端 SHALL 依据 `/api/stream` 推送的事件自动刷新预览图与真机当前帧，且 MUST NOT 依赖每次操作后固定延时的手动刷新（取代旧的 `setTimeout(refreshPreview, 300)` 方式）。

#### Scenario: 改动后预览自动更新
- **WHEN** 用户在某分区完成一次写操作
- **THEN** 预览/真机帧因收到 SSE 事件而自动刷新，无需用户手动点刷新或固定等待

#### Scenario: 他端改动本端也更新
- **WHEN** 另一端或设备触发了 token 变化
- **THEN** 本端网页据 SSE 事件自动刷新对应视图
