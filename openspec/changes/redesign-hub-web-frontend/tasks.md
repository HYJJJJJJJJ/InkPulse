## 1. 后端：真机当前帧记录与端点 (device-frame-mirror)

- [x] 1.1 在 hub 状态（`state.py` 或新 `device_view` 模块）增加"最后送出帧"内存槽：png 字节、时间戳、env(t/h/rssi)、etag
- [x] 1.2 修改 `/frame` handler：返回 200 真实帧体时写入该槽；304 命中时不覆盖
- [x] 1.3 新增 `GET /api/device/frame.png`（无记录时回退 preview/占位，不报错）
- [x] 1.4 新增 `GET /api/device/status`（`pulled_at`/`age_s`/`rssi`/`temp`/`humidity`）
- [x] 1.5 pytest 覆盖：拉帧后被记录、304 不覆盖、无记录回退、status 字段

## 2. 后端：统一信号源与 SSE (hub-realtime-sync)

- [x] 2.1 抽出 `bump_web()` 单一入口；写请求经 middleware 统一 bump，`/frame` 拉帧经 record_device_frame bump（设备 refresh_token 语义不变，避免死循环）
- [x] 2.2 新增 `GET /api/stream`（`text/event-stream`），token 变化时推送 `{token, device_pulled_at}`，含心跳 keep-alive
- [x] 2.3 pytest 覆盖：数据变更/拉帧触发 bump、设备令牌不受影响、`sse_stream` 初值+变更各发一条事件

## 3. 前端工程脚手架 (hub-web-ui)

- [x] 3.1 在 `software/hub/web-ui/` 初始化 Vue 3 + Vite 工程（`package.json`、构建脚本）
- [x] 3.2 建立纸墨视觉设计 token（纸白/墨黑/红点缀）与全局样式，承接 mockup-explorer 配色
- [x] 3.3 搭好 API 封装层（`/api/*` 调用）与 SSE 客户端（`EventSource` 自动重连）
- [x] 3.4 实现侧栏分区导航骨架（总览/屏幕/待办/习惯/日程/行情/天气/照片/设置）+ 响应式窄屏导航

## 4. 前端：常驻预览/真机帧面板

- [x] 4.1 实现跨分区常驻面板：`[真机当前]`/`[改完预览]` 切换 + `⟳刷屏`
- [x] 4.2 真机当前视图接 `/api/device/frame.png` + `/api/device/status`，标注"设备 N 秒前拉帧 · RSSI · 温度"
- [x] 4.3 改完预览视图接 `/preview.png`；两视图均由 SSE 事件自动刷新，去除任何固定 setTimeout 刷新

## 5. 前端：各分区面板迁移

- [x] 5.1 屏幕分区：布局选择 + 布局编辑器(网格框选保留交互) + 刷新间隔
- [x] 5.2 待办、习惯分区
- [x] 5.3 日程、行情、天气分区
- [x] 5.4 照片分区（上传/删除/钉选）
- [x] 5.5 设置分区（预算/token 上限/刷新间隔等）
- [x] 5.6 总览分区（汇总入口 + 真机帧主视图）

## 6. 集成、退役与文档

- [x] 6.1 FastAPI 用 `StaticFiles` 挂载 `web-ui/dist/` 为网页入口
- [x] 6.2 移除 `web/config.html`、`web/todos.html` 及 `/config`、`/todos` 路由（旧页测试一并删除）
- [x] 6.3 更新 README/部署文档：`run.sh` 内置幂等 build、hub/主 README 构建步骤与端点表、systemd 注意事项
- [x] 6.4 全量回归：pytest 292 通过、端到端冒烟(SPA 入口/旧路由404/设备帧端点/API)验证
