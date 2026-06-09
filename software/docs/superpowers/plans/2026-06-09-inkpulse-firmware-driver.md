# InkPulse 固件 — UC8179 墨水屏驱动 Bring-up 计划（子系统②·阶段一）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
> **本计划需要真实硬件 + ESP-IDF 工具链**：每个"烧录/观察"步骤由具备设备的执行者在硬件上完成；本机无法替你刷屏。

**Goal:** 在 ESP32-S3 上写通 E075A42（UC8179，7.5" 800×480 三色 BWR）SPI 驱动——复位、初始化、写黑/红双 plane、全刷，并用一组测试图案（全白/全黑/全红/上下分屏/棋盘）确认显示正确、方向正确、颜色极性正确。

**Architecture:** 纯 ESP-IDF C 工程。`epd_uc8179` 模块封装 SPI/GPIO HAL + UC8179 命令序列；`main.c` 跑测试图案并打印 BUSY 时序日志。此阶段**不联网**（WiFi/HTTP/离线缓存属阶段二，驱动通了再加）。

**Tech Stack:** ESP-IDF v5.x、ESP32-S3、SPI Master、FreeRTOS。

**引脚映射（已从原理图 net label + 引脚坐标逐行对齐确认）：**

| 信号 | 网络名 | ESP32-S3 GPIO | 方向 |
|---|---|---|---|
| SPI CLK | SCL | **GPIO41** | 输出 |
| SPI MOSI | SDA | **GPIO42** | 输出 |
| 片选 CS | CSB | **GPIO40** | 输出 |
| 命令/数据 D/C | DC | **GPIO39** | 输出 |
| 复位 RST | RES | **GPIO38** | 输出 |
| 忙 BUSY_N | BUSY | **GPIO37** | 输入(低=忙) |

> HTU21D 在 GPIO2(SCL)/GPIO1(SDA)，本阶段不涉及。GDR/RESE 接板载升压 MOSFET，固件不直接控制（芯片内部时序驱动）。

**UC8179 关键事实（来自 E075A42 规格书命令表）：**
- 命令码：PSR=0x00, PWR=0x01, POF=0x02, PON=0x04, BTST=0x06, DSLP=0x07, DTM1=0x10, DSP=0x11, DRF=0x12, DTM2=0x13, PLL=0x30, CDI=0x50, TCON=0x60, TRES=0x61, VDCS=0x82
- 分辨率：HRES=0x0320(800), VRES=0x01E0(480) → TRES 数据 `03 20 01 E0`
- BWR 模式 + OTP 内置 LUT：PSR=0x0F（REG=0 用 OTP LUT、KW/R=0 三色、booster on）
- **BUSY_N 低有效**：PON/DRF 期间为低，就绪/完成后回高 → 固件等 BUSY==1
- 每帧：DTM1(0x10) 写 B/W plane → DTM2(0x13) 写 RED plane → DRF(0x12) 刷新（约 15~30s）
- **极性（按 UC8179 7.5"BWR 通行约定，bring-up 验证）**：发给 0x10 的字节 `1=白 0=黑`；发给 0x13 的字节 `1=红 0=不红`。清屏=白：0x10←0xFF、0x13←0x00。

最终文件结构：
```
software/firmware/
  CMakeLists.txt
  sdkconfig.defaults
  main/
    CMakeLists.txt
    pins.h
    epd_uc8179.h
    epd_uc8179.c
    main.c
```

---

## Task 0: 前置——ESP-IDF 工具链与工程骨架

**Files:**
- Create: `software/firmware/CMakeLists.txt`
- Create: `software/firmware/sdkconfig.defaults`
- Create: `software/firmware/main/CMakeLists.txt`
- Create: `software/firmware/main/main.c`（临时 hello，占位）

- [ ] **Step 1: 确认 ESP-IDF 已安装（用户动作，规范禁止自动装工具链）**

本机检测：`idf.py` 不在 PATH、`IDF_PATH` 未设置。请按官方方式安装 ESP-IDF v5.x（不要用 brew 装编译链）：
```bash
mkdir -p ~/esp && cd ~/esp
git clone -b v5.2.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32s3
# 每次开发前：
. ~/esp/esp-idf/export.sh
```
确认：`idf.py --version` 能输出版本号后再继续。

- [ ] **Step 2: 写顶层 `CMakeLists.txt`**

```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(inkpulse_firmware)
```

- [ ] **Step 3: 写 `sdkconfig.defaults`（最小化，日志波特率显式）**

```
CONFIG_ESP_CONSOLE_UART_DEFAULT=y
CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y
CONFIG_FREERTOS_HZ=1000
```

- [ ] **Step 4: 写 `main/CMakeLists.txt`**

```cmake
idf_component_register(SRCS "main.c" "epd_uc8179.c"
                       INCLUDE_DIRS ".")
```
> 注：`epd_uc8179.c` 在 Task 2 创建；本任务先只放 `main.c`，故本步先写：
```cmake
idf_component_register(SRCS "main.c"
                       INCLUDE_DIRS ".")
```

- [ ] **Step 5: 写占位 `main/main.c`**

```c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "inkpulse";

void app_main(void)
{
    ESP_LOGI(TAG, "InkPulse firmware boot OK");
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
```

- [ ] **Step 6: 设目标、编译**

Run: `cd software/firmware && idf.py set-target esp32s3 && idf.py build`
Expected: 编译成功，生成 `build/inkpulse_firmware.bin`。

- [ ] **Step 7: 烧录并看日志确认能跑**

Run: `idf.py -p <串口,如 /dev/cu.usbmodemXXXX> flash monitor`
Expected: 串口打印 `InkPulse firmware boot OK`。`Ctrl+]` 退出 monitor。

- [ ] **Step 8: Commit**

```bash
git add software/firmware/CMakeLists.txt software/firmware/sdkconfig.defaults software/firmware/main
git commit -m "chore(fw): ESP-IDF工程骨架(esp32s3)可启动"
```

---

## Task 1: 引脚定义

**Files:**
- Create: `software/firmware/main/pins.h`

- [ ] **Step 1: 写 `pins.h`**

```c
#pragma once
// E075A42 (UC8179) <-> ESP32-S3 引脚映射，来自原理图 net label 对齐确认
#define EPD_PIN_SCLK   41   // SCL
#define EPD_PIN_MOSI   42   // SDA
#define EPD_PIN_CS     40   // CSB
#define EPD_PIN_DC     39   // DC
#define EPD_PIN_RST    38   // RES
#define EPD_PIN_BUSY   37   // BUSY_N (低=忙)

#define EPD_WIDTH      800
#define EPD_HEIGHT     480
#define EPD_ROW_BYTES  (EPD_WIDTH / 8)        // 100
#define EPD_PLANE_BYTES (EPD_ROW_BYTES * EPD_HEIGHT) // 48000
```

- [ ] **Step 2: Commit**

```bash
git add software/firmware/main/pins.h
git commit -m "feat(fw): 引脚与分辨率定义"
```

---

## Task 2: EPD HAL（SPI/GPIO + 命令/数据原语 + 复位 + 忙等待）

**Files:**
- Create: `software/firmware/main/epd_uc8179.h`
- Create: `software/firmware/main/epd_uc8179.c`
- Modify: `software/firmware/main/CMakeLists.txt`（把 `epd_uc8179.c` 加入 SRCS）

- [ ] **Step 1: 写头文件 `epd_uc8179.h`**

```c
#pragma once
#include <stdint.h>
#include <stddef.h>

void epd_hal_init(void);                 // 初始化 SPI + GPIO
void epd_reset(void);                    // 硬复位
void epd_send_cmd(uint8_t cmd);          // DC=0 发命令
void epd_send_data(uint8_t data);        // DC=1 发单字节
void epd_send_data_buf(const uint8_t *buf, size_t len); // DC=1 发缓冲
void epd_wait_busy(void);                // 等 BUSY_N 回高(空闲)

void epd_init(void);                     // UC8179 初始化序列
void epd_fill_plane(uint8_t cmd, uint8_t value); // 用常量填满一个 plane(48000B)
void epd_refresh(void);                  // DRF + 等忙
void epd_clear(void);                    // 清成白
void epd_sleep(void);                    // 深睡
```

- [ ] **Step 2: 写实现 `epd_uc8179.c`（HAL 部分）**

```c
#include "epd_uc8179.h"
#include "pins.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "epd";
static spi_device_handle_t s_spi;

void epd_hal_init(void)
{
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << EPD_PIN_DC) | (1ULL << EPD_PIN_RST),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&out);

    gpio_config_t in = {
        .pin_bit_mask = (1ULL << EPD_PIN_BUSY),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&in);

    spi_bus_config_t bus = {
        .mosi_io_num = EPD_PIN_MOSI,
        .miso_io_num = -1,
        .sclk_io_num = EPD_PIN_SCLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 4096,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));

    spi_device_interface_config_t dev = {
        .clock_speed_hz = 10 * 1000 * 1000, // 10MHz
        .mode = 0,                          // CPOL=0 CPHA=0
        .spics_io_num = EPD_PIN_CS,
        .queue_size = 4,
    };
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev, &s_spi));
    ESP_LOGI(TAG, "HAL init done");
}

static void spi_tx(const uint8_t *data, size_t len)
{
    spi_transaction_t t = { .length = len * 8, .tx_buffer = data };
    ESP_ERROR_CHECK(spi_device_polling_transmit(s_spi, &t));
}

void epd_send_cmd(uint8_t cmd)
{
    gpio_set_level(EPD_PIN_DC, 0);
    spi_tx(&cmd, 1);
}

void epd_send_data(uint8_t data)
{
    gpio_set_level(EPD_PIN_DC, 1);
    spi_tx(&data, 1);
}

void epd_send_data_buf(const uint8_t *buf, size_t len)
{
    gpio_set_level(EPD_PIN_DC, 1);
    size_t off = 0;
    while (off < len) {
        size_t chunk = (len - off > 4096) ? 4096 : (len - off);
        spi_tx(buf + off, chunk);
        off += chunk;
    }
}

void epd_reset(void)
{
    gpio_set_level(EPD_PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(EPD_PIN_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(EPD_PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
}

void epd_wait_busy(void)
{
    // BUSY_N: 低=忙, 高=空闲。等到高电平。
    ESP_LOGI(TAG, "wait busy...");
    int waited = 0;
    while (gpio_get_level(EPD_PIN_BUSY) == 0) {
        vTaskDelay(pdMS_TO_TICKS(50));
        waited += 50;
        if (waited % 2000 == 0) {
            ESP_LOGI(TAG, "  still busy %dms", waited);
        }
        if (waited > 40000) {
            ESP_LOGW(TAG, "  busy timeout(40s) — 检查复位/电源/引脚");
            break;
        }
    }
    ESP_LOGI(TAG, "busy released after %dms", waited);
}
```

- [ ] **Step 3: 把 `epd_uc8179.c` 加入 `main/CMakeLists.txt`**

```cmake
idf_component_register(SRCS "main.c" "epd_uc8179.c"
                       INCLUDE_DIRS ".")
```

- [ ] **Step 4: 临时验证 HAL（改 `main.c` 调 reset + 读 BUSY 一次）**

把 `main.c` 的 `app_main` 改为：
```c
#include "epd_uc8179.h"
#include "pins.h"
#include "driver/gpio.h"
// ...保留头文件...
void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    epd_hal_init();
    epd_reset();
    ESP_LOGI(TAG, "BUSY level after reset = %d", gpio_get_level(EPD_PIN_BUSY));
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
```

- [ ] **Step 5: 编译+烧录+观察**

Run: `idf.py build flash monitor`
Expected: 打印 `HAL init done`、`BUSY level after reset = 1`（复位后空闲应为高）。若为 0 或报 SPI 错，先排引脚/接线。

- [ ] **Step 6: Commit**

```bash
git add software/firmware/main/epd_uc8179.h software/firmware/main/epd_uc8179.c software/firmware/main/CMakeLists.txt software/firmware/main/main.c
git commit -m "feat(fw): EPD HAL(SPI/GPIO/复位/忙等待)"
```

---

## Task 3: UC8179 初始化序列

**Files:**
- Modify: `software/firmware/main/epd_uc8179.c`（追加 `epd_init`）

- [ ] **Step 1: 在 `epd_uc8179.c` 末尾追加 `epd_init`**

```c
void epd_init(void)
{
    epd_reset();

    // PWR: 电源设置(内部DC/DC, VGH/VGL=±20V, VDH/VDL=±15V) — UC8179 7.5BWR 通行值
    epd_send_cmd(0x01);
    epd_send_data(0x07); epd_send_data(0x07);
    epd_send_data(0x3f); epd_send_data(0x3f);

    epd_send_cmd(0x04);   // PON 上电
    vTaskDelay(pdMS_TO_TICKS(100));
    epd_wait_busy();

    epd_send_cmd(0x00); epd_send_data(0x0F);   // PSR: BWR + OTP LUT, booster on

    epd_send_cmd(0x61);                          // TRES 分辨率 800x480
    epd_send_data(0x03); epd_send_data(0x20);
    epd_send_data(0x01); epd_send_data(0xE0);

    epd_send_cmd(0x15); epd_send_data(0x00);     // DUSPI 单SPI

    epd_send_cmd(0x50); epd_send_data(0x11); epd_send_data(0x07); // CDI VCOM/数据间隔

    epd_send_cmd(0x60); epd_send_data(0x22);     // TCON

    ESP_LOGI(TAG, "epd_init done");
}

void epd_fill_plane(uint8_t cmd, uint8_t value)
{
    static uint8_t row[EPD_ROW_BYTES];
    memset(row, value, sizeof(row));
    epd_send_cmd(cmd);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        epd_send_data_buf(row, sizeof(row));
    }
}

void epd_refresh(void)
{
    epd_send_cmd(0x12);   // DRF
    vTaskDelay(pdMS_TO_TICKS(100));
    epd_wait_busy();
}

void epd_clear(void)
{
    epd_fill_plane(0x10, 0xFF);  // B/W plane = 全白
    epd_fill_plane(0x13, 0x00);  // RED plane = 无红
    epd_refresh();
}

void epd_sleep(void)
{
    epd_send_cmd(0x02);   // POF
    epd_wait_busy();
    epd_send_cmd(0x07); epd_send_data(0xA5);  // DSLP
}
```

- [ ] **Step 2: 编译确认无语法错误**

Run: `cd software/firmware && idf.py build`
Expected: 编译通过。

- [ ] **Step 3: Commit**

```bash
git add software/firmware/main/epd_uc8179.c
git commit -m "feat(fw): UC8179初始化序列+填充/刷新/清屏/深睡"
```

---

## Task 4: 首次点亮——清屏（最关键里程碑）

**Files:**
- Modify: `software/firmware/main/main.c`

- [ ] **Step 1: 改 `main.c` 跑 init + clear**

```c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "epd_uc8179.h"

static const char *TAG = "inkpulse";

void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    epd_hal_init();
    epd_init();
    ESP_LOGI(TAG, "clearing to white...");
    epd_clear();
    ESP_LOGI(TAG, "clear done");
    epd_sleep();
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
```

- [ ] **Step 2: 编译+烧录+观察屏幕**

Run: `idf.py build flash monitor`
Expected:
- 日志依次出现 `epd_init done` → `wait busy` → `busy released` → `clear done`
- **屏幕完成一次全刷（闪烁后变纯白/干净）**——这是驱动通的标志

- [ ] **Step 3: 若不动/超时——bring-up 排查（按序试）**

1. `busy timeout`：BUSY 引脚不对或没接 → 复查 GPIO37 接线
2. 屏无反应但 BUSY 正常释放：PWR 值偏弱 → 把 `0x3f,0x3f` 改 `0x3a,0x3a`(±14V) 或反之；或 PON 后 delay 加大
3. 整屏花/残影：属正常首刷，可连刷两次 `epd_clear()`
4. 完全黑屏：可能 PSR 极性/模式不对，确认 `0x00→0x0F`

- [ ] **Step 4: Commit（清屏通过后）**

```bash
git add software/firmware/main/main.c
git commit -m "feat(fw): 首次点亮——init+清屏全刷成功"
```

---

## Task 5: 测试图案——验证颜色极性与方向

**Files:**
- Modify: `software/firmware/main/epd_uc8179.c`（加 `epd_test_patterns` 与按行生成）
- Modify: `software/firmware/main/epd_uc8179.h`（声明）
- Modify: `software/firmware/main/main.c`（调用）

- [ ] **Step 1: 头文件加声明**

在 `epd_uc8179.h` 加：
```c
void epd_show_solid(uint8_t bw_val, uint8_t red_val); // 纯色:两plane常量
void epd_show_split(void);     // 上半黑 下半红
void epd_show_checker(void);   // 棋盘(黑/白) 验证方向与寻址
```

- [ ] **Step 2: `epd_uc8179.c` 追加实现**

```c
void epd_show_solid(uint8_t bw_val, uint8_t red_val)
{
    epd_fill_plane(0x10, bw_val);
    epd_fill_plane(0x13, red_val);
    epd_refresh();
}

void epd_show_split(void)
{
    static uint8_t row[EPD_ROW_BYTES];
    // B/W plane: 上半黑(0x00) 下半白(0xFF)
    epd_send_cmd(0x10);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        memset(row, (y < EPD_HEIGHT / 2) ? 0x00 : 0xFF, sizeof(row));
        epd_send_data_buf(row, sizeof(row));
    }
    // RED plane: 上半不红(0x00) 下半红(0xFF)
    epd_send_cmd(0x13);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        memset(row, (y < EPD_HEIGHT / 2) ? 0x00 : 0xFF, sizeof(row));
        epd_send_data_buf(row, sizeof(row));
    }
    epd_refresh();
}

void epd_show_checker(void)
{
    static uint8_t row[EPD_ROW_BYTES];
    epd_send_cmd(0x10);  // 64px 方格: 行带与列带异或
    for (int y = 0; y < EPD_HEIGHT; y++) {
        uint8_t band = (y / 64) & 1;
        for (int xb = 0; xb < EPD_ROW_BYTES; xb++) {
            uint8_t col = ((xb * 8) / 64) & 1;
            row[xb] = (band ^ col) ? 0x00 : 0xFF;  // 黑/白交替
        }
        epd_send_data_buf(row, sizeof(row));
    }
    epd_fill_plane(0x13, 0x00);  // 无红
    epd_refresh();
}
```

- [ ] **Step 3: `main.c` 依次跑图案（每个之间留观察时间）**

```c
void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    epd_hal_init();
    epd_init();

    ESP_LOGI(TAG, "1/5 白"); epd_show_solid(0xFF, 0x00); vTaskDelay(pdMS_TO_TICKS(3000));
    ESP_LOGI(TAG, "2/5 黑"); epd_show_solid(0x00, 0x00); vTaskDelay(pdMS_TO_TICKS(3000));
    ESP_LOGI(TAG, "3/5 红"); epd_show_solid(0xFF, 0xFF); vTaskDelay(pdMS_TO_TICKS(3000));
    ESP_LOGI(TAG, "4/5 上黑下红"); epd_show_split(); vTaskDelay(pdMS_TO_TICKS(3000));
    ESP_LOGI(TAG, "5/5 棋盘"); epd_show_checker(); vTaskDelay(pdMS_TO_TICKS(3000));

    ESP_LOGI(TAG, "patterns done");
    epd_sleep();
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
```

- [ ] **Step 4: 编译+烧录+逐图案核对**

Run: `idf.py build flash monitor`
Expected（逐一核对，记录实际现象）：
- 白 → 纯白
- 黑 → 纯黑
- **红 → 纯红**（若显示成白，则红极性相反 → 把"红"用 `epd_show_solid(0xFF, 0x?)` 的 red_val 改 0x00 之外验证，并在 `epd_clear`/驱动里统一红极性）
- 上黑下红 → 上半黑、下半红（确认左上为原点、行方向正确）
- 棋盘 → 64px 黑白方格无错位（确认 X 字节序/行字节数 100 正确、无横向偏移或撕裂）

- [ ] **Step 5: 记录极性/方向结论到代码注释**

把核对结论（红极性是否需反、原点/扫描方向是否需调 PSR 的 UD/SHL 位）写进 `epd_uc8179.c` 顶部注释，供阶段二（接 Hub 位图）对齐 `/frame` 的 plane 极性。

- [ ] **Step 6: Commit**

```bash
git add software/firmware/main
git commit -m "feat(fw): 测试图案验证颜色极性与显示方向"
```

---

## 自检对照（目标 → task）

- 引脚映射落地 → Task 1 ✅
- SPI/GPIO/复位/忙等待 HAL → Task 2 ✅
- UC8179 初始化序列(命令码/分辨率/PSR=0x0F) → Task 3 ✅
- 首次点亮(清屏全刷) → Task 4 ✅（核心里程碑）
- 颜色极性(红)/原点/方向验证 → Task 5 ✅
- BUSY 时序可观测(日志) → Task 2/4 ✅

**本计划交付物：** 一块能被正确驱动、可显示黑/白/红任意图案的屏。

**已知 bring-up 变量（在 Task 4/5 现场确定）：**
- PWR 电压档（`0x3f`±15V vs `0x3a`±14V）
- 红 plane 极性（0x13 的 `1=红` vs `1=不红`）—— 决定阶段二 `/frame` 红 plane 是否需取反
- 扫描方向（PSR 的 UD/SHL）—— 若上下/左右镜像则调
- 首刷残影 → 是否需连刷两次

**阶段二（驱动通后、另立计划/任务）：** WiFi STA + NVS + SoftAP 配网 + `esp_http_client` 拉 `/frame`(If-None-Match/ETag) + 离线缓存上一帧 + 把 `/frame` 双 plane 按本阶段确定的极性写入 0x10/0x13 + HTU21D 读数随请求上报 + `X-Next-Refresh` 节拍。对接计划① 已定的 `/frame` 二进制契约。
