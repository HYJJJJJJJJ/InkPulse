## Why

Hub 的配置中心目前是一个 459 行的 `config.html` 单文件：10 张卡片叠成一根长卷轴、用 vanilla JS 拼 `innerHTML`、内联样式满天飞。三个痛点叠加——(1) 全堆一页要命的长滚，配置类与日常类内容互相干扰；(2) 实时预览埋在第 3 张卡、改完要靠 `setTimeout(refreshPreview, 300)` 手动刷，预览不跟手；(3) 视觉朴素。更关键的是：网页只能看到一张"按当前 state 渲染的 PNG"，**看不到设备此刻物理显示的那一帧**——而这正是用户想要的"所见即真机"。

## What Changes

- **BREAKING**：用 Vue 3 + Vite 重写整个配置中心，退役 `config.html` 与遗留的 `todos.html`。前端产物 `dist/` 经 FastAPI `StaticFiles` 挂载到 `/`。
- 用**侧栏分区导航**拆掉长卷轴：总览 / 屏幕(布局+编辑器+刷新) / 待办 / 习惯 / 日程 / 行情 / 天气 / 照片 / 设置，各分区各司其职。
- 引入**"真机当前帧"常驻主角**：网页顶部/侧栏常驻一块，显示设备最后真正拉走的那一帧（= 此刻玻璃上的内容），附"设备 N 秒前拉帧 · RSSI · 温度"。可在 `[真机当前]` 与 `[改完预览]` 间切换，把 e-ink 刷新延迟可视化。
- 后端**增量加法**（不动渲染核心）：`/frame` 命中时记录"最后送给设备的帧"（png + 时间戳 + rssi/temp）；新增 `GET /api/device/frame.png` 与 `GET /api/device/status`。
- 引入 **SSE 实时流** `GET /api/stream`：统一 `refresh-token`，配置改 / 数据改 / 设备拉帧都 bump，网页订阅后自动更新预览与真机帧——**删除所有 `setTimeout(refreshPreview, 300)`**，多端打开自动同步。
- 现代化**纸墨 / e-ink 视觉风格**，承接 `docs/mockups/mockup-explorer.html` 已有的配色审美；响应式，手机上也可用。
- 现有 `/api/*` 业务端点（todos/habits/weather/events/market/config/layouts/photos/refresh）**保持不变**，仅被新前端消费。

## Capabilities

### New Capabilities
- `hub-web-ui`: Vue 3 + Vite 重写的 Hub 配置中心——侧栏分区导航、纸墨视觉、响应式，常驻"真机当前帧 / 改完预览"切换面板；Vite `dist/` 经 FastAPI 静态挂载、部署时 build。
- `device-frame-mirror`: 后端记录"最后送给设备的帧"（png + 时间戳 + rssi/temp），并通过 `GET /api/device/frame.png`、`GET /api/device/status` 暴露给网页，实现"真机当前帧"镜像。
- `hub-realtime-sync`: SSE 流 `GET /api/stream` 统一 `refresh-token` 信号（配置改/数据改/设备拉帧均 bump），网页订阅后自动刷新预览与真机帧，取代客户端定时轮询。

### Modified Capabilities
<!-- 现有 dashboard-rendering(设备端渲染)的需求不变；本次只新增 web 与后端配套端点。 -->

## Impact

- **新增前端工程**：`software/hub/web-ui/`（Vue 3 + Vite 源码 + `package.json`），build 产物 `dist/`。
- **`software/hub/inkpulse_hub/server.py`**：新增 `/api/device/frame.png`、`/api/device/status`、`/api/stream`(SSE)，`/frame` handler 增加"记录最后送出帧"；用 `StaticFiles` 挂载 `dist/`；移除 `/config`、`/todos` 旧 HTML 路由与 `web/config.html`、`web/todos.html`。
- **`software/hub/inkpulse_hub/state.py`**（或新模块）：保存最后送出帧的字节/PNG/时间戳/env。
- **部署**：systemd 托管的 hub 启动前需 `npm ci && vite build`（或文档化的构建步骤）；新增 Node/npm 构建依赖。
- **测试**：新增 `/api/device/*`、`/api/stream` 的 pytest；前端可加轻量构建校验。
- 设备固件**无需改动**（仍只拉 `/frame`）。
