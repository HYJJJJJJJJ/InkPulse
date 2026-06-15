# InkPulse

> 一块放在桌面的 7.5" 三色墨水屏，实时显示 **Claude Code 的工作状态、token 用量、待办事项、照片**，外加时钟与温湿度。
> 渲染全部在电脑端完成，设备只负责"把电脑渲染好的整屏位图拉下来贴上去"。

InkPulse 是一个**软硬件一体**的开源项目，包含：自制 PCB（ESP32-S3 + UC8179 墨水屏驱动）、3D 打印楔形外壳、设备固件、以及电脑端的渲染服务 Hub。

---

## 目录

- [它是什么](#它是什么)
- [系统架构](#系统架构)
- [仓库结构](#仓库结构)
- [技术规格速查](#技术规格速查)
- [快速开始（端到端）](#快速开始端到端)
- [当前状态与路线图](#当前状态与路线图)
- [文档索引](#文档索引)

---

## 它是什么

桌面信息屏，单屏组合显示（不翻页，避免三色屏每次全刷闪烁）：

- **Claude 状态**（主角）：某台开发机上 Claude Code 的实时状态 —— 空闲 / 工作中 / 等你输入 / 刚完成 / 出错，附项目名。需要注意的状态用**红色**强调。
- **用量**：订阅制下今日 token（输入/输出/缓存）、估算花费、5 小时计划窗口剩余比例。
- **待办**：工作/生活待办，提供局域网网页（手机也能加）。
- **照片**：可选的整屏照片布局（Floyd–Steinberg 三色抖动）。
- **顶栏白送**：时钟/日期 + 板载温湿度。

**设计取舍**（详见 [显示系统设计文档](software/docs/superpowers/specs/2026-06-09-inkpulse-display-system-design.md)）：局域网内使用、常插电无电池、订阅制用量靠解析本机日志、布局用 YAML 配置而非拖拽编辑器。

---

## 系统架构

**瘦客户端 + 本机 Hub 渲染**：复杂的排版、三色量化、抖动都在电脑上做好，设备只做整屏 blit。改布局只改配置、不用重新烧固件。

```
开发机 (跑 Claude Code)                          墨水屏设备 (ESP32-S3)
┌─────────────────────────────────────┐
│  Claude Code ──hooks──┐              │
│                       ▼              │
│  ┌────────── InkPulse Hub ─────────┐ │   WiFi / HTTP      ┌──────────────────┐
│  │ 采集器 → 状态模型 → 渲染引擎     │ │ ─────────────────▶ │ 固件:             │
│  │   ├ 用量(解析 ~/.claude 日志)    │ │  GET /frame        │  BLE/SoftAP 配网  │
│  │   ├ 待办(JSON + 网页)           │ │  → 96000B 双plane  │  拉帧→变了才刷    │
│  │   ├ 照片(目录轮换)              │ │  + ETag/304        │  →按节拍轻睡循环  │
│  │   └ Claude状态(hook POST 推送)  │ │  + X-Next-Refresh  │  离线缓存上一帧   │
│  └─────────────────────────────────┘ │                    └──────────────────┘
│   ▲ config.yaml  ▲ photos/  ▲ todos   │                       ▲ HTU21D 温湿度
└─────────────────────────────────────┘                       随取帧请求上报
```

**关键协议**（设备 ⇄ Hub）：

| 项 | 约定 |
|---|---|
| 取帧 | `GET /frame`，请求带 `If-None-Match: <上次ETag>` |
| 帧格式 | 黑 plane(48000B) + 红 plane(48000B) = **96000B**；行主序，每行 100 字节，MSB=最左像素；bit=1 表示该色 |
| 去重 | `ETag`=帧内容哈希；未变返回 `304`，**设备不刷屏**（三色屏体验命门：避免无谓闪烁） |
| 节奏 | 响应头 `X-Next-Refresh`（秒）由 Hub 决定下次拉取间隔 |
| 上报 | 设备取帧时把温湿度作为 query 带上（`/frame?t=22&h=55`），Hub 渲染进顶栏 |

---

## 仓库结构

```
InkPulse/
├── hardware/        Altium Designer PCB 工程（原理图 + PCB + 3D STEP）
│   └── library/     元件库（git submodule）
├── cad/             build123d 参数化外壳（楔形三件套 + 抽拉盖板）+ 校验脚本
│   └── output/      生成的 STL/STEP 产物
├── software/
│   ├── firmware/    ESP32-S3 固件（ESP-IDF）：UC8179 驱动 + 配网 + 拉帧主循环
│   ├── hub/         电脑端 Hub（Python/FastAPI）：采集 + 渲染 + HTTP 服务
│   └── docs/        软件侧设计文档（specs）与实现计划（plans）
└── docs/            硬件/外壳设计文档
```

各子系统都有自己的 README：[hardware](hardware/README.md) · [cad](cad/README.md) · [firmware](software/firmware/README.md) · [hub](software/hub/README.md)。

---

## 技术规格速查

| 模块 | 规格 |
|---|---|
| 主控 | ESP32-S3 模组（YD-ESP32-S3），WiFi + BLE + PSRAM |
| 屏幕 | 英瑞达 E075A42，7.5"，**800×480**，黑/白/红三色 (BWR)，控制器 **UC8179**，4 线 SPI |
| 刷新 | 全刷约 15~30s，**无局刷、无灰阶**；红色仅用于强调/告警 |
| 帧缓冲 | 双 plane（黑+红）= 96000 B ≈ 94 KB |
| 传感器 | 板载 HTU21D 温湿度（I2C，地址 0x40） |
| 供电 | USB-C 5V → LDO 3.3V，无电池，常插电 |
| 烧录 | CH343G USB 串口 + DTR/RTS 自动下载 |
| 外壳 | 3D 打印楔形支架，屏面仰角 60°，前框/后盖/底座三件 + 抽拉盖板 |

**引脚映射**（以 PCB 网表为准）：

| 信号 | GPIO | | 信号 | GPIO |
|---|---|---|---|---|
| SCL(CLK) | 41 | | DC | 39 |
| SDA(MOSI) | 42 | | RES(RST) | 38 |
| CSB(CS) | 40 | | BUSY_N | 37 |

HTU21D：SCL=GPIO2, SDA=GPIO1。

---

## 快速开始（端到端）

从零到屏上显示，需要两步：起 Hub（电脑）→ 烧固件并配网（设备）。

### 1. 起 Hub（电脑端）

```bash
cd software/hub
pip install -e ".[dev]"
( cd web-ui && npm ci && npm run build )           # 构建配置中心前端（或直接用 ./run.sh, 已内置）
cp config.example.yaml ~/inkpulse-config.yaml      # 按需改 photos/todos 路径
INKPULSE_CONFIG=~/inkpulse-config.yaml python -m inkpulse_hub
# 监听 0.0.0.0:8080（INKPULSE_PORT 可改）
```

浏览器打开 `http://<本机IP>:8080/` 即可进**配置中心**——分区管理待办/日程/行情/天气/照片、可视化布局编辑，常驻「真机当前帧 / 改完预览」面板，改动经 SSE 即时反映。无设备也能用 `/preview.png` 看渲染效果。
详见 [Hub README](software/hub/README.md)。

### 2. 烧固件 + 配网（设备端）

```bash
cd software/firmware
# 先把 main/net_config.h 的 HUB_FRAME_URL 改成你电脑的局域网地址
./build.sh setup                       # 首次：set-target esp32s3
PORT=/dev/ttyUSB0 ./build.sh fm        # 编译 + 烧录 + 看日志
```

设备首次上电无凭据 → 开 **BLE 配网**（用 Espressif 官方 *ESP BLE Provisioning* App，设备名 `PROV_InkPulse`，PoP `inkpulse`）；BLE 超时 180s 自动回退 SoftAP 网页配网。配好网后设备自动拉帧上屏。详见 [固件 README](software/firmware/README.md)。

### 3.（可选）接 Claude Code 状态

把 `software/hub/hooks/claude_status.sh` 挂到 `~/.claude/settings.json` 的 hooks，在 SessionStart→working、Stop→done、Notification→waiting_for_input 等时机上报状态。

---

## 当前状态与路线图

**已端到端跑通并真机验证**：BLE 配网 → 连 WiFi → 拉 Hub 帧 → 三色墨水屏显示仪表盘（时钟/Claude 状态/用量/温度），中文清晰、无残影。

| 子系统 | 状态 |
|---|---|
| 固件：UC8179 驱动 + 拉帧主循环 | ✅ 跑通 |
| 固件：BLE 配网（+ SoftAP 兜底） | ✅ 跑通（SoftAP 兜底路径代码就绪，未单独实测） |
| Hub：采集 + 渲染 + HTTP 服务 | ✅ 跑通，33 项测试通过 |
| 外壳 CAD：四件套 + 装配/干涉校验 | ✅ 模型与校验脚本就绪 |
| 硬件 PCB | ✅ 已制板、已焊接联调 |

**已知限制**：
- 板载这颗 HTU21D **湿度通道硬件损坏**（温度正常，湿度恒返回 0）；Hub 已在顶栏隐藏无效湿度，换好传感器后自动恢复显示。

**后续可做**：
- 微信小程序替代官方 App 配网（提升体验）
- 待办/照片/配置化的进一步打磨
- SoftAP 兜底路径的实测验证

---

## 文档索引

**设计文档（specs）**
- [显示系统设计](software/docs/superpowers/specs/2026-06-09-inkpulse-display-system-design.md) —— 软件总体架构、协议、布局、刷新策略
- [BLE 配网设计](software/docs/superpowers/specs/2026-06-11-inkpulse-ble-provisioning-design.md) —— BLE 主 + SoftAP 兜底
- [外壳设计](docs/superpowers/specs/2026-06-03-inkpulse-enclosure-design.md) —— 楔形外壳尺寸、PCB 机械接口约定

**实现计划（plans）**
- [固件：屏驱动](software/docs/superpowers/plans/2026-06-09-inkpulse-firmware-driver.md)
- [固件：联网](software/docs/superpowers/plans/2026-06-09-inkpulse-firmware-net.md)
- [固件：BLE 配网](software/docs/superpowers/plans/2026-06-11-inkpulse-firmware-ble-prov.md)
- [Hub](software/docs/superpowers/plans/2026-06-09-inkpulse-hub.md)

**子系统 README**：[hardware](hardware/README.md) · [cad](cad/README.md) · [firmware](software/firmware/README.md) · [hub](software/hub/README.md)

---

## 许可

见 [LICENSE](LICENSE)。
