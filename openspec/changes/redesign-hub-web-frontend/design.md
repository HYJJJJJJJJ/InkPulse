## Context

Hub 配置中心现状是单文件 `software/hub/inkpulse_hub/web/config.html`（459 行，vanilla JS + `innerHTML` 拼接 + 内联样式），10 张卡片叠成长卷轴。后端 `server.py` 已提供完整的 `/api/*` 业务端点，渲染由 `render.engine.render_frame(cfg, state, profile)` 完成——`/frame`(设备字节) 与 `/preview.png`(预览图) 同源同一帧、on-demand 渲染。设备是瘦客户端，仅周期性 `GET /frame`（ETag/304 去重，`X-Next-Refresh` 节拍），e-ink 实际上屏约 21s 延迟。

关键缺口：服务端从不记录"上次真正送给设备的是哪一帧"，所以网页无法呈现"设备此刻物理显示的内容"；网页刷新预览靠每个操作后 `setTimeout(refreshPreview, 300)`，既不跟手也不能多端同步。

## Goals / Non-Goals

**Goals:**
- 用 Vue 3 + Vite 重写配置中心，侧栏分区导航拆掉长卷轴。
- 网页常驻"真机当前帧"（设备最后拉走的帧）+ "改完预览"切换，所见即真机。
- SSE 实时同步替换所有客户端定时刷新；多端打开自动一致。
- 纸墨/e-ink 视觉风格，响应式。
- 后端改动是纯增量加法，不碰 `render_frame` 渲染核心，设备固件零改动。

**Non-Goals:**
- 不改设备端渲染逻辑或 `/frame` 的字节格式与 ETag/304 协议（设备无感）。
- 不把屏幕上的实时数值拆成 web 原生数据卡（探索时确认走 B·真机帧，不是 A·数据镜像）。
- 不引入用户认证 / 多用户（hub 仍是单用户局域网工具）。
- 不替换现有 `/api/*` 业务端点的契约。

## Decisions

### D1：Vue 3 + Vite，而非 React 或保留 vanilla
配置型仪表盘、单文件组件(SFC)、样板少、运行时体积小，最贴这个场景。React 同样可行但样板更多；保留 vanilla 无法根治"拼字符串 + 无反应式"的老问题（用户已明确选"上正经框架"）。源码置于 `software/hub/web-ui/`，与 Python 包并列。

### D2：dist 部署时 build，不提交产物
hub 由 systemd 托管，部署时增加 `npm ci && npm run build` 一步产出 `web-ui/dist/`，FastAPI 用 `StaticFiles` 挂载。保持 git 仓库干净、避免产物与源码漂移。代价是部署机需 Node/npm，并在 README/部署文档中记录。**回退**：若构建链暂不可用，可临时保留旧 `config.html` 作 fallback 路由直到 dist 就绪（迁移期）。

### D3："真机当前帧"靠服务端记录最后送出帧实现
在 `/frame` handler 中，当返回真实帧体（非 304）时，把该帧的 `png_bytes` + 时间戳 + 当前 env(t/h/rssi) 存入 hub 状态（`state.py` 或新 `device_view` 模块的内存字段，单设备、单槽即可）。新增：
- `GET /api/device/frame.png` → 返回该 PNG（无记录时回退为当前 `preview.png` 或占位）。
- `GET /api/device/status` → `{ pulled_at, age_s, rssi, temp, humidity, etag }`。
这样"真机当前帧"与"改完预览(`/preview.png`)"是两张可对比的图，差异窗口正好可视化 e-ink 延迟。**备选**：在网页侧用 ETag 推断——否决，服务端记录更直接、可附 env/时间戳。

### D4：SSE 单向流 + 独立 web 同步令牌，替代轮询
**关键修正**：现有 `_refresh["token"]`（`/api/refresh-token`）是**设备**轮询的"强制立即刷屏"信号，只应由用户点「刷新屏幕」(`/api/refresh`) 触发。若把"设备拉帧"并入同一令牌会造成死循环（设备拉帧→bump→设备再拉帧），把"每次数据改"并入则会让设备每改一条就强刷一次、伤 e-ink。因此采用**两个独立令牌**：
- **设备令牌** `refresh_token`（`/api/refresh-token`）：语义**完全不变**，仅 `/api/refresh` 触发，设备只看它。
- **web 同步令牌** `web_token`（仅 SSE 用）：配置改 / 数据改(todos/habits/events/market/photos/...) / 设备拉帧 / `/api/refresh` 都 `bump`，**只驱动网页**自动刷新预览与真机帧；设备永不感知。

新增 `GET /api/stream`（`text/event-stream`），推送 `{ token, device_pulled_at }`，网页订阅后据此自动刷新，**删除所有 `setTimeout(refreshPreview, 300)`**。SSE 而非 WebSocket：单向推送够用、FastAPI 下 `StreamingResponse` 实现简单、无额外依赖、`EventSource` 断线自动重连。SSE 生成器以 ~1s 轮询 `web_token` 变化（避免跨线程信号，sync 端点在线程池里 bump，不能安全 `set()` 事件循环里的 Event），变化即推送。**备选**：网页直接轮询 `/api/refresh-token`——否决，延迟高、多端不同步、且会与设备令牌语义打架。

### D5：信息架构——侧栏分区 + 常驻帧主角
导航分区拆掉长卷轴，按"低频配置 vs 高频日常"归类：
```
总览 | 屏幕(布局+编辑器+刷新间隔) | 待办 | 习惯 | 日程 | 行情 | 天气 | 照片 | 设置
```
顶部/侧栏常驻 `[真机当前] / [改完预览]` 切换 + `⟳刷屏` 按钮，跨分区始终可见。布局编辑器(网格框选)作为"屏幕"分区下的子面板保留现有交互。

### D6：纸墨视觉语言
承接 `docs/mockups/mockup-explorer.html` 既有配色审美，建立 CSS 设计 token（纸白底、墨黑字、点缀红——对应 BWR 三色屏）。响应式：桌面侧栏、窄屏抽屉/底部 Tab。

## Risks / Trade-offs

- [部署新增 Node 构建依赖] → 在部署文档/README 记录 `npm ci && npm run build`；迁移期保留旧 HTML fallback（D2）。
- [SSE 长连接占用 worker / 断线] → 限制单连接、心跳 keep-alive、客户端 `EventSource` 自动重连；uvicorn 异步天然支持。
- [最后送出帧的内存状态在 hub 重启后丢失] → 可接受：重启后首次设备拉帧即重建；`/api/device/frame.png` 无记录时回退到 `preview.png`。
- [前端大改面积、回归风险] → 现有 `/api/*` 契约不变，逐分区迁移并对照旧页验证；后端改动有 pytest 覆盖。
- [真机帧 vs 预览混淆用户] → UI 明确标注"设备 N 秒前拉帧"与"下次拉帧将变成"，把延迟讲清楚而非藏起来。

## Migration Plan

1. 后端先行：加 `/api/device/*` 与 `/api/stream`、`/frame` 记录最后送出帧；补 pytest。旧 `config.html` 暂留。
2. 搭 `web-ui/` Vue+Vite 骨架，逐分区迁移（先总览+屏幕+预览/真机帧，再 todos/habits/events/market/weather/photos/settings）。
3. 接 SSE，删除 `setTimeout(refreshPreview,300)`。
4. `StaticFiles` 挂载 `dist/`，切换默认入口；验证通过后移除 `config.html`、`todos.html` 及 `/config`、`/todos` 旧路由。
5. 更新部署文档（构建步骤）。**回退**：保留旧 HTML 路由分支即可快速切回。

## Open Questions

- 纸墨配色的具体 token 值是否直接复用 mockup-explorer 的调色板，还是另立一套？（实现时定）
- 窄屏导航用底部 Tab 还是抽屉？（实现时按手感定）
