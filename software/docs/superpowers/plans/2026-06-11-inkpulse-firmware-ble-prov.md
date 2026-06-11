# InkPulse 蓝牙配网 实现计划（BLE 主 + SoftAP 兜底）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans（推荐，本计划需硬件在环）或 superpowers:subagent-driven-development。步骤用 `- [ ]` 复选框跟踪。
> **说明：** 固件无自动化单测（硬件相关），各任务用「编译通过 + 硬件联调」替代 TDD 红绿循环。沿用现有 `build.sh`（`PORT=/dev/ttyACM0`）。

**Goal:** 设备无凭据时先用 BLE 配网（ESP-IDF `wifi_provisioning` + 官方 App），超时无果自动回退到现有 SoftAP 网页；任一方式存 NVS `inkpulse` 后重启走 STA。

**Architecture:** 复用现有 `wifi_prov.c` 的 STA / SoftAP 网页 / NVS。新增 `ble_prov.c` 封装 BLE 配网（NimBLE + protocomm），在 `wifi_connect_or_provision()` 里编排「BLE→超时→SoftAP」顺序切换。加 BLE 协议栈后体积超 1MB，故换 2MB 分区表。

**Tech Stack:** ESP-IDF v5.3.2、`wifi_provisioning`（scheme_ble）、NimBLE、nvs_flash。

**对接契约（来自蓝牙配网设计，勿改）：**
- 凭据统一写 NVS namespace `inkpulse` 的 `ssid`/`pass`；启动只读这一处。
- BLE 广播名 `PROV_InkPulse`、security1、PoP `inkpulse`、超时 180s。
- BLE 超时/启动失败 → 回退现有 SoftAP 网页（`InkPulse-Setup` / 192.168.4.1）。

参考：设计 `software/docs/superpowers/specs/2026-06-11-inkpulse-ble-provisioning-design.md`；现有 `main/wifi_prov.c`、`main/net_config.h`。

---

## Task 1: 分区表扩到 2MB + 启用 NimBLE

**Files:**
- Create: `software/firmware/partitions.csv`
- Modify: `software/firmware/sdkconfig.defaults`

- [ ] **Step 1: 新建 `partitions.csv`（8MB flash，app=2MB）**

```
# Name,   Type, SubType, Offset,   Size
nvs,      data, nvs,     0x9000,   0x6000
phy_init, data, phy,     0xf000,   0x1000
factory,  app,  factory, 0x10000,  0x200000
```

- [ ] **Step 2: `sdkconfig.defaults` 追加 BLE/分区表配置**

在文件末尾追加：
```
# 自定义分区表(app 扩到 2MB, 容纳 BLE 协议栈)
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
# 蓝牙: 启用 NimBLE(省 flash/RAM)
CONFIG_BT_ENABLED=y
CONFIG_BT_NIMBLE_ENABLED=y
```

- [ ] **Step 3: 删旧 sdkconfig 让默认值重新生成，编译验证分区表生效**

Run:
```bash
cd software/firmware && rm -f sdkconfig && ./build.sh build 2>&1 | tail -15
```
Expected: 编译通过；日志 Partition Table 中 `factory` 行 Length 为 `0x200000`（2MB）。此时还没用 BLE 代码，仅验证配置生效。

- [ ] **Step 4: Commit**

```bash
git add software/firmware/partitions.csv software/firmware/sdkconfig.defaults
git commit -m "build(fw): 自定义分区表(app 2MB) + 启用NimBLE"
```

---

## Task 2: BLE 配网模块 `ble_prov`

**Files:**
- Create: `software/firmware/main/ble_prov.h`
- Create: `software/firmware/main/ble_prov.c`

- [ ] **Step 1: `ble_prov.h`**

```c
#pragma once
#include <stdbool.h>
// 启动 BLE 配网, 阻塞等待直到配网成功或超时(timeout_s 秒)。
// 成功: 凭据已写入 NVS namespace "inkpulse", 返回 true(调用方应 esp_restart)。
// 超时/启动失败: 返回 false(调用方应回退 SoftAP)。
// 前置: 调用前需已 esp_wifi_init + 创建默认 STA netif。
bool ble_prov_run(int timeout_s);
```

- [ ] **Step 2: `ble_prov.c`**

```c
#include "ble_prov.h"
#include "net_config.h"
#include "esp_log.h"
#include "esp_event.h"
#include "nvs.h"
#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_ble.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "ble_prov";
static EventGroupHandle_t s_eg;
#define PROV_OK BIT0

static void save_creds(const char *ssid, const char *pass)
{
    nvs_handle_t h;
    if (nvs_open("inkpulse", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_str(h, "ssid", ssid);
        nvs_set_str(h, "pass", pass);
        nvs_commit(h);
        nvs_close(h);
        ESP_LOGI(TAG, "凭据已存 NVS (ssid=%s)", ssid);
    }
}

static void prov_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base != WIFI_PROV_EVENT) return;
    switch (id) {
    case WIFI_PROV_START:
        ESP_LOGI(TAG, "BLE 配网启动, 等待 App 连接...");
        break;
    case WIFI_PROV_CRED_RECV: {
        wifi_sta_config_t *c = (wifi_sta_config_t *)data;
        ESP_LOGI(TAG, "收到凭据 SSID=%s", (const char *)c->ssid);
        save_creds((const char *)c->ssid, (const char *)c->password);
        break;
    }
    case WIFI_PROV_CRED_FAIL:
        ESP_LOGW(TAG, "凭据验证失败(密码错或连不上)");
        break;
    case WIFI_PROV_CRED_SUCCESS:
        ESP_LOGI(TAG, "BLE 配网成功");
        xEventGroupSetBits(s_eg, PROV_OK);
        break;
    case WIFI_PROV_END:
        wifi_prov_mgr_deinit();
        break;
    default:
        break;
    }
}

bool ble_prov_run(int timeout_s)
{
    s_eg = xEventGroupCreate();
    esp_event_handler_register(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, prov_event_handler, NULL);

    wifi_prov_mgr_config_t cfg = {
        .scheme = wifi_prov_scheme_ble,
        .scheme_event_handler = WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BTDM,
    };
    if (wifi_prov_mgr_init(cfg) != ESP_OK) {
        ESP_LOGE(TAG, "prov mgr init 失败, 回退 SoftAP");
        return false;
    }

    // 自定义 128-bit service UUID(官方示例值, App 据此识别)
    uint8_t uuid[16] = {0xb4,0xdf,0x5a,0x1c,0x3f,0x6b,0xf4,0xbf,
                        0xea,0x4a,0x82,0x03,0x04,0x90,0x1a,0x02};
    wifi_prov_scheme_ble_set_service_uuid(uuid);

    if (wifi_prov_mgr_start_provisioning(WIFI_PROV_SECURITY_1, PROV_POP,
                                         PROV_BLE_NAME, NULL) != ESP_OK) {
        ESP_LOGE(TAG, "start provisioning 失败, 回退 SoftAP");
        wifi_prov_mgr_deinit();
        return false;
    }
    ESP_LOGI(TAG, "BLE 广播名=%s PoP=%s 超时=%ds", PROV_BLE_NAME, PROV_POP, timeout_s);

    EventBits_t b = xEventGroupWaitBits(s_eg, PROV_OK, pdFALSE, pdFALSE,
                                        pdMS_TO_TICKS(timeout_s * 1000));
    if (b & PROV_OK) {
        vTaskDelay(pdMS_TO_TICKS(1000));   // 等组件收尾(END→deinit)
        return true;
    }
    ESP_LOGW(TAG, "BLE 配网超时, 停止并回退 SoftAP");
    wifi_prov_mgr_stop_provisioning();
    vTaskDelay(pdMS_TO_TICKS(500));
    wifi_prov_mgr_deinit();
    return false;
}
```

> 注：`WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BTDM` 会在配网结束后释放 BT 内存，让回退的 SoftAP(WiFi AP) 能用内存。若某些 IDF 版本宏名不同，按编译提示调整。

- [ ] **Step 3: 暂不单独编译（缺 net_config 常量与 CMake 注册，Task 3 一并编译）**

无独立验证步骤；Task 3 完成后统一编译。

---

## Task 3: 常量 + 编排切换 + CMake 注册

**Files:**
- Modify: `software/firmware/main/net_config.h`
- Modify: `software/firmware/main/wifi_prov.c`
- Modify: `software/firmware/main/CMakeLists.txt`

- [ ] **Step 1: `net_config.h` 加 BLE 配网常量**

在 `#define PROV_AP_PASS ...` 之后追加：
```c
// BLE 配网(优先) 参数
#define PROV_BLE_NAME       "PROV_InkPulse"   // BLE 广播名(官方 App 扫描显示)
#define PROV_POP            "inkpulse"         // proof-of-possession 口令(App 输入)
#define PROV_BLE_TIMEOUT_S  180                // BLE 等待超时, 超时回退 SoftAP
```

- [ ] **Step 2: `wifi_prov.c` 顶部加 include**

在 `#include "net_config.h"` 之后加：
```c
#include "ble_prov.h"
```

- [ ] **Step 3: `wifi_prov.c` 改无凭据分支为「BLE→超时→SoftAP」**

把现有：
```c
    char ssid[33] = {0}, pass[65] = {0};
    if (!load_creds(ssid, pass)) {
        start_provision_ap();
        return false;
    }
```
改成：
```c
    char ssid[33] = {0}, pass[65] = {0};
    if (!load_creds(ssid, pass)) {
        // wifi_provisioning 需要默认 STA netif
        esp_netif_create_default_wifi_sta();
        // ① 优先 BLE 配网
        if (ble_prov_run(PROV_BLE_TIMEOUT_S)) {
            ESP_LOGI(TAG, "BLE 配网成功, 重启走 STA");
            esp_restart();
        }
        // ② BLE 超时/失败 → SoftAP 网页兜底
        ESP_LOGW(TAG, "回退 SoftAP 配网");
        start_provision_ap();
        return false;
    }
```

> 注：`start_provision_ap()` 内部已 `esp_netif_create_default_wifi_ap()` + `set_mode(WIFI_MODE_AP)`。BLE 结束已释放 BTDM；若 SoftAP 起不来(WiFi 状态残留)，在 `start_provision_ap()` 首行加 `esp_wifi_stop();` 再重配——bring-up 时按需微调。

- [ ] **Step 4: `main/CMakeLists.txt` 注册新源文件与组件**

把 `SRCS` 列表加入 `"ble_prov.c"`；`REQUIRES` 加入 `wifi_provisioning` 与 `bt`。改完应为：
```cmake
idf_component_register(
    SRCS
        "main.c"
        "epd_uc8179.c"
        "htu21d.c"
        "wifi_prov.c"
        "ble_prov.c"
        "frame_client.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver
        esp_driver_i2c
        esp_wifi
        esp_event
        esp_netif
        esp_http_client
        esp_http_server
        nvs_flash
        wifi_provisioning
        bt
)
```

- [ ] **Step 5: 编译验证（含 BLE，确认未超 2MB 分区）**

Run:
```bash
cd software/firmware && ./build.sh build 2>&1 | tail -15
```
Expected: `Project build complete`；末尾 `check_sizes` 显示 `inkpulse.bin` size 小于 `0x200000`（2MB）且有 free 余量；0 error。

- [ ] **Step 6: Commit**

```bash
git add software/firmware/main/ble_prov.c software/firmware/main/ble_prov.h \
        software/firmware/main/net_config.h software/firmware/main/wifi_prov.c \
        software/firmware/main/CMakeLists.txt
git commit -m "feat(fw): BLE配网(wifi_provisioning+NimBLE) + BLE→SoftAP兜底编排"
```

---

## Task 4: 硬件联调（App 配网 + 兜底）

**Files:** 无（验证任务）

- [ ] **Step 1: 烧录**

Run:
```bash
cd software/firmware && PORT=/dev/ttyACM0 ./build.sh flash
```
Expected: `Hash of data verified.` + `Hard resetting`。

- [ ] **Step 2: 抓启动日志，确认进入 BLE 配网**

复位抓日志（沿用 net 阶段的 pyserial 抓取脚本，读 ~16s），期望看到：
```
ble_prov: BLE 配网启动, 等待 App 连接...
ble_prov: BLE 广播名=PROV_InkPulse PoP=inkpulse 超时=180s
```

- [ ] **Step 3: 官方 App 配网**

手机装 Espressif **ESP BLE Provisioning**（App Store / 应用商店）。打开 → Provision New Device → 扫描/选择 `PROV_InkPulse` → 输 PoP `inkpulse` → 选 WiFi `Xiaomi 15` 填密码 → 提交。期望日志：
```
ble_prov: 收到凭据 SSID=Xiaomi 15
ble_prov: 凭据已存 NVS (ssid=Xiaomi 15)
ble_prov: BLE 配网成功
inkpulse: BLE 配网成功, 重启走 STA
```
重启后连 WiFi → 拉帧 → 屏显仪表盘。

- [ ] **Step 4: 验证 SoftAP 兜底**

清凭据重来：`cd software/firmware && PORT=/dev/ttyACM0 ./build.sh erase-flash` 后重新 `flash`（或在 App 不配网的情况下等 180s）。BLE 阶段不配网，等 180s → 期望日志 `BLE 配网超时, 停止并回退 SoftAP` → `回退 SoftAP 配网`，热点 `InkPulse-Setup` 出现，网页 192.168.4.1 配网仍可用。

- [ ] **Step 5: 颜色/拉帧最终确认**

配网成功后屏显 Hub 仪表盘，中文正常、温湿度随上报刷新。若红/黑反相，按现有 `EPD_RED_INVERT` 调（与本计划无关）。

---

## Task 5: 更新 README

**Files:**
- Modify: `software/firmware/README.md`

- [ ] **Step 1: 把「首次配网」一节改为 BLE 为主 + SoftAP 兜底**

将 README 中「## 首次配网（SoftAP）」整节替换为：
```markdown
## 首次配网（BLE 为主，SoftAP 兜底）

设备无 WiFi 凭据时优先进入 **BLE 配网**：

1. 手机装 Espressif **ESP BLE Provisioning**（App Store / 应用商店免费）
2. App → Provision New Device → 扫描/选择 **`PROV_InkPulse`**
3. 输入 PoP 口令 **`inkpulse`** → 选你的 WiFi、填密码 → 提交
4. 设备存凭据并重启 → 连 WiFi → 拉帧上屏

**SoftAP 兜底**：若 BLE 180s 内无人配网，自动开热点 **`InkPulse-Setup`**（密码 `inkpulse123`），浏览器开 `http://192.168.4.1` 填 WiFi 配网。

凭据存 NVS namespace `inkpulse`；`./build.sh erase-flash` 清空重新配网。
```

- [ ] **Step 2: Commit**

```bash
git add software/firmware/README.md
git commit -m "docs(fw): README 配网说明改为 BLE 为主 + SoftAP 兜底"
```

---

## 自检对照（spec → task）
- 配网状态机(BLE→超时→SoftAP) → Task 3 ✅
- 凭据统一写 NVS `inkpulse` → Task 2(save_creds) ✅
- BLE 细节(NimBLE/security1/PoP/广播名) → Task 2 + net_config 常量(Task 3) ✅
- 分区表 2MB + NimBLE 启用 → Task 1 ✅
- SoftAP 兜底复用现有网页 → Task 3(start_provision_ap 不动) ✅
- 屏幕保持白屏(不画配网文字) → 现有 main.c 配网分支 epd_clear, 不改 ✅
- 验证(编译≤2MB / App配网 / 兜底 / 拉帧) → Task 4 ✅
- README 更新 → Task 5 ✅
- 微信小程序 → 设计文档「未来增强」, 本计划不实现(YAGNI) ✅

**已知待 bring-up 微调：** BLE 结束后 SoftAP 起不来时在 `start_provision_ap` 首行补 `esp_wifi_stop()`；`WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BTDM` 宏名的 IDF 版本差异；首轮编译若组件名报错，确认 `wifi_provisioning`/`bt` 在 REQUIRES。
