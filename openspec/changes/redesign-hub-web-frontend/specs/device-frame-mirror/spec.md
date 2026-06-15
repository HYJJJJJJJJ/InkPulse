## ADDED Requirements

### Requirement: 记录最后送给设备的帧
当设备通过 `GET /frame` 取得真实帧体（非 304）时，hub SHALL 记录该帧对应的预览 PNG、记录时间戳以及当时的环境数据（温度/湿度/RSSI）。该记录 MUST 反映"设备此刻物理显示的内容"。304 命中（设备复用缓存）SHALL 不覆盖已记录的帧。

#### Scenario: 设备拉取新帧后被记录
- **WHEN** 设备请求 `/frame` 且 hub 返回 200 帧体
- **THEN** hub 更新"最后送出帧"的 PNG、时间戳与 env 快照

#### Scenario: 304 不覆盖记录
- **WHEN** 设备请求 `/frame` 且命中 ETag 返回 304
- **THEN** hub 保留先前记录的最后送出帧不变

### Requirement: 真机当前帧端点
hub SHALL 提供 `GET /api/device/frame.png`，返回最后送给设备的帧的 PNG。当尚无记录时 SHALL 回退返回当前渲染预览或占位图，而非报错。

#### Scenario: 已有记录
- **WHEN** 设备至少拉过一次帧后，网页请求 `/api/device/frame.png`
- **THEN** 返回该帧的 PNG 图像

#### Scenario: 尚无记录回退
- **WHEN** hub 启动后设备尚未拉过帧，网页请求 `/api/device/frame.png`
- **THEN** 返回当前预览或占位图，HTTP 状态为成功

### Requirement: 设备状态端点
hub SHALL 提供 `GET /api/device/status`，返回最后拉帧时间、距今时长（秒）、以及最近上报的 RSSI、温度、湿度等设备状态。

#### Scenario: 查询设备状态
- **WHEN** 网页请求 `/api/device/status`
- **THEN** 返回包含 `pulled_at`、`age_s` 及可得的 `rssi`/`temp`/`humidity` 的 JSON
