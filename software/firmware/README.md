# InkPulse 固件（ESP32-S3 + UC8179 7.5" BWR 墨水屏）

- **阶段一**：屏驱动 bring-up（清屏 + 白/黑/红测试图案）—— 已通过。
- **阶段二**：联网瘦客户端 —— BLE 配网（SoftAP 兜底）→ 从 Hub 拉 800×480 三色帧 → 写屏；ETag/304 去重、离线保留上一帧、按 `X-Next-Refresh` 节拍循环；HTU21D 温湿度随请求上报。

## 环境

ESP-IDF v5.3.2（建议装在 `~/esp/esp-idf`，可用 `IDF_PATH` 覆盖）。每开新终端先激活：

```bash
source ~/miniforge3/etc/profile.d/conda.sh && conda activate espidf   # 若用 conda
. ~/esp/esp-idf/export.sh
```

> 国内网络：工具链走 `dl.espressif.cn` 镜像、源码走 gitee。

## 构建 / 烧录 / 看日志（跨平台脚本）

脚本会自动激活 ESP-IDF 环境（找不到 `idf.py` 时 source `$IDF_PATH/export.sh`）。

**Linux / macOS / WSL** — `./build.sh`：

```bash
cd software/firmware
./build.sh setup            # 首次: set-target esp32s3
./build.sh build            # 编译
PORT=/dev/ttyUSB0 ./build.sh fm   # 烧录 + 看日志(Ctrl+] 退出)
./build.sh verify           # bring-up 验证模式(温湿度+白黑红, 不联网)
./build.sh clean
```

**Windows PowerShell** — `.\build.ps1`：

```powershell
cd software\firmware
.\build.ps1 setup
.\build.ps1 build
$env:PORT='COM5'; .\build.ps1 fm
.\build.ps1 verify
```

> 也可直接用原生 `idf.py set-target esp32s3 && idf.py build && idf.py -p <PORT> flash monitor`。
> 脚本未识别的子命令会透传给 `idf.py`，例如 `./build.sh menuconfig`。

## 配置 Hub 地址

编辑 `main/net_config.h`，把 `HUB_FRAME_URL` 改成你电脑跑 `inkpulse_hub` 的局域网地址：

```c
#define HUB_FRAME_URL "http://192.168.1.23:8080/frame"   // 改成你的 IP
```

Hub 默认端口 8080（`INKPULSE_PORT` 可改）。

## 首次配网（BLE 为主，SoftAP 兜底）

无 WiFi 凭据时，设备**优先开 BLE 配网**；超时（`PROV_BLE_TIMEOUT_S`，默认 180s）仍未配网则**自动回退 SoftAP 网页配网**。

### 方式一：BLE（推荐）

1. 手机装 **ESP BLE Provisioning** App（Espressif 官方，App Store / Google Play）
2. 打开 App → *Provision New Device* → 扫码或选设备 **PROV_InkPulse**
3. 输入 Proof of Possession：**inkpulse**
4. 选家里 WiFi → 填密码 → 提交
5. App 显示配网成功后，设备**直接复用该连接拉帧上屏，无需重启**

> 配网参数在 `main/net_config.h`：`PROV_BLE_NAME` / `PROV_POP` / `PROV_BLE_TIMEOUT_S`。
> 收到凭据后由 `wifi_prov_mgr` 完成 WiFi 连接并回报 App，再进主循环——不在配网收尾处 `esp_restart`，否则 App 会误报 “Device disconnected”。
> 后续计划：用微信小程序替代官方 App 进一步提升体验（见 `../docs`）。

### 方式二：SoftAP（BLE 超时兜底）

BLE 超时未配网时设备自动开热点 **InkPulse-Setup**（密码 `inkpulse123`）：

1. 手机/电脑连该热点 → 浏览器打开 `http://192.168.4.1`
2. 填 WiFi 的 SSID / 密码 → 保存 → 设备重启
3. 重启后连 WiFi → 拉帧 → 屏上显示 Hub 渲染的仪表盘

凭据存在 NVS namespace `inkpulse`；`./build.sh erase-flash` 可清空重新配网。

## 引脚映射（原理图确认）

| 信号 | GPIO | | 信号 | GPIO |
|---|---|---|---|---|
| SCL(CLK) | 41 | | DC | 39 |
| SDA(MOSI) | 42 | | RES(RST) | 38 |
| CSB(CS) | 40 | | BUSY_N | 37 |

HTU21D（I2C）：SCL=GPIO2, SDA=GPIO1，地址 0x40。

## 帧/颜色契约（与 Hub `/frame` 对齐，勿改）

- body = 黑 plane(48000B) + 红 plane(48000B) = 96000B；行主序，每行 100 字节，MSB=最左像素。
- 黑 plane bit=1→黑；红 plane bit=1→红。
- 写屏映射（`epd_display_planes`，阶段一极性结论）：
  - 0x10(B/W) `1=白 0=黑` → 发 `~black`
  - 0x13(RED) `1=红` → 红 plane 直发（`EPD_RED_INVERT=0`；若实测红/白反相改 1）
- 响应头 `ETag`（带引号哈希）、`X-Next-Refresh`（秒）；请求带 `If-None-Match`，命中返回 304 不刷屏。

## 源文件

| 文件 | 职责 |
|---|---|
| `epd_uc8179.c/.h` | UC8179 驱动 + `epd_display_planes` 双 plane 写屏 |
| `htu21d.c/.h` | HTU21D 温湿度（I2C） |
| `ble_prov.c/.h` | BLE 配网（`wifi_provisioning` + NimBLE，security1 + PoP） |
| `wifi_prov.c/.h` | WiFi STA 连接 + NVS 凭据 + BLE→SoftAP 配网编排 + SoftAP 配网页 |
| `frame_client.c/.h` | HTTP 拉帧 + ETag/304 + 离线缓存 + 写屏 |
| `net_config.h` | Hub URL / 配网参数 |
| `main.c` | 联网主循环（`INKPULSE_VERIFY` 宏切回 bring-up 验证）|

详见 `../docs/superpowers/plans/2026-06-09-inkpulse-firmware-{driver,net}.md`。
