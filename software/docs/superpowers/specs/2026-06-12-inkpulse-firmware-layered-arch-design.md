# InkPulse 固件分层解耦架构 — 设计文档

- 日期：2026-06-12
- 状态：已与用户确认方向，待评审后进入实现计划
- 范围：`software/firmware/` —— 把现有平铺的 `main/*.c` 重构为标准 ESP-IDF components 分层架构

---

## 1. 背景与目标

当前固件所有模块平铺在 `main/`（`epd_uc8179`/`htu21d`/`wifi_prov`/`ble_prov`/`frame_client`/`main`/`net_config`/`pins`），互相直接 `#include`、无接口隔离。典型耦合：

- `frame_client.c` 直接 `#include "epd_uc8179.h"` 并调用 `epd_display_planes(black, red)` —— 把「数据来源（HTTP/Hub）」和「显示（UC8179 双 plane）」绑死在一个函数里。
- `epd_uc8179.h` 一个头暴露了 HAL（`epd_send_cmd/data`）+ UC8179 驱动序列 + 双 plane 协议（`EPD_RED_INVERT`）+ bring-up 测试图案，四层混在一起。

**目标**：按标准嵌入式工程分层解耦，使以后
- **换屏幕**（不同墨水屏控制器/尺寸，甚至单色/多色/LCD）只新增 display 实现、不动上层；
- **换上层数据源**（Hub 服务端 / App / PC-BLE）只新增 channel 实现、不动上层。

## 2. 设计前提（已与用户确认）

| 边界 | 结论 |
|---|---|
| 显示抽象层次 | **通用「显示设备」接口**：能力查询（分辨率/色彩模型/帧格式）+ 显帧/刷新/睡眠。不假设双 plane 三色。 |
| 上层通道 | **双向 channel 抽象**：帧下行 + 状态上行（温湿度），预留控制下行。本期只实现 WiFi/HTTP，BLE **仅配网**。 |
| 交付范围 | **重构现有功能**搬进分层 + 立好接口并预留双向/多 transport；**不**实现 BLE 传帧/双向控制。 |
| 重构形态 | **完整 ESP-IDF components 化**：每层独立 component，`include/` 接口 + `src/` 实现 + `CMakeLists` 显式依赖。 |

**非目标（YAGNI）**：BLE 传帧、双向控制下行、状态上报除温湿度外的项、运行时多 display/channel 共存。这些只在接口上预留，不实现。

## 3. Component 分层与依赖方向

```
components/
├── ip_hal/           SPI/I2C/GPIO 封装 + 板级引脚(board_pins.h)
├── ip_display/       【接口】display.h(能力查询/显帧/刷新/清屏/睡眠)
│                     【实现】uc8179.c  → 依赖 ip_hal
├── ip_sensor/        【接口】sensor.h(读环境量, 带有效位)
│                     【实现】htu21d.c  → 依赖 ip_hal
├── ip_net/           WiFi STA 生命周期(连接/WPA3-SAE/循环重连/状态)
├── ip_provisioning/  【接口】provisioning.h
│                     【实现】ble_prov.c + softap_prov.c + creds_nvs.c → 依赖 ip_net
├── ip_channel/       【接口】channel.h(取帧/上报env/预留控制下行)
│                     【实现】http_hub.c → 依赖 ip_net
└── ip_config/        编译期常量(Hub URL、配网参数、刷新节拍默认)
main/                 app: 只组装接口 + 主循环编排, 变薄
```

**依赖方向严格单向，上层只依赖接口头**：

```
main(app) ──→ display.h / channel.h / sensor.h / provisioning.h / ip_net / ip_config
uc8179.c ──→ ip_hal          htu21d.c ──→ ip_hal
http_hub.c ──→ ip_net        ble/softap_prov ──→ ip_net + creds_nvs
```

app **从不** `#include` 任何具体实现头（`uc8179.h`/`htu21d.h`/`http_hub.h`）。

## 4. 接口定义（ops 结构体 / 函数指针表）

C 里以「能力 struct + ops 函数指针表 + 工厂函数」实现面向接口编程。换实现 = 让 app 取另一个工厂 + 改 CMake，零改上层逻辑。

### 4.1 display（`ip_display/include/ip_display/display.h`）

```c
typedef enum { DISP_BWR, DISP_BW, DISP_ACEP7, DISP_RGB } disp_color_model_t;

typedef struct {
    uint16_t width, height;
    disp_color_model_t color_model;
    const char *frame_format;   // 如 "bwr-dualplane"; Hub 据此渲染
    size_t frame_bytes;          // 一帧字节数(BWR 800x480 = 96000)
} display_caps_t;

typedef struct {
    esp_err_t (*init)(void);
    void      (*get_caps)(display_caps_t *out);
    esp_err_t (*show)(const uint8_t *frame, size_t len);  // 写一帧(格式由 caps 定义)
    void      (*refresh)(void);
    void      (*clear)(void);
    void      (*sleep)(void);
} display_if_t;

const display_if_t *uc8179_driver(void);   // 工厂
```

> UC8179 实现内部保留现有极性结论（`0x10` 取反、`0x13` 直发）与 bring-up 测试图案（移到实现内部的 `uc8179_selftest.c`，不进公开接口）。

### 4.2 sensor（`ip_sensor/include/ip_sensor/sensor.h`）

```c
typedef struct {
    float temp_c;     bool temp_valid;
    float humidity;   bool humidity_valid;   // 传感器损坏读 0 时置 false
} sensor_env_t;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*read)(sensor_env_t *out);
} sensor_if_t;

const sensor_if_t *htu21d_sensor(void);
```

> 有效位取代现状的「传 -100 哨兵」：湿度通道坏时 `humidity_valid=false`，上层/Hub 据此隐藏，语义清晰。

### 4.3 channel（`ip_channel/include/ip_channel/channel.h`）

```c
typedef struct { bool changed; int next_refresh_s; } channel_result_t;

typedef struct {
    esp_err_t (*init)(const display_caps_t *caps);   // 知道要拉什么帧格式
    // 拉一帧到 buf(buf 大小= caps.frame_bytes), 顺带上报 env; changed=false 表示未变(304)
    esp_err_t (*fetch)(uint8_t *buf, size_t buf_len,
                       const sensor_env_t *env, channel_result_t *out);
    // 预留(本期不实现): esp_err_t (*poll_control)(channel_control_t *out);
} channel_if_t;

const channel_if_t *http_hub_channel(void);
```

### 4.4 net / provisioning

```c
// ip_net: WiFi STA(含 WPA3-SAE + 带间隔循环重连, 沿用现有修复)
esp_err_t ip_net_connect(const char *ssid, const char *pass);
bool      ip_net_is_up(void);

// ip_provisioning: 拿到凭据存 NVS(creds_nvs); 成功后(BLE)复用已建连接
typedef struct { bool (*run)(int timeout_s); } provisioning_if_t;
const provisioning_if_t *ble_provisioning(void);
const provisioning_if_t *softap_provisioning(void);
bool creds_load(char *ssid, size_t sl, char *pass, size_t pl);
```

## 5. 帧格式与能力协商

- 设备启动时由 `display->get_caps()` 得到 `display_caps_t`，`channel->init(caps)` 据此知道要拉哪种帧；HTTP 实现把 `frame_format`/分辨率作为请求参数或头带给 Hub，Hub 渲染对应格式。
- 本期 UC8179 = `bwr-dualplane`/800×480/96000B，与现有 `/frame` 协议一致（行为不变）。
- 换屏（如单色/ACeP7）只改 `get_caps` 返回值 + 对应 `show()` 解码，Hub 端按上报能力渲染——设备上层与 channel 接口不变。

## 6. 数据流（app 主循环编排）

```c
const display_if_t *disp   = uc8179_driver();
const sensor_if_t  *sensor = htu21d_sensor();
const channel_if_t *chan   = http_hub_channel();

disp->init();  display_caps_t caps; disp->get_caps(&caps);
sensor->init();

if (!creds_load(...)) {                       // 无凭据 → 配网
    if (!ble_provisioning()->run(PROV_BLE_TIMEOUT_S))
        softap_provisioning()->run(...);       // 兜底; 配完重启或复用连接
}
ip_net_connect(ssid, pass);                    // WPA3-SAE + 循环重连
chan->init(&caps);
disp->clear();                                 // 开机消残影

static uint8_t framebuf[/*caps.frame_bytes 上限*/];
while (1) {
    sensor_env_t env; sensor->read(&env);
    channel_result_t r;
    if (chan->fetch(framebuf, sizeof framebuf, &env, &r) == ESP_OK && r.changed) {
        disp->show(framebuf, caps.frame_bytes);
        disp->refresh();
    }
    delay_s(r.next_refresh_s);
}
```

帧 buffer 由 app 持有（`.bss`），channel 填、display 显示；三方通过接口协作，互不知道对方实现。

## 7. 现有代码 → 新结构映射

| 现有 | 去向 |
|---|---|
| `epd_uc8179.c` HAL 部分(SPI/GPIO/send_cmd/data/wait_busy) | `ip_hal/` |
| `epd_uc8179.c` UC8179 序列 + `epd_display_planes` | `ip_display/src/uc8179.c`(实现 `display_if_t`) |
| `epd_uc8179.c` 测试图案(`show_split/checker/solid`) | `ip_display/src/uc8179_selftest.c`(实现内部) |
| `htu21d.c` | `ip_sensor/src/htu21d.c`(实现 `sensor_if_t`，加有效位) |
| `wifi_prov.c` STA 连接/重连部分 | `ip_net/` |
| `wifi_prov.c` 配网编排 + SoftAP 页 + NVS 凭据 | `ip_provisioning/`(softap_prov + creds_nvs) |
| `ble_prov.c` | `ip_provisioning/src/ble_prov.c`(实现 `provisioning_if_t`) |
| `frame_client.c` | `ip_channel/src/http_hub.c`(实现 `channel_if_t`，去掉对 display 的直接依赖) |
| `net_config.h` | `ip_config/` |
| `pins.h` | `ip_hal/include/ip_hal/board_pins.h` |
| `main.c` | `main/`(只做接口组装 + 主循环 + 保留 `INKPULSE_VERIFY` 走 display selftest) |

## 8. 错误处理 / 容错（沿用现有，不退化）

- 离线：`channel->fetch` 失败保留上一帧、按退避节拍重试（现有行为）。
- WiFi：`ip_net_connect` 内含 WPA3-SAE + 带 2s 间隔循环重连（沿用本周期修复）。
- 配网：BLE 超时 → SoftAP 兜底（`esp_wifi_stop` 后切 AP，沿用修复）。
- 接口调用返回 `esp_err_t`，app 对失败做日志 + 安全降级，不 crash。

## 9. 测试策略

- **接口契约**：每个 ops 工厂返回非空、`get_caps` 字段合理，可在真机 boot 时断言。
- **display selftest**：`INKPULSE_VERIFY` 走 `uc8179_selftest`（白/黑/红/分屏/棋盘），真机肉眼验证（沿用，已修宏生效问题）。
- **端到端**：配网 → 连 WPA3 → 拉帧 → 上屏，真机回归（现有 harness）。
- 纯逻辑（如 sensor 有效位判定、帧字节数校验）可抽到 host 可测函数。

## 10. 落地分期（详细步骤留给实现计划）

1. **骨架**：建 components 目录 + 各 `CMakeLists` + 接口头（先空实现/桩），全工程能编译。
2. **下沉实现**：按映射表逐 component 迁移现有代码到实现里，对齐接口；每迁一层编译通过。
3. **app 重写**：`main.c` 改为纯接口组装 + 主循环；删旧平铺文件。
4. **真机回归**：selftest + 端到端配网拉帧上屏，行为与重构前一致。

## 11. 验收标准

- 目录为 components 分层，`main` 不再 `#include` 任何具体实现头。
- 「换屏」可行性自检：能描述新增一个 display 实现 component 需要改哪些（答案应为：新 component + app 一行 + CMake，零改上层）。
- 真机端到端行为与重构前一致（配网/拉帧/上屏/温度显示/重连）。
