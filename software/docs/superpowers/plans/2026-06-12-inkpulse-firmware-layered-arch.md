# InkPulse 固件分层解耦重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把平铺在 `main/` 的固件重构为 ESP-IDF components 分层架构(ip_hal/ip_display/ip_sensor/ip_net/ip_provisioning/ip_channel/ip_config + 薄 main),接口用 ops 结构体,换屏/换 transport 只改实现不动上层,且现有功能行为不变。

**Architecture:** 每层独立 component,`include/<comp>/` 暴露接口、`src/` 藏实现、`CMakeLists.txt` 用 `REQUIRES` 显式声明依赖。app 只持有接口指针(`const display_if_t *` 等),从不 include 具体实现头。逐层迁移,每层迁完即 `idf.py build` 验证,全部迁完做真机端到端回归。

**Tech Stack:** ESP-IDF v5.3.2、ESP32-S3、CMake component 机制、C(ops 函数指针表面向接口)。

**设计依据:** `software/docs/superpowers/specs/2026-06-12-inkpulse-firmware-layered-arch-design.md`(接口签名见 §4,代码映射见 §7)。

**重要约定:**
- 所有命令在 `software/firmware/` 下执行;构建用 `./build.sh build`(已封装 idf.py + 环境)。
- 重构期间 `main/` 旧文件**保留到 Task 8 才删**,新 component 与旧文件并存时,通过逐步切换 `main/CMakeLists.txt` 的 SRCS 与 main.c 的 include 来过渡。为避免符号冲突,**每个 component 迁移时同步从 `main/CMakeLists.txt` 的 SRCS 移除对应旧 .c**(见各 Task 的 CMake 步骤)。
- commit 署名沿用仓库配置(`zengqx <zengqx1996@gmail.com>`),**禁止** `Co-Authored-By`。

---

## File Structure

```
software/firmware/
├── CMakeLists.txt                  (顶层, 基本不动; EXTRA_COMPONENT_DIRS 默认含 components/)
├── components/
│   ├── ip_config/
│   │   ├── CMakeLists.txt
│   │   └── include/ip_config/net_config.h        ← 原 main/net_config.h
│   ├── ip_hal/
│   │   ├── CMakeLists.txt
│   │   ├── include/ip_hal/{board_pins.h, spi_bus.h, i2c_bus.h}
│   │   └── src/{spi_bus.c, i2c_bus.c}
│   ├── ip_display/
│   │   ├── CMakeLists.txt
│   │   ├── include/ip_display/display.h          ← ops 接口
│   │   └── src/{uc8179.c, uc8179_selftest.c}
│   ├── ip_sensor/
│   │   ├── CMakeLists.txt
│   │   ├── include/ip_sensor/sensor.h
│   │   └── src/htu21d.c
│   ├── ip_net/
│   │   ├── CMakeLists.txt
│   │   ├── include/ip_net/net.h
│   │   └── src/net_sta.c
│   ├── ip_provisioning/
│   │   ├── CMakeLists.txt
│   │   ├── include/ip_provisioning/provisioning.h
│   │   └── src/{ble_prov.c, softap_prov.c, creds_nvs.c}
│   └── ip_channel/
│       ├── CMakeLists.txt
│       ├── include/ip_channel/channel.h
│       └── src/http_hub.c
└── main/
    ├── CMakeLists.txt              (SRCS 逐步缩到只剩 main.c; REQUIRES 各接口 component)
    └── main.c                      (Task 8 重写为接口组装)
```

---

## Task 0: 骨架 — 建 components 目录与桩,全工程编译通过

**Files:**
- Create: `components/ip_config/CMakeLists.txt`, `components/ip_config/include/ip_config/net_config.h`
- Modify: `main/CMakeLists.txt`

- [ ] **Step 1: 建 ip_config component 目录并迁入 net_config.h**

```bash
cd software/firmware
mkdir -p components/ip_config/include/ip_config
git mv main/net_config.h components/ip_config/include/ip_config/net_config.h
```

- [ ] **Step 2: 写 ip_config/CMakeLists.txt(纯头, INTERFACE)**

`components/ip_config/CMakeLists.txt`:
```cmake
idf_component_register(INCLUDE_DIRS "include")
```

- [ ] **Step 3: 改 main.c 与 frame_client.c 的 include 路径**

把 `#include "net_config.h"` 改为 `#include "ip_config/net_config.h"`(`main.c`、`frame_client.c`、`wifi_prov.c`、`ble_prov.c` 中所有出现处)。

- [ ] **Step 4: main/CMakeLists.txt 加 REQUIRES ip_config**

在 `main/CMakeLists.txt` 的 `REQUIRES` 列表加一行 `ip_config`(其余不变,旧 .c 仍在 SRCS)。

- [ ] **Step 5: 编译验证**

Run: `./build.sh build`
Expected: 编译成功(`Project build complete`),行为未变 —— 仅把 net_config.h 挪进 component。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(fw): 骨架 — net_config 迁入 ip_config component"
```

---

## Task 1: ip_hal — 下沉 SPI/I2C/GPIO 与板级引脚

**Files:**
- Create: `components/ip_hal/include/ip_hal/{board_pins.h, spi_bus.h, i2c_bus.h}`, `components/ip_hal/src/{spi_bus.c, i2c_bus.c}`, `components/ip_hal/CMakeLists.txt`
- Modify: 暂不动 epd_uc8179.c / htu21d.c(它们 Task 2/3 才迁;本 Task 只建好 HAL 供后续用)

- [ ] **Step 1: 迁 pins.h → board_pins.h**

```bash
git mv main/pins.h components/ip_hal/include/ip_hal/board_pins.h
```

- [ ] **Step 2: 写 spi_bus.h 接口**

`components/ip_hal/include/ip_hal/spi_bus.h`:
```c
#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
// EPD 用的 SPI: 初始化 + 片选/DC/RST 由调用方控 GPIO; 这里只管总线与传输
esp_err_t hal_spi_init(int mosi, int sclk, int cs, int dc, int rst, int busy);
void hal_spi_cmd(uint8_t cmd);                       // DC=0 发命令
void hal_spi_data(uint8_t data);                     // DC=1 发单字节
void hal_spi_data_buf(const uint8_t *buf, size_t len);
void hal_spi_reset(void);                            // 复位时序
int  hal_spi_busy_level(void);                       // 读 BUSY 脚
```

- [ ] **Step 3: 写 spi_bus.c(从 epd_uc8179.c 的 HAL 部分迁移)**

`components/ip_hal/src/spi_bus.c`:把 `epd_uc8179.c` 中 `epd_hal_init`/`spi_tx`/`epd_send_cmd`/`epd_send_data`/`epd_send_data_buf`/`epd_reset`/`epd_wait_busy` 里**纯硬件操作**搬过来,改名为 `hal_spi_*`,引脚改为参数(由 init 传入,保存到 static)。`hal_spi_busy_level` 返回 `gpio_get_level(busy)`。保留原 SPI 配置(10MHz, mode0, SPI2_HOST)。

- [ ] **Step 4: 写 i2c_bus.h / i2c_bus.c(从 htu21d.c 的 I2C 部分迁移)**

`components/ip_hal/include/ip_hal/i2c_bus.h`:
```c
#pragma once
#include <stdint.h>
#include "esp_err.h"
esp_err_t hal_i2c_init(int sda, int scl, uint8_t addr_7b);
esp_err_t hal_i2c_write(const uint8_t *data, size_t len, int timeout_ms);
esp_err_t hal_i2c_read(uint8_t *data, size_t len, int timeout_ms);
```
`src/i2c_bus.c`:把 `htu21d.c` 的 `i2c_new_master_bus`/`add_device`/`i2c_master_transmit`/`i2c_master_receive` 封装成上述函数(bus/dev handle 存 static)。

- [ ] **Step 5: 写 ip_hal/CMakeLists.txt**

```cmake
idf_component_register(
    SRCS "src/spi_bus.c" "src/i2c_bus.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_driver_i2c
)
```

- [ ] **Step 6: 改 epd_uc8179.c / htu21d.c 暂时 include 新 HAL(过渡)**

`main/epd_uc8179.c` 顶部把 `#include "pins.h"` 改为 `#include "ip_hal/board_pins.h"`;`htu21d.c` 同理。`main/CMakeLists.txt` 的 REQUIRES 加 `ip_hal`。(此步只为让引脚头跟着走,实际 HAL 调用切换在 Task 2/3。)

- [ ] **Step 7: 编译验证**

Run: `./build.sh build`
Expected: 成功。ip_hal 已编译进来,旧驱动仍用自己的实现(尚未切到 hal_*)。

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(fw): 新增 ip_hal component(SPI/I2C/GPIO 封装 + board_pins)"
```

---

## Task 2: ip_display — display 接口 + UC8179 实现 + selftest

**Files:**
- Create: `components/ip_display/include/ip_display/display.h`, `components/ip_display/src/uc8179.c`, `components/ip_display/src/uc8179_selftest.c`, `components/ip_display/CMakeLists.txt`
- Modify: `main/CMakeLists.txt`(移除 epd_uc8179.c)、`main/frame_client.c`、`main/main.c`

- [ ] **Step 1: 写 display.h(spec §4.1 完整接口)**

`components/ip_display/include/ip_display/display.h`:
```c
#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

typedef enum { DISP_BWR, DISP_BW, DISP_ACEP7, DISP_RGB } disp_color_model_t;

typedef struct {
    uint16_t width, height;
    disp_color_model_t color_model;
    const char *frame_format;   // 如 "bwr-dualplane"
    size_t frame_bytes;
} display_caps_t;

typedef struct {
    esp_err_t (*init)(void);
    void      (*get_caps)(display_caps_t *out);
    esp_err_t (*show)(const uint8_t *frame, size_t len);  // frame = black(48000)+red(48000)
    void      (*refresh)(void);
    void      (*clear)(void);
    void      (*sleep)(void);
    void      (*selftest)(void);   // bring-up 图案(白/黑/红/分屏/棋盘)
} display_if_t;

const display_if_t *uc8179_driver(void);
```

- [ ] **Step 2: 写 uc8179.c —— 迁移 + 实现 display_if_t**

`components/ip_display/src/uc8179.c`:从 `main/epd_uc8179.c` 迁移 `epd_init`/`epd_display_planes`/`epd_clear`/`epd_refresh`/`epd_fill_plane`/`epd_sleep`,改为 static 函数,底层硬件调用换成 `hal_spi_*`(用 `ip_hal/spi_bus.h`)。`show()` = 现 `epd_display_planes`(frame 前 48000 为 black、后 48000 为 red,内部按现有极性 `~black`/`red 直发`)。文件末尾给:
```c
static esp_err_t disp_init(void) {
    hal_spi_init(EPD_PIN_MOSI, EPD_PIN_SCLK, EPD_PIN_CS, EPD_PIN_DC, EPD_PIN_RST, EPD_PIN_BUSY);
    uc8179_panel_init();   // 原 epd_init 序列
    return ESP_OK;
}
static void disp_get_caps(display_caps_t *o){
    o->width=800; o->height=480; o->color_model=DISP_BWR;
    o->frame_format="bwr-dualplane"; o->frame_bytes=96000;
}
static const display_if_t s_if = {
    .init=disp_init, .get_caps=disp_get_caps, .show=disp_show,
    .refresh=disp_refresh, .clear=disp_clear, .sleep=disp_sleep,
    .selftest=uc8179_selftest_run,
};
const display_if_t *uc8179_driver(void){ return &s_if; }
```

- [ ] **Step 3: 写 uc8179_selftest.c**

从 `epd_uc8179.c` 迁移 `epd_show_solid`/`epd_show_split`/`epd_show_checker`,组成 `void uc8179_selftest_run(void)`:依次白/黑/红/分屏/棋盘(各 `vTaskDelay(4000)`),供 `INKPULSE_VERIFY` 用。声明放 uc8179.c 内部头或 extern。

- [ ] **Step 4: 写 ip_display/CMakeLists.txt**

```cmake
idf_component_register(
    SRCS "src/uc8179.c" "src/uc8179_selftest.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_hal ip_config
)
```

- [ ] **Step 5: 切换 frame_client.c 用 display 接口(去耦合)**

`main/frame_client.c`:删 `#include "epd_uc8179.h"` 和 `#include "pins.h"`;改为 `#include "ip_display/display.h"`。把直接调 `epd_display_planes(s_black, s_red)` 改为通过传入的 display 指针 —— 即 `frame_fetch_and_show` 增参 `const display_if_t *disp`,内部 `disp->show(framebuf,96000); disp->refresh();`(framebuf 改成连续一块 96000,black 段 + red 段)。`EPD_PLANE_BYTES` 用常量 48000。

- [ ] **Step 6: main/CMakeLists.txt 移除 epd_uc8179.c、加 REQUIRES ip_display**

从 SRCS 删 `"epd_uc8179.c"`;REQUIRES 加 `ip_display`。`git rm main/epd_uc8179.c main/epd_uc8179.h`。main.c 里 `epd_*` 调用暂时改用 `uc8179_driver()`(过渡:main.c 顶部取 `const display_if_t *disp = uc8179_driver();`,把 `epd_hal_init();epd_init()` → `disp->init()`,`epd_clear()` → `disp->clear()`,VERIFY 分支 → `disp->selftest()`)。

- [ ] **Step 7: 编译验证**

Run: `./build.sh build`
Expected: 成功。display 已 component 化,frame_client 不再依赖具体屏驱动。

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(fw): ip_display component(display_if 接口 + UC8179 实现 + selftest), frame_client 解耦屏驱动"
```

---

## Task 3: ip_sensor — sensor 接口 + HTU21D 实现(带有效位)

**Files:**
- Create: `components/ip_sensor/include/ip_sensor/sensor.h`, `components/ip_sensor/src/htu21d.c`, `components/ip_sensor/CMakeLists.txt`
- Modify: `main/CMakeLists.txt`、`main/main.c`、`main/frame_client.c`

- [ ] **Step 1: 写 sensor.h(spec §4.2)**

`components/ip_sensor/include/ip_sensor/sensor.h`:
```c
#pragma once
#include <stdbool.h>
#include "esp_err.h"
typedef struct {
    float temp_c;   bool temp_valid;
    float humidity; bool humidity_valid;
} sensor_env_t;
typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*read)(sensor_env_t *out);
} sensor_if_t;
const sensor_if_t *htu21d_sensor(void);
```

- [ ] **Step 2: 写 htu21d.c —— 迁移 + 有效位**

从 `main/htu21d.c` 迁移,I2C 操作改用 `hal_i2c_*`。`read()`:温度照算并 `temp_valid=true`;湿度 raw==0 时 `humidity_valid=false`(否则按公式 + true)。保留软复位与诊断日志。末尾:
```c
static const sensor_if_t s_if = { .init=htu_init, .read=htu_read };
const sensor_if_t *htu21d_sensor(void){ return &s_if; }
```

- [ ] **Step 3: 写 ip_sensor/CMakeLists.txt**

```cmake
idf_component_register(
    SRCS "src/htu21d.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_hal
)
```

- [ ] **Step 4: main/CMakeLists.txt 移除 htu21d.c、加 REQUIRES ip_sensor;切 main.c**

`git rm main/htu21d.c main/htu21d.h`;SRCS 删 htu21d.c;REQUIRES 加 ip_sensor。main.c 取 `const sensor_if_t *sensor = htu21d_sensor();`,`htu21d_init()`→`sensor->init()`,`htu21d_read(&t,&h)`→`sensor->read(&env)`。frame_fetch 调用改为传 `env`(温湿度 + 有效位;无效时传 Hub 的方式:`humidity_valid?h:-1`,与现有 Hub 隐藏逻辑一致)。

- [ ] **Step 5: 编译验证**

Run: `./build.sh build`
Expected: 成功。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(fw): ip_sensor component(sensor_if + HTU21D, 湿度有效位取代-100哨兵)"
```

---

## Task 4: ip_net — WiFi STA 生命周期

**Files:**
- Create: `components/ip_net/include/ip_net/net.h`, `components/ip_net/src/net_sta.c`, `components/ip_net/CMakeLists.txt`
- Modify: `main/wifi_prov.c`(拆分)、`main/CMakeLists.txt`

- [ ] **Step 1: 写 net.h**

`components/ip_net/include/ip_net/net.h`:
```c
#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t ip_net_init(void);                 // nvs/netif/event/wifi 初始化(一次)
esp_err_t ip_net_sta_connect(const char *ssid, const char *pass);  // WPA3-SAE + 循环重连; 成功返回 ESP_OK
bool      ip_net_is_up(void);
// 供 provisioning 复用: 创建默认 STA netif / 注册事件
esp_err_t ip_net_prepare_sta(void);
```

- [ ] **Step 2: 写 net_sta.c —— 从 wifi_prov.c 迁 STA 部分**

迁移 `wifi_prov.c` 的:nvs/netif/event/wifi_init、`on_wifi` 事件处理(GOT_IP/DISCONNECTED + EventGroup)、STA 连接的**循环重连**逻辑(`STA_CONNECT_ATTEMPTS=15` + 2s 间隔 + WPA3 config:`WIFI_AUTH_WPA2_WPA3_PSK`/`pmf_cfg.capable`/`sae_pwe_h2e=WPA3_SAE_PWE_BOTH`)。封装为 `ip_net_init`/`ip_net_prepare_sta`/`ip_net_sta_connect`。事件组与 reason 日志一并迁入。

- [ ] **Step 3: 写 ip_net/CMakeLists.txt**

```cmake
idf_component_register(
    SRCS "src/net_sta.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_wifi esp_event esp_netif nvs_flash
)
```

- [ ] **Step 4: 编译验证(此时 wifi_prov.c 仍在,net 并存)**

Run: `./build.sh build`
Expected: 成功(net_sta 编入;wifi_prov.c 暂未删,Task 5 处理)。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(fw): ip_net component(WiFi STA 连接 + WPA3-SAE 循环重连)"
```

---

## Task 5: ip_provisioning — BLE/SoftAP 配网 + NVS 凭据

**Files:**
- Create: `components/ip_provisioning/include/ip_provisioning/provisioning.h`, `components/ip_provisioning/src/{ble_prov.c, softap_prov.c, creds_nvs.c}`, `components/ip_provisioning/CMakeLists.txt`
- Modify: `main/CMakeLists.txt`、删 `main/wifi_prov.c`/`ble_prov.c`

- [ ] **Step 1: 写 provisioning.h**

`components/ip_provisioning/include/ip_provisioning/provisioning.h`:
```c
#pragma once
#include <stdbool.h>
#include <stddef.h>
typedef struct { bool (*run)(int timeout_s); } provisioning_if_t;
const provisioning_if_t *ble_provisioning(void);
const provisioning_if_t *softap_provisioning(void);
// 凭据(NVS namespace "inkpulse")
bool creds_load(char *ssid, size_t sl, char *pass, size_t pl);
void creds_save(const char *ssid, const char *pass);
```

- [ ] **Step 2: 写 creds_nvs.c**

从 `wifi_prov.c`/`ble_prov.c` 抽 `load_creds`/`save_creds` 成 `creds_load`/`creds_save`(NVS namespace "inkpulse")。

- [ ] **Step 3: 写 ble_prov.c —— 迁移,实现 provisioning_if_t**

迁移 `main/ble_prov.c`(`wifi_prov_mgr_wait` + 定时器超时方案),凭据存用 `creds_save`。包装:
```c
static bool ble_run(int t){ return ble_prov_run(t); }  // ble_prov_run 改 static
static const provisioning_if_t s_if = { .run = ble_run };
const provisioning_if_t *ble_provisioning(void){ return &s_if; }
```

- [ ] **Step 4: 写 softap_prov.c —— 迁移 SoftAP 网页配网**

从 `wifi_prov.c` 迁 `start_provision_ap`/`form_get`/`save_post`(含 `esp_wifi_stop()` 切 AP 修复),封装 `softap_run(int)`(开热点 + httpd,返回是否配网完成)+ `provisioning_if_t`。

- [ ] **Step 5: 写 ip_provisioning/CMakeLists.txt**

```cmake
idf_component_register(
    SRCS "src/ble_prov.c" "src/softap_prov.c" "src/creds_nvs.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_net ip_config wifi_provisioning bt esp_http_server nvs_flash esp_wifi
)
```

- [ ] **Step 6: 删 main/wifi_prov.c、ble_prov.c;改 main/CMakeLists.txt**

```bash
git rm main/wifi_prov.c main/wifi_prov.h main/ble_prov.c main/ble_prov.h
```
main/CMakeLists.txt SRCS 删这两个;REQUIRES 加 `ip_net ip_provisioning`,删 `wifi_provisioning bt`(已转移到 ip_provisioning)。

- [ ] **Step 7: main.c 临时编排接通(让其编译)**

main.c 配网段改为:`if (!creds_load(...)) { if (!ble_provisioning()->run(PROV_BLE_TIMEOUT_S)) softap_provisioning()->run(0); }` 再 `ip_net_init(); ip_net_prepare_sta(); ip_net_sta_connect(ssid,pass);`(完整编排在 Task 8 收口,这里先保证能编)。

- [ ] **Step 8: 编译验证**

Run: `./build.sh build`
Expected: 成功。配网与网络已分别 component 化。

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(fw): ip_provisioning component(BLE/SoftAP 配网 + NVS 凭据), 删除旧 wifi_prov/ble_prov"
```

---

## Task 6: ip_channel — channel 接口 + HTTP-Hub 实现

**Files:**
- Create: `components/ip_channel/include/ip_channel/channel.h`, `components/ip_channel/src/http_hub.c`, `components/ip_channel/CMakeLists.txt`
- Modify: 删 `main/frame_client.c`、`main/CMakeLists.txt`

- [ ] **Step 1: 写 channel.h(spec §4.3)**

`components/ip_channel/include/ip_channel/channel.h`:
```c
#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
#include "ip_display/display.h"
#include "ip_sensor/sensor.h"

typedef struct { bool changed; int next_refresh_s; } channel_result_t;

typedef struct {
    esp_err_t (*init)(const display_caps_t *caps);
    esp_err_t (*fetch)(uint8_t *buf, size_t buf_len,
                       const sensor_env_t *env, channel_result_t *out);
} channel_if_t;

const channel_if_t *http_hub_channel(void);
```

- [ ] **Step 2: 写 http_hub.c —— 从 frame_client.c 迁移**

迁移 `frame_client.c` 的 HTTP 拉帧逻辑(esp_http_client + ETag/304 + X-Next-Refresh),改为:`init(caps)` 存 caps(帧字节数);`fetch(buf,len,env,out)` 把帧收进 `buf`(连续 black+red),`env` 按 `humidity_valid` 决定 `h` 取值拼进 URL query,`out->changed`=200且收满、`out->next_refresh_s`=X-Next-Refresh。**不再调用任何 display 函数**(显示交回 app)。末尾:
```c
static const channel_if_t s_if = { .init=ch_init, .fetch=ch_fetch };
const channel_if_t *http_hub_channel(void){ return &s_if; }
```

- [ ] **Step 3: 写 ip_channel/CMakeLists.txt**

```cmake
idf_component_register(
    SRCS "src/http_hub.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_display ip_sensor ip_config esp_http_client
)
```

- [ ] **Step 4: 删 main/frame_client.c;改 main/CMakeLists.txt**

```bash
git rm main/frame_client.c main/frame_client.h
```
SRCS 删 frame_client.c;REQUIRES 加 `ip_channel`,删 `esp_http_client`(转移到 ip_channel)。

- [ ] **Step 5: 编译验证**

Run: `./build.sh build`
Expected: 成功(此时 main.c 可能还引用旧 frame_fetch_and_show —— 若编译报未定义,在 Step 6 的 Task 8 收口前,临时在 main.c 用 channel 接口替换,见 Task 8)。

> 注:若本 Task 末编译因 main.c 旧调用失败,直接进入 Task 8 收口 main.c 后再统一验证;Task 6 的 commit 可与 Task 8 合并。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(fw): ip_channel component(channel_if + HTTP-Hub), 删除 frame_client"
```

---

## Task 7: 顶层 CMake 与 ip_config 收尾确认

**Files:**
- Modify: `software/firmware/CMakeLists.txt`(确认无需手列 components;ESP-IDF 默认扫描 `components/`)

- [ ] **Step 1: 确认顶层 CMakeLists.txt 不需改**

ESP-IDF 自动把 `<project>/components/` 下每个子目录当 component。打开 `software/firmware/CMakeLists.txt` 确认没有写死的 COMPONENT 列表会冲突;通常只有 `include($ENV{IDF_PATH}/tools/cmake/project.cmake)` + `project(inkpulse)`,无需改。

- [ ] **Step 2: 编译验证**

Run: `./build.sh build`
Expected: 成功,7 个 component 都被发现并编译。

- [ ] **Step 3: Commit(若有改动)**

```bash
git add -A
git commit -m "refactor(fw): 确认顶层 CMake 自动发现 components" || echo "无改动, 跳过"
```

---

## Task 8: app 重写 — main.c 纯接口组装 + 主循环

**Files:**
- Modify: `main/main.c`(重写)、`main/CMakeLists.txt`(SRCS 只剩 main.c)

- [ ] **Step 1: 重写 main.c(联网主循环 + VERIFY 分支)**

`main/main.c`:
```c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "ip_config/net_config.h"
#include "ip_display/display.h"
#include "ip_sensor/sensor.h"
#include "ip_net/net.h"
#include "ip_provisioning/provisioning.h"
#include "ip_channel/channel.h"

static const char *TAG = "inkpulse";
static uint8_t s_framebuf[96000];   // BWR 双 plane; 上限按 caps.frame_bytes

#ifdef INKPULSE_VERIFY
void app_main(void){
    const display_if_t *disp = uc8179_driver();
    const sensor_if_t  *sensor = htu21d_sensor();
    disp->init();
    sensor_env_t e; for(int i=0;i<3;i++){ sensor->read(&e);
        ESP_LOGI(TAG,"温度=%.2f valid=%d 湿度=%.2f valid=%d",
            e.temp_c,e.temp_valid,e.humidity,e.humidity_valid); vTaskDelay(pdMS_TO_TICKS(1000)); }
    disp->selftest();
    while(1) vTaskDelay(pdMS_TO_TICKS(1000));
}
#else
void app_main(void){
    const display_if_t *disp = uc8179_driver();
    const sensor_if_t  *sensor = htu21d_sensor();
    const channel_if_t *chan = http_hub_channel();

    disp->init();
    display_caps_t caps; disp->get_caps(&caps);
    sensor->init();
    ip_net_init();

    char ssid[33]={0}, pass[65]={0};
    if (!creds_load(ssid,sizeof ssid,pass,sizeof pass)) {
        ip_net_prepare_sta();
        if (!ble_provisioning()->run(PROV_BLE_TIMEOUT_S))
            softap_provisioning()->run(0);   // 兜底; 内部配完重启
        // 配网后凭据已存, 重新读
        creds_load(ssid,sizeof ssid,pass,sizeof pass);
    }
    if (ip_net_sta_connect(ssid,pass) != ESP_OK) {
        disp->clear(); while(1) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    chan->init(&caps);
    disp->clear();   // 开机消残影

    while (1) {
        sensor_env_t env; sensor->read(&env);
        channel_result_t r;
        if (chan->fetch(s_framebuf, sizeof s_framebuf, &env, &r) == ESP_OK && r.changed) {
            disp->show(s_framebuf, caps.frame_bytes);
            disp->refresh();
        }
        int next = r.next_refresh_s < 30 ? 30 : r.next_refresh_s;
        ESP_LOGI(TAG,"循环, next=%ds", next);
        vTaskDelay(pdMS_TO_TICKS((uint32_t)next*1000));
    }
}
#endif
```

- [ ] **Step 2: main/CMakeLists.txt 收口**

`main/CMakeLists.txt`:
```cmake
idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES ip_config ip_display ip_sensor ip_net ip_provisioning ip_channel
)
```
保留 `if(INKPULSE_VERIFY) target_compile_definitions(...)`(宏修复)。

- [ ] **Step 3: 确认 main/ 已无旧平铺 .c**

```bash
ls main/    # 期望只有 main.c CMakeLists.txt
```

- [ ] **Step 4: 编译验证**

Run: `./build.sh build`
Expected: 成功。main 只依赖接口 component。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(fw): main 重写为纯接口组装 + 主循环, 删除全部旧平铺文件"
```

---

## Task 9: 真机端到端回归

**Files:** 无(验证)

- [ ] **Step 1: VERIFY 模式真机自检**

```bash
PORT=/dev/ttyACM0 ./build.sh verify   # 注意 cache 残留已修, 会真进 VERIFY
PORT=/dev/ttyACM0 ./build.sh flash
```
盯串口/屏:温湿度读数(温度有效/湿度 invalid)、白→黑→红→分屏→棋盘。预期与重构前一致。

- [ ] **Step 2: 烧回正常固件, 端到端回归**

```bash
PORT=/dev/ttyACM0 ./build.sh build && PORT=/dev/ttyACM0 ./build.sh flash
```
串口确认全链路:`creds_load` →(已配网)`ip_net_sta_connect` 连上 Xiaomi 15 WPA3-SAE → `chan->fetch` → `disp->show` → `fetch 新帧已刷`。屏显仪表盘(温度,湿度隐藏),与重构前一致。

- [ ] **Step 3: 验收自检**

确认:`main/` 只剩 main.c;`grep -rn "epd_\|htu21d_\|frame_fetch" main/main.c` 无具体实现符号(只有接口指针调用);`grep -rn "uc8179\|http_hub\|htu21d" main/main.c` 仅出现在工厂函数取指针处。回答验收问题:新增一个 display 实现需改哪些 → 答:新 component + main 一行 `uc8179_driver()`→新工厂 + 该 component CMake,零改 channel/sensor/net/app 逻辑。

- [ ] **Step 4: 文档更新 + Commit**

更新 `software/firmware/README.md` 的「源文件」表为 components 结构(各 component 职责一句话)。
```bash
git add -A
git commit -m "docs(fw): README 更新为 components 分层结构; 重构真机回归通过"
```

---

## Self-Review

- **Spec 覆盖**:§3 分层→Task 0-7;§4 接口→各 Task Step 1;§5 帧格式协商→Task 2 caps + Task 6 channel init;§6 数据流→Task 8 main.c;§7 映射→逐 Task 迁移步骤;§8 容错→Task 4(重连)/Task 5(SoftAP esp_wifi_stop)/Task 6(离线保留帧,迁移时保留);§9 测试→Task 9;§10 分期→Task 0-9 对应。覆盖完整。
- **Placeholder**:无 TBD/TODO;迁移步骤给了源→目标 + 具体改动点(代码已在仓库,执行 agent 可读源文件),新增接口/适配/工厂代码完整给出。
- **类型一致**:`display_if_t`/`channel_if_t`/`sensor_if_t`/`provisioning_if_t`、工厂名 `uc8179_driver`/`htu21d_sensor`/`http_hub_channel`/`ble_provisioning`/`softap_provisioning`、`creds_load/creds_save`、`ip_net_init/ip_net_prepare_sta/ip_net_sta_connect` 在 spec 与各 Task 间一致;帧 96000=black48000+red48000 贯穿一致。
