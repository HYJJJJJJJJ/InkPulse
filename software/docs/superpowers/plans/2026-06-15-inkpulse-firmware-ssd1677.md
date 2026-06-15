# InkPulse 固件 SSD1677(4.2″ BW)驱动实现计划(Plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在固件里新增 SSD1677(4.2″ 480×800 BW)屏驱动,与现有 UC8179(7.5″ BWR)并存,编译期 Kconfig 选屏;设备在 `GET /frame` 上报 `&panel=<id>`,与 Plan A 的 hub 多 profile 对接。

**Architecture:** `display_if_t` 接口已抽象;新增 `ssd1677.c` 实现它(`show`=写 0x24 RAM,`refresh`=0x22/0x20),caps 报 `{480,800,DISP_BW,"bw-1plane",48000}`。`display_caps_t` 增加 `panel_id` 字段,各驱动自报("bwr_750"/"bw_426"),channel 据此拼 `&panel=`。`main.c` 按 `CONFIG_PANEL_*` 选驱动 + BW 版 `mark_offline`。

**Tech Stack:** ESP-IDF v5.4.1(C)、SPI(`ip_hal/spi_bus`)、Kconfig。

**关键约束 — 验证边界:**
- **可自动化**:`idf.py build` 编译两种 panel 变体均通过(无硬件)。
- **必须真机**:旋转方向、BW bit 极性、升压参数、局部刷新效果 —— 需把物理 4.2″ 屏接到板上跑 `INKPULSE_VERIFY` selftest 观察。这些是 bring-up 校准,本计划写出可调的代码 + 校准清单,但不能在无硬件环境判定通过。

**构建命令(source IDF 后):**
```bash
. ~/esp/v5.4.1/esp-idf/export.sh
cd /home/zqx/workspace/InkPulse/software/firmware
idf.py set-target esp32s3      # 仅首次
idf.py build                   # 默认 = UC8179(bwr_750)
```
切到 SSD1677 变体见 Task 7。

---

## 文件结构

- **改** `components/ip_display/include/ip_display/display.h` — `display_caps_t` 增加 `const char *panel_id`。
- **改** `components/ip_display/src/uc8179.c` — `disp_get_caps` 设 `panel_id="bwr_750"`。
- **改** `components/ip_channel/src/http_hub.c` — 保存 `s_panel_id`,`ch_fetch` URL 追加 `&panel=`。
- **新建** `main/Kconfig.projbuild` — `choice INKPULSE_PANEL`。
- **新建** `components/ip_display/src/ssd1677_internal.h`
- **新建** `components/ip_display/src/ssd1677.c` — 驱动实现。
- **新建** `components/ip_display/src/ssd1677_selftest.c` — bring-up 图案。
- **改** `components/ip_display/CMakeLists.txt` — 加入新源文件。
- **改** `main/main.c` — Kconfig 选驱动 + BW `mark_offline`。

向后兼容:默认 Kconfig 选 UC8179,`panel_id="bwr_750"`;现役行为不变。

---

## Task 1: display_caps_t 增加 panel_id,UC8179 自报

**Files:** Modify `components/ip_display/include/ip_display/display.h`, `components/ip_display/src/uc8179.c`

- [ ] **Step 1: 改 display.h** —— 在 `display_caps_t` 末尾加字段:
```c
typedef struct {
    uint16_t width, height;
    disp_color_model_t color_model;
    const char *frame_format;   // 如 "bwr-dualplane"
    size_t frame_bytes;
    const char *panel_id;       // 上报给 hub 的 profile id, 如 "bwr_750"/"bw_426"; 可空
} display_caps_t;
```

- [ ] **Step 2: 改 uc8179.c 的 `disp_get_caps`** —— 加一行:
```c
static void disp_get_caps(display_caps_t *out)
{
    out->width       = 800;
    out->height      = 480;
    out->color_model = DISP_BWR;
    out->frame_format = "bwr-dualplane";
    out->frame_bytes  = 96000;
    out->panel_id     = "bwr_750";
}
```

- [ ] **Step 3: 编译验证**
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware && idf.py build 2>&1 | tail -15
```
Expected: `Project build complete.`(新增字段不破坏现有代码)

- [ ] **Step 4: 提交**
```bash
cd /home/zqx/workspace/InkPulse && export PATH="$HOME/.local/bin:$PATH" && git add software/firmware/components/ip_display && git commit -m "feat(fw/display): display_caps_t 增加 panel_id, UC8179 报 bwr_750"
```

---

## Task 2: channel 上报 &panel=

**Files:** Modify `components/ip_channel/src/http_hub.c`

- [ ] **Step 1: 保存 panel_id** —— 在 `static size_t s_frame_bytes = 96000;` 附近加:
```c
static char s_panel_id[24] = "";   // ch_init 时从 caps 取
```
在 `ch_init` 里,`s_frame_bytes = caps->frame_bytes;` 之后加:
```c
        if (caps->panel_id && caps->panel_id[0]) {
            strlcpy(s_panel_id, caps->panel_id, sizeof(s_panel_id));
        }
```

- [ ] **Step 2: URL 追加 &panel=** —— 在 `ch_fetch` 里,把构造 URL 的那段改为:
```c
    char panel_q[40] = "";
    if (s_panel_id[0]) {
        snprintf(panel_q, sizeof(panel_q), "&panel=%s", s_panel_id);
    }
    char url[256];
    snprintf(url, sizeof(url), "%s/frame?t=%.1f&h=%.1f%s%s", s_base, t, h, rssi_q, panel_q);
```
(保持 rssi_q 逻辑不变,只是末尾多拼 panel_q。)

- [ ] **Step 3: 编译验证**
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware && idf.py build 2>&1 | tail -8
```
Expected: build complete。当前默认 UC8179 → URL 带 `&panel=bwr_750`(hub 也会回退同款,行为不变)。

- [ ] **Step 4: 提交**
```bash
cd /home/zqx/workspace/InkPulse && export PATH="$HOME/.local/bin:$PATH" && git add software/firmware/components/ip_channel && git commit -m "feat(fw/channel): GET /frame 追加 &panel= 上报面板 id"
```

---

## Task 3: Kconfig 选屏

**Files:** Create `main/Kconfig.projbuild`

- [ ] **Step 1: 新建 `main/Kconfig.projbuild`**
```kconfig
menu "InkPulse Panel"

choice INKPULSE_PANEL
    prompt "EPD panel"
    default PANEL_UC8179_BWR_750
    help
        选择物理墨水屏型号(编译期固定, 一块板只焊一块屏)。

    config PANEL_UC8179_BWR_750
        bool "7.5\" 800x480 BWR (UC8179)"

    config PANEL_SSD1677_BW_426
        bool "4.2\" 480x800 BW partial-refresh (SSD1677)"
endchoice

endmenu
```

- [ ] **Step 2: 编译验证(默认仍 UC8179)**
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware && idf.py build 2>&1 | tail -8
```
Expected: build complete;`sdkconfig` 出现 `CONFIG_PANEL_UC8179_BWR_750=y`(可 `grep PANEL sdkconfig` 确认)。

- [ ] **Step 3: 提交**
```bash
cd /home/zqx/workspace/InkPulse && export PATH="$HOME/.local/bin:$PATH" && git add software/firmware/main/Kconfig.projbuild && git commit -m "feat(fw): Kconfig 选屏 choice(UC8179/SSD1677)"
```

---

## Task 4: SSD1677 驱动

**Files:** Create `components/ip_display/src/ssd1677_internal.h`, `components/ip_display/src/ssd1677.c`; Modify `components/ip_display/CMakeLists.txt`

> 设计要点:
> - caps = `{480, 800, DISP_BW, "bw-1plane", 48000, "bw_426"}`。
> - hub 发来的是 **已旋转的 800×480 单 plane**(100 字节/行 × 480 行,bit=1=黑)。SSD1677 `0x24` RAM 的 X=源(800)、Y=栅(480),与之直接对应。
> - **BW 极性**:SSD1677 `0x24` 常约定 1=白/0=黑,而 hub bit=1=黑,故默认发 `~byte`(`EPD_BW_INVERT=1`),真机不对则改 0。
> - 初始化序列照规格书 p35 OTP 参考码。

- [ ] **Step 1: 新建 `components/ip_display/src/ssd1677_internal.h`**
```c
#pragma once
// ssd1677 内部共享声明 —— 不进 public include/
#include <stdint.h>
#include <stddef.h>

#define SSD_WIDTH       800     // 控制器 RAM 源方向(hub 旋转后宽)
#define SSD_HEIGHT      480     // 控制器 RAM 栅方向
#define SSD_ROW_BYTES   (SSD_WIDTH / 8)               // 100
#define SSD_PLANE_BYTES (SSD_ROW_BYTES * SSD_HEIGHT)   // 48000

// 0x24 BW RAM: 1=白/0=黑(常约定)。hub bit=1=黑, 故默认取反发送。真机不对改 0。
#define SSD_BW_INVERT   1

// 暴露给 selftest 的内部辅助
void ssd1677_write_ram(const uint8_t *plane);   // 写 0x24 整屏(48000B, 已按极性处理)
void ssd1677_update_full(void);                  // 0x22(0xF7)+0x20 全刷 + 等忙
```

- [ ] **Step 2: 新建 `components/ip_display/src/ssd1677.c`**
```c
// SSD1677 4.2" 480x800 BW 驱动实现
// caps 报逻辑竖屏 480x800; hub 渲染 480x800 -> 旋转90 -> 800x480 单plane(bit=1=黑) 发来。
// 控制器 RAM: X=源(800), Y=栅(480), 0x24 写 48000B。
// 极性: 0x24 约定 1=白0=黑, 与 hub(1=黑) 相反, 默认 SSD_BW_INVERT=1 取反。真机校准。
#include "ip_display/display.h"
#include "ssd1677_internal.h"
#include "ip_hal/spi_bus.h"
#include "ip_hal/board_pins.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include <string.h>

static const char *TAG = "ssd1677";

static void wait_busy(void)
{
    // SSD1677 BUSY: 高=忙(规格书 5-4)。等到低电平。
    // 注: hal_spi_busy_level() 读原始电平。本驱动等其变 0(空闲)。
    int waited = 0;
    while (hal_spi_busy_level() == 1) {
        vTaskDelay(pdMS_TO_TICKS(20));
        waited += 20;
        if (waited > 35000) { ESP_LOGW(TAG, "busy 35s 超时"); break; }
    }
}

// 上电 + 寄存器初始化(规格书 p35 OTP 参考码)
static void ssd1677_panel_init(void)
{
    hal_spi_reset();

    hal_spi_cmd(0x12);              // SWRESET
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();

    hal_spi_cmd(0x0C);             // 升压软启动
    hal_spi_data(0xAE); hal_spi_data(0xC7); hal_spi_data(0xC3);
    hal_spi_data(0xC0); hal_spi_data(0x80);

    hal_spi_cmd(0x01);             // 驱动输出控制: 480 行
    hal_spi_data(0xDF); hal_spi_data(0x01); hal_spi_data(0x02);

    hal_spi_cmd(0x11); hal_spi_data(0x01);   // 数据进入模式

    hal_spi_cmd(0x44);             // RAM X: 0..799
    hal_spi_data(0x00); hal_spi_data(0x00);
    hal_spi_data(0x1F); hal_spi_data(0x03);

    hal_spi_cmd(0x45);             // RAM Y: 479..0
    hal_spi_data(0xDF); hal_spi_data(0x01);
    hal_spi_data(0x00); hal_spi_data(0x00);

    hal_spi_cmd(0x3C); hal_spi_data(0x01);   // 边框
    hal_spi_cmd(0x18); hal_spi_data(0x80);   // 内置温度传感器

    ESP_LOGI(TAG, "panel init done");
}

static void set_ram_counter(void)
{
    hal_spi_cmd(0x4E); hal_spi_data(0x00); hal_spi_data(0x00);   // X counter=0
    hal_spi_cmd(0x4F); hal_spi_data(0xDF); hal_spi_data(0x01);   // Y counter=479
}

// 写 0x24 整屏(按极性处理)。供 show / selftest 用。
void ssd1677_write_ram(const uint8_t *plane)
{
    set_ram_counter();
    hal_spi_cmd(0x24);
    static uint8_t tmp[SSD_ROW_BYTES];
    for (int y = 0; y < SSD_HEIGHT; y++) {
        const uint8_t *src = plane + y * SSD_ROW_BYTES;
#if SSD_BW_INVERT
        for (int i = 0; i < SSD_ROW_BYTES; i++) tmp[i] = (uint8_t)~src[i];
        hal_spi_data_buf(tmp, SSD_ROW_BYTES);
#else
        hal_spi_data_buf(src, SSD_ROW_BYTES);
#endif
    }
}

// 全刷
void ssd1677_update_full(void)
{
    hal_spi_cmd(0x22); hal_spi_data(0xF7);
    hal_spi_cmd(0x20);
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();
}

// ---- display_if_t ----
static esp_err_t disp_init(void)
{
    esp_err_t ret = hal_spi_init(EPD_PIN_MOSI, EPD_PIN_SCLK, EPD_PIN_CS,
                                 EPD_PIN_DC, EPD_PIN_RST, EPD_PIN_BUSY);
    if (ret != ESP_OK) { ESP_LOGE(TAG, "spi init: %s", esp_err_to_name(ret)); return ret; }
    ssd1677_panel_init();
    return ESP_OK;
}

static void disp_get_caps(display_caps_t *out)
{
    out->width        = 480;
    out->height       = 800;
    out->color_model  = DISP_BW;
    out->frame_format = "bw-1plane";
    out->frame_bytes  = 48000;
    out->panel_id     = "bw_426";
}

static esp_err_t disp_show(const uint8_t *frame, size_t len)
{
    if (len < SSD_PLANE_BYTES) {
        ESP_LOGE(TAG, "frame too short: %u < %u", (unsigned)len, SSD_PLANE_BYTES);
        return ESP_ERR_INVALID_ARG;
    }
    ssd1677_write_ram(frame);
    return ESP_OK;
}

static void disp_refresh(void) { ssd1677_update_full(); }

static void disp_clear(void)
{
    static uint8_t white[SSD_ROW_BYTES];
    memset(white, 0x00, sizeof(white));   // hub 约定 bit=1=黑 => 0x00=白
    set_ram_counter();
    hal_spi_cmd(0x24);
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_write_ram_row_white();
    // 注: 简洁起见直接整屏写 0x00(经极性取反=全白)。见下方 helper。
    ssd1677_update_full();
}

static void disp_sleep(void)
{
    hal_spi_cmd(0x10); hal_spi_data(0x01);   // 深睡
}

extern void ssd1677_selftest_run(void);

static const display_if_t s_if = {
    .init = disp_init, .get_caps = disp_get_caps, .show = disp_show,
    .refresh = disp_refresh, .clear = disp_clear, .sleep = disp_sleep,
    .selftest = ssd1677_selftest_run,
};

const display_if_t *ssd1677_driver(void) { return &s_if; }
```
> 实现者注意:上面 `disp_clear` 里我写了个不存在的 `ssd1677_write_ram_row_white()` 占位以示意——请改成正确写法:构造一块全 `0x00` 的 48000B 概念帧并走 `ssd1677_write_ram`。最简实现:
> ```c
> static void disp_clear(void)
> {
>     static uint8_t whole[SSD_PLANE_BYTES];
>     memset(whole, 0x00, sizeof(whole));   // bit=1=黑 约定下 0x00=全白
>     ssd1677_write_ram(whole);             // 注意: write_ram 会按 SSD_BW_INVERT 取反
>     ssd1677_update_full();
> }
> ```
> 若 `SSD_BW_INVERT=1`,`0x00` 取反成 `0xFF` 发给控制器(1=白)→ 全白,正确。`SSD_PLANE_BYTES`(48000B)的静态数组放 `.bss`,ESP32-S3 内存足够。

- [ ] **Step 3: 在 `ssd1677_driver()` 前声明,并加到 display.h** —— 在 `components/ip_display/include/ip_display/display.h` 末尾(`uc8179_driver` 声明旁)加:
```c
const display_if_t *ssd1677_driver(void);
```

- [ ] **Step 4: 改 `components/ip_display/CMakeLists.txt`** 加入新源(两驱动都编译,main 只引用其一):
```cmake
idf_component_register(
    SRCS "src/uc8179.c" "src/uc8179_selftest.c" "src/ssd1677.c" "src/ssd1677_selftest.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_hal ip_config
)
```
(Task 5 会创建 `ssd1677_selftest.c`;若想 Task 4 先单独编译,可暂时只加 `src/ssd1677.c` 并在本任务末尾把 selftest 占位为一个空函数,Task 5 再补全。推荐:先做 Task 5 再回来改 CMake,或在本步同时建一个最小 `ssd1677_selftest.c` 桩。)

- [ ] **Step 5: 编译验证默认变体仍 OK**(此时 main 仍调 uc8179)
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware && idf.py build 2>&1 | tail -15
```
Expected: build complete(新驱动被编译进来但未被 main 引用也应链接通过)。

- [ ] **Step 6: 提交**
```bash
cd /home/zqx/workspace/InkPulse && export PATH="$HOME/.local/bin:$PATH" && git add software/firmware/components/ip_display && git commit -m "feat(fw/display): SSD1677 BW 驱动(全刷) + caps bw_426"
```

---

## Task 5: SSD1677 selftest(bring-up 图案)

**Files:** Create `components/ip_display/src/ssd1677_selftest.c`

- [ ] **Step 1: 新建 `ssd1677_selftest.c`** —— 对标 `uc8179_selftest.c` 的结构,出几个可肉眼判读的图案(全白/全黑/竖条/棋盘),每个之间全刷:
```c
// SSD1677 bring-up selftest: 全白 / 全黑 / 竖条 / 棋盘, 用于真机校准极性与旋转。
#include "ssd1677_internal.h"
#include "ip_hal/spi_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "ssd1677_test";
static uint8_t s_plane[SSD_PLANE_BYTES];   // 概念帧: bit=1=黑(与 hub 同约定)

static void show(const char *name)
{
    ESP_LOGI(TAG, "图案: %s", name);
    ssd1677_write_ram(s_plane);
    ssd1677_update_full();
    vTaskDelay(pdMS_TO_TICKS(2000));
}

void ssd1677_selftest_run(void)
{
    memset(s_plane, 0x00, sizeof(s_plane)); show("全白");      // bit=0 => 白
    memset(s_plane, 0xFF, sizeof(s_plane)); show("全黑");      // bit=1 => 黑

    // 竖条: 每 16 像素黑白交替(判旋转方向/左右)
    for (int y = 0; y < SSD_HEIGHT; y++)
        for (int b = 0; b < SSD_ROW_BYTES; b++)
            s_plane[y*SSD_ROW_BYTES + b] = ((b/2) & 1) ? 0xFF : 0x00;
    show("竖条");

    // 棋盘
    for (int y = 0; y < SSD_HEIGHT; y++)
        for (int b = 0; b < SSD_ROW_BYTES; b++)
            s_plane[y*SSD_ROW_BYTES + b] = ((y/8 + b/2) & 1) ? 0xFF : 0x00;
    show("棋盘");

    ESP_LOGI(TAG, "selftest 结束");
}
```

- [ ] **Step 2: 确保 CMake 已含该源**(Task 4 Step 4 已加 `src/ssd1677_selftest.c`)。

- [ ] **Step 3: 编译验证**
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware && idf.py build 2>&1 | tail -10
```
Expected: build complete。

- [ ] **Step 4: 提交**
```bash
cd /home/zqx/workspace/InkPulse && export PATH="$HOME/.local/bin:$PATH" && git add software/firmware/components/ip_display && git commit -m "feat(fw/display): SSD1677 bring-up selftest 图案"
```

---

## Task 6: main.c 选驱动 + BW mark_offline

**Files:** Modify `main/main.c`

- [ ] **Step 1: 选驱动** —— 把两处 `const display_if_t *disp = uc8179_driver();`(INKPULSE_VERIFY 分支 + 主循环分支)改为:
```c
    const display_if_t *disp =
#if CONFIG_PANEL_SSD1677_BW_426
        ssd1677_driver();
#else
        uc8179_driver();
#endif
```
(`ssd1677_driver`/`uc8179_driver` 声明都在已 include 的 `ip_display/display.h`。)

- [ ] **Step 2: BW 版 mark_offline** —— 现有 `mark_offline` 往 red plane(`fb + frame_bytes/2`)写,BW 无红 plane。改为按颜色模型分支:BW 时在单 plane(800×480,bit=1=黑)右上角画黑色 X。把 `mark_offline` 整体替换为:
```c
// 离线叉: BWR 用红 plane 画红叉; BW 用单 plane 画黑叉。on=画, off=清。
static void mark_offline(uint8_t *fb, const display_caps_t *c, bool on)
{
    const int x0 = 766, y0 = 8, sz = 18;
    if (c->color_model == DISP_BW) {
        int rb = 800 / 8;                 // 旋转后单 plane 行字节(800/8=100)
        uint8_t *plane = fb;              // bit=1=黑
        for (int i = 0; i <= sz; i++) {
            for (int w = 0; w < 3; w++) {
                int yy = y0 + i;
                int xa = x0 + i + w, xb = x0 + sz - i + w;
                uint8_t ma = 0x80 >> (xa % 8), mb = 0x80 >> (xb % 8);
                if (on) { plane[yy*rb + xa/8] |= ma;  plane[yy*rb + xb/8] |= mb; }
                else    { plane[yy*rb + xa/8] &= ~ma; plane[yy*rb + xb/8] &= ~mb; }
            }
        }
        return;
    }
    int rb = c->width / 8;                 // BWR: row bytes (800/8=100)
    uint8_t *red = fb + c->frame_bytes / 2;
    for (int i = 0; i <= sz; i++) {
        for (int w = 0; w < 3; w++) {
            int yy = y0 + i;
            int xa = x0 + i + w, xb = x0 + sz - i + w;
            uint8_t ma = 0x80 >> (xa % 8), mb = 0x80 >> (xb % 8);
            if (on) { red[yy*rb + xa/8] |= ma;  red[yy*rb + xb/8] |= mb; }
            else    { red[yy*rb + xa/8] &= ~ma; red[yy*rb + xb/8] &= ~mb; }
        }
    }
}
```
> 注:BW 的叉位置(800×480 旋转后 RAM 坐标的右上角)与肉眼"竖屏右上"未必一致,属 bring-up 视觉校准,真机再微调坐标。

- [ ] **Step 3: 编译默认变体(UC8179)**
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware && idf.py build 2>&1 | tail -10
```
Expected: build complete。

- [ ] **Step 4: 提交**
```bash
cd /home/zqx/workspace/InkPulse && export PATH="$HOME/.local/bin:$PATH" && git add software/firmware/main/main.c && git commit -m "feat(fw): main 按 Kconfig 选驱动 + BW 版 mark_offline"
```

---

## Task 7: 两种 panel 变体均编译通过

**Files:** 无(仅验证)

- [ ] **Step 1: 默认(UC8179)已在前面验证。现验证 SSD1677 变体。** 用临时 sdkconfig 覆盖切换 panel,避免污染默认 sdkconfig:
```bash
. ~/esp/v5.4.1/esp-idf/export.sh && cd /home/zqx/workspace/InkPulse/software/firmware
echo 'CONFIG_PANEL_SSD1677_BW_426=y' > sdkconfig.ssd1677
SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ssd1677" idf.py -B build_ssd1677 build 2>&1 | tail -20
```
Expected: `Project build complete.`,且 `grep PANEL build_ssd1677/.../sdkconfig` 或 `idf.py -B build_ssd1677 confserver` 不便时直接 `grep CONFIG_PANEL build_ssd1677/sdkconfig` 显示 `CONFIG_PANEL_SSD1677_BW_426=y`。这一步确认 SSD1677 路径(驱动 + main 选择 + BW mark_offline)真的被编译且无错。

- [ ] **Step 2: 清理临时产物**(不提交 build 目录)
```bash
cd /home/zqx/workspace/InkPulse/software/firmware && rm -rf build_ssd1677 sdkconfig.ssd1677
```
确认 `software/firmware/.gitignore` 已忽略 `build*/` 与 `sdkconfig`(若没忽略 `build_ssd1677`/`sdkconfig.ssd1677`,本步删除即可;勿提交)。

- [ ] **Step 3: 默认 sdkconfig 仍是 UC8179** —— `grep CONFIG_PANEL sdkconfig` 应为 `CONFIG_PANEL_UC8179_BWR_750=y`。无需提交(本任务无源码改动)。

---

## Task 8: 真机 bring-up 校准清单(硬件,人工)

> 本任务**无法在无硬件环境判定通过**。把物理 4.2″ SSD1677 屏接到板(FPC pin-to-pin 兼容,见 spec 硬件节),按下列逐项校准,改对应宏/参数后重编烧录。

- [ ] **B1 烧录 selftest**:`idf.py -DINKPULSE_VERIFY=1`(+ SSD1677 sdkconfig)build flash monitor,运行 `ssd1677_selftest`。
- [ ] **B2 极性**:看"全白/全黑"是否正确。反了 → 改 `ssd1677_internal.h` 的 `SSD_BW_INVERT`(0↔1)重烧。
- [ ] **B3 旋转/镜像**:看"竖条/棋盘"方向。图像转了 90° → 改 hub `profiles.py` 的 `bw_426.rotate`(90↔270);左右/上下镜像 → 调 SSD1677 `0x11` 数据进入模式 + `0x44/0x45/0x4E/0x4F` 起止方向。
- [ ] **B4 升压/对比度**:残影重/偏淡 → 调 `0x0C` 软启动或确认 VCOM;必要时核对新屏参考电路升压电容(spec 硬件清单)。
- [ ] **B5 整链路**:去掉 `INKPULSE_VERIFY`,连 hub,确认 `GET /frame?...&panel=bw_426` 取到 48000B 帧并正确全刷;离线黑叉位置肉眼在右上角(否则微调 Task 6 坐标)。
- [ ] **B6 离线叉/按键/刷新令牌** 行为与 7.5″ 一致。

---

## (可选)Task 9: 局部刷新

> 规格书声明支持局刷。全刷链路(Task 1-8)稳定后再做。需:partial LUT/`0x22` 局刷参数 + 设置局刷窗口(`0x44/0x45` 子区)+ 仅写变化区。属增量优化,**真机校准为主**,在此不展开伪代码以免无依据。建议作为 Plan B 之后的独立小计划,基于 bring-up 后的实测波形参数编写。

---

## Self-Review(对照 spec 第 2 节)

- 编译期 Kconfig 选驱动 → Task 3/6 ✓
- ssd1677.c 实现 display_if_t + caps bw_426 → Task 4 ✓
- URL 追加 &panel= 上报(对接 hub Plan A)→ Task 1/2 ✓
- s_framebuf 尺寸:保持 96000(BW 仅用前 48000,过大无害)→ 无需改 main 缓冲 ✓
- BW mark_offline 黑叉 → Task 6 ✓
- ssd1677_selftest → Task 5 ✓
- 真机校准(旋转/极性/升压)→ Task 8 清单 ✓(硬件,人工)
- 占位符:Task 4 的 `disp_clear` 占位已在注记中给出正确实现,实现者须采用注记版本。

## 与 Plan A 的衔接

Plan A 已让 hub 对 `&panel=bw_426` 渲 480×800→旋转→48000B 单 plane(bit=1=黑)。Plan B 固件 caps 报 `bw_426`、channel 上报该 id、ssd1677 消费 48000B。旋转方向是 hub 侧 `profiles.bw_426.rotate` 单一旋钮,真机 B3 校准。
