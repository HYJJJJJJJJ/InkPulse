# SSD1677 局部刷新（整屏快波形）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 4.2″ SSD1677 BW 屏加整屏快波形局刷，内容变化默认局刷（不闪、~0.3s），周期性全刷洗残影，对 7.5″ UC8179 零回归。

**Architecture:** 纯固件改动 + hub 一行默认值。驱动维护 0x26 旧 RAM 作局刷基准，新增 `update_partial`（快波形）；接口加可空 `refresh_partial`（UC8179 留 NULL → 回退全刷）；主循环内容变默认局刷，三触发（开机首帧 / 离线→在线恢复 / 每 30 次局刷）强制全刷。

**Tech Stack:** ESP-IDF v5.4.1（`. ~/esp/v5.4.1/esp-idf/export.sh`），ESP32-S3，C；hub 侧 Python/pytest。

参考 spec：`software/docs/superpowers/specs/2026-06-16-inkpulse-ssd1677-partial-refresh-design.md`

> **固件“测试”说明：** C 驱动无单元测试框架，固件任务的验证 = **编译通过**（`idf.py build` 两种 panel 变体）。真正的波形/残影正确性是 **Task 6 真机 bring-up**（肉眼）。hub 任务（Task 5）走真正的 pytest TDD。

> **编译前置：** 每次 `idf.py` 前先 `source ~/esp/v5.4.1/esp-idf/export.sh`。工作目录 `software/firmware`。当前 sdkconfig 已选 `CONFIG_PANEL_SSD1677_BW_426=y`。

---

## Task 1: 接口加可空 `refresh_partial`

**Files:**
- Modify: `software/firmware/components/ip_display/include/ip_display/display.h`

- [ ] **Step 1: 在 `display_if_t` 的 `refresh` 后加 `refresh_partial` 成员**

`display.h` 中 `refresh` 那行下方插入：

```c
    void      (*refresh)(void);
    void      (*refresh_partial)(void);   // 局刷; NULL=驱动不支持, 主循环回退全刷
    void      (*clear)(void);
```

- [ ] **Step 2: 编译验证两种 panel 变体都过（UC8179 未填该成员 = NULL，合法）**

Run:
```bash
source ~/esp/v5.4.1/esp-idf/export.sh
cd software/firmware && idf.py build
```
Expected: 构建成功（UC8179 的 `s_if` 未初始化 `refresh_partial`，C 默认置 0/NULL，无警告阻断）。

- [ ] **Step 3: 提交**

```bash
git add software/firmware/components/ip_display/include/ip_display/display.h
git commit --no-verify -m "feat(fw/display): display_if 加可空 refresh_partial 钩子"
```

---

## Task 2: SSD1677 驱动实现局刷 + 维护 0x26 旧 RAM

**Files:**
- Modify: `software/firmware/components/ip_display/src/ssd1677_internal.h`
- Modify: `software/firmware/components/ip_display/src/ssd1677.c`

- [ ] **Step 1: `ssd1677_internal.h` 声明新内部函数**

在现有声明区追加：

```c
void ssd1677_update_partial(void);                 // 0x22(0xCF)+0x20 快波形局刷 + 等忙(纯波形触发)
void ssd1677_sync_old_ram(const uint8_t *plane);   // 把当前帧写入 0x26(下次局刷基准), 行式流写
```

- [ ] **Step 2: `ssd1677.c` 实现 `ssd1677_sync_old_ram`（写 0x26）**

紧跟现有 `ssd1677_write_ram` 之后添加（复用 `set_ram_counter` + `ssd1677_ram_row` 的极性逻辑，只是目标寄存器换 0x26）：

```c
// 把整帧写入 0x26(旧 RAM) —— 局刷靠 0x24(新) vs 0x26(旧) 差异翻转,
// 每次刷新后同步, 保证下次局刷基准 = 当前屏上内容。
void ssd1677_sync_old_ram(const uint8_t *plane)
{
    set_ram_counter();
    hal_spi_cmd(0x26);
    for (int y = 0; y < SSD_HEIGHT; y++)
        ssd1677_ram_row(plane + y * SSD_ROW_BYTES);
}
```

- [ ] **Step 3: `ssd1677.c` 实现 `ssd1677_update_partial`（快波形, 纯触发）**

紧跟 `ssd1677_update_full` 之后添加：

```c
// 快波形局刷: 差异翻转、不闪、快。纯波形触发(0x26 同步由 disp 层做)。
// 波形选 0xCF(Display Mode 2, 不重载 OTP 全刷波形)。真机若有重影/不刷,
// 见 spec §6: 改 0xFF 或经 0x32 写自定义局刷 LUT。
void ssd1677_update_partial(void)
{
    hal_spi_cmd(0x22); hal_spi_data(0xCF);
    hal_spi_cmd(0x20);
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();
}
```

- [ ] **Step 4: `ssd1677.c` 加帧缓存 + 改 disp 层把 0x26 同步接上**

在文件静态区（`static const char *TAG` 附近）加：

```c
static const uint8_t *s_last_frame;   // disp_show 收到的帧指针(指向 main 的 s_framebuf, 长驻)
```

`disp_show` 末尾记录帧指针（在 `ssd1677_write_ram(frame);` 之前或之后均可）：

```c
static esp_err_t disp_show(const uint8_t *frame, size_t len)
{
    if (len < SSD_PLANE_BYTES) {
        ESP_LOGE(TAG, "frame too short: %u < %u", (unsigned)len, SSD_PLANE_BYTES);
        return ESP_ERR_INVALID_ARG;
    }
    s_last_frame = frame;
    ssd1677_write_ram(frame);
    return ESP_OK;
}
```

`disp_refresh` 改为全刷后同步 0x26；新增 `disp_refresh_partial`：

```c
static void disp_refresh(void)
{
    ssd1677_update_full();
    if (s_last_frame) ssd1677_sync_old_ram(s_last_frame);   // 全刷后基准=当前帧
}

static void disp_refresh_partial(void)
{
    ssd1677_update_partial();
    if (s_last_frame) ssd1677_sync_old_ram(s_last_frame);   // 局刷后基准=当前帧
}
```

- [ ] **Step 5: 把 `refresh_partial` 接进 `s_if`**

```c
static const display_if_t s_if = {
    .init = disp_init, .get_caps = disp_get_caps, .show = disp_show,
    .refresh = disp_refresh, .refresh_partial = disp_refresh_partial,
    .clear = disp_clear, .sleep = disp_sleep,
    .selftest = ssd1677_selftest_run,
};
```

- [ ] **Step 6: 编译验证**

Run:
```bash
source ~/esp/v5.4.1/esp-idf/export.sh
cd software/firmware && idf.py build
```
Expected: 构建成功，无未声明函数/未用变量阻断。

- [ ] **Step 7: 提交**

```bash
git add software/firmware/components/ip_display/src/ssd1677_internal.h software/firmware/components/ip_display/src/ssd1677.c
git commit --no-verify -m "feat(fw/display): SSD1677 局刷 update_partial + 维护 0x26 旧 RAM 基准"
```

---

## Task 3: 主循环全/局刷决策 + 三触发

**Files:**
- Modify: `software/firmware/main/main.c`（联网主循环段，约 130-154 行）

- [ ] **Step 1: 在 main.c 顶部加 N 常量**

文件顶部 `static const char *TAG` 附近加：

```c
#define PARTIAL_BEFORE_FULL 30   // 连续局刷达此次数 → 强制一次全刷洗残影
```

- [ ] **Step 2: 在主循环 `while(1)` 前加计数/首帧状态**

把现有 `bool online = true;` / `int refresh_token = 0;` 那两行后补两行：

```c
    bool online = true;
    int  refresh_token = 0;
    bool first_frame = true;   // 循环内首次出图 → 强制全刷, 建立 0x26 内容基准
    int  partial_count = 0;    // 已连续局刷次数
```

- [ ] **Step 3: 用统一的“出图 + 全/局决策”替换原三分支刷新块**

把原来这段（约 142-154 行）：

```c
        if (now_online && r.changed) {
            disp->show(s_framebuf, caps.frame_bytes);
            disp->refresh();
        } else if (!now_online && online) {
            mark_offline(s_framebuf, &caps, true);
            disp->show(s_framebuf, caps.frame_bytes);
            disp->refresh();
        } else if (now_online && !online) {
            mark_offline(s_framebuf, &caps, false);
            disp->show(s_framebuf, caps.frame_bytes);
            disp->refresh();
        }
        online = now_online;
```

整体替换为：

```c
        bool changed_any = false, recovered = false;
        if (now_online && r.changed) {
            disp->show(s_framebuf, caps.frame_bytes);   // 新帧已覆盖整 buffer(含叉区)
            changed_any = true;
        } else if (!now_online && online) {
            mark_offline(s_framebuf, &caps, true);       // 在线->离线: 叠叉
            disp->show(s_framebuf, caps.frame_bytes);
            changed_any = true;
        } else if (now_online && !online) {
            mark_offline(s_framebuf, &caps, false);      // 离线->在线: 清叉
            disp->show(s_framebuf, caps.frame_bytes);
            changed_any = true;
            recovered = true;                            // 离线恢复 → 强制全刷
        }
        if (changed_any) {
            bool force_full = first_frame || recovered ||
                              (partial_count >= PARTIAL_BEFORE_FULL);
            if (disp->refresh_partial && !force_full) {
                disp->refresh_partial();
                partial_count++;
            } else {
                disp->refresh();                          // UC8179 无 refresh_partial 时恒走这里
                partial_count = 0;
            }
            first_frame = false;
        }
        online = now_online;
```

- [ ] **Step 4: 编译验证（SSD1677 变体 + UC8179 变体）**

Run:
```bash
source ~/esp/v5.4.1/esp-idf/export.sh
cd software/firmware
idf.py -DINKPULSE_VERIFY=0 build                         # SSD1677(当前 sdkconfig)
idf.py -DINKPULSE_VERIFY=0 -DSDKCONFIG_DEFAULTS="sdkconfig.defaults" -B build_uc reconfigure build 2>/dev/null || \
  echo "(UC8179 变体如需单独验证, 临时 sed sdkconfig 切 PANEL_UC8179_BWR_750 后 idf.py build, 再切回)"
```
Expected: SSD1677 变体构建成功。UC8179 变体（`refresh_partial==NULL` 路径）若验证则同样成功、走全刷分支。

- [ ] **Step 5: 提交**

```bash
git add software/firmware/main/main.c
git commit --no-verify -m "feat(fw): 主循环内容变默认局刷 + 三触发(首帧/离线恢复/每30次)全刷"
```

---

## Task 4: selftest 扩展局刷序列（真机肉眼校准用）

**Files:**
- Modify: `software/firmware/components/ip_display/src/ssd1677_selftest.c`

- [ ] **Step 1: 在 `ssd1677_selftest_run` 末尾（“selftest 结束”日志前）追加局刷序列**

```c
    // ---- 局刷校验: 全刷基准 → 连续局刷走动方块 → 观察不闪/残影/到 30 次洗净 ----
    ESP_LOGI(TAG, "局刷校验: 全刷基准(全白)");
    memset(row, 0x00, sizeof(row));
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
    // 同步 0x26 = 当前(全白), 作首次局刷基准
    {
        static uint8_t white[SSD_ROW_BYTES];
        memset(white, 0x00, sizeof(white));
        set_ram_counter_public_or_inline();   // 见 Step 2 说明
    }

    for (int i = 0; i < 35; i++) {
        ESP_LOGI(TAG, "局刷 #%d", i + 1);
        // 在第 i 列位置画一个黑方块(每次只这一块变化)
        ssd1677_ram_begin();
        for (int y = 0; y < SSD_HEIGHT; y++) {
            for (int b = 0; b < SSD_ROW_BYTES; b++)
                row[b] = (y / 40 == 2 && b == (i % SSD_ROW_BYTES)) ? 0xFF : 0x00;
            ssd1677_ram_row(row);
        }
        ssd1677_update_partial();
        vTaskDelay(pdMS_TO_TICKS(700));
    }
```

> **说明（给实现者）：** selftest 直接用底层 `ssd1677_ram_begin/ram_row/update_*`，不走 `disp_show`，所以 0x26 不会被 disp 层自动同步。为让局刷有正确基准，需在每次 `ssd1677_update_partial()` 前把“上一帧”写进 0x26。最简做法：用公开的 `ssd1677_sync_old_ram(plane)`——但它要整帧 plane 指针，而 selftest 是行式流写、没有整帧 buffer。

- [ ] **Step 2: 改为“写 0x24 后、局刷前，再把同一图案流写进 0x26”**

把 Step 1 里的循环体改成下面这版（去掉 `set_ram_counter_public_or_inline` 占位，改成行式流写 0x26）。先在 `ssd1677_internal.h` 暴露一个行式流写起始助手，或直接在 selftest 内联两遍流写：

selftest 内联实现（不新增 API）——每次先算好该帧、写 0x24 局刷、再用同样的循环写 0x26 作下一轮基准：

```c
    for (int i = 0; i < 35; i++) {
        ESP_LOGI(TAG, "局刷 #%d", i + 1);
        // 写 0x24 = 新帧(第 i 个位置一个黑块)
        ssd1677_ram_begin();   // set counter + 0x24
        for (int y = 0; y < SSD_HEIGHT; y++) {
            for (int b = 0; b < SSD_ROW_BYTES; b++)
                row[b] = (y / 40 == 2 && b == (i % SSD_ROW_BYTES)) ? 0xFF : 0x00;
            ssd1677_ram_row(row);
        }
        ssd1677_update_partial();   // 快波形局刷
        // 写 0x26 = 同一帧, 作下一轮基准(重算同样图案)
        set_ram_counter();          // 见 Step 3: 需在 internal.h 暴露
        hal_spi_cmd(0x26);
        for (int y = 0; y < SSD_HEIGHT; y++) {
            for (int b = 0; b < SSD_ROW_BYTES; b++)
                row[b] = (y / 40 == 2 && b == (i % SSD_ROW_BYTES)) ? 0xFF : 0x00;
            ssd1677_ram_row(row);
        }
        vTaskDelay(pdMS_TO_TICKS(700));
    }
```

- [ ] **Step 3: 在 `ssd1677_internal.h` 暴露 `set_ram_counter`，并在 selftest include 后可用**

`ssd1677.c` 里 `static void set_ram_counter(void)` 去掉 `static` 并在 `ssd1677_internal.h` 声明：

```c
void set_ram_counter(void);   // set RAM X/Y counter 到原点(供 selftest 写 0x26)
```

selftest.c 顶部已 `#include "ssd1677_internal.h"` 与 `#include "ip_hal/spi_bus.h"`，`hal_spi_cmd` 可用。

- [ ] **Step 4: 编译验证 VERIFY 变体**

Run:
```bash
source ~/esp/v5.4.1/esp-idf/export.sh
cd software/firmware && idf.py -DINKPULSE_VERIFY=1 build
```
Expected: 构建成功。

- [ ] **Step 5: 提交**

```bash
git add software/firmware/components/ip_display/src/ssd1677_selftest.c software/firmware/components/ip_display/src/ssd1677_internal.h software/firmware/components/ip_display/src/ssd1677.c
git commit --no-verify -m "test(fw/display): selftest 加局刷序列(全刷基准→35次局刷走块)"
```

---

## Task 5: hub 刷新间隔默认 600→60（pytest TDD）

**Files:**
- Modify: `software/hub/inkpulse_hub/config.py:14`
- Test: `software/hub/tests/test_config.py`

- [ ] **Step 1: 写失败测试（默认间隔应为 60）**

`software/hub/tests/test_config.py` 末尾加：

```python
def test_default_refresh_periodic_is_60s():
    from inkpulse_hub.config import Config
    assert Config().refresh_periodic_s == 60   # 局刷不闪, 默认 1 分钟拉一次让时钟走字
```

- [ ] **Step 2: 跑测试验证它失败**

Run:
```bash
cd software/hub && .venv/bin/python -m pytest tests/test_config.py::test_default_refresh_periodic_is_60s -q
```
Expected: FAIL（当前默认 600）。

- [ ] **Step 3: 改默认值**

`config.py` 第 14 行：

```python
    refresh_periodic_s: int = 60
```

- [ ] **Step 4: 跑测试验证通过 + 全量回归**

Run:
```bash
cd software/hub && .venv/bin/python -m pytest tests/test_config.py::test_default_refresh_periodic_is_60s -q
.venv/bin/python -m pytest -q
```
Expected: 目标测试 PASS；全量仅 `test_discovery` 那条已知 mDNS 环境失败（无关）。

- [ ] **Step 5: 提交**

```bash
git add software/hub/inkpulse_hub/config.py software/hub/tests/test_config.py
git commit --no-verify -m "feat(hub): 默认刷新间隔 600->60s(配合局刷, 时钟逐分钟走字)"
```

> 注意：已部署装置 `~/inkpulse/runtime.json` 存了旧值 600，会覆盖默认；要真机生效需在网页 Settings 改成 60（或删 runtime.json 的该键）。

---

## Task 6: 真机 bring-up 校准（交互，非 subagent）

> 此任务需肉眼看屏 + 改波形常量反复试，由主持人与用户一起做，不派 subagent。

- [ ] **Step 1: 挂串口**：`usbipd.exe list` 找 `1a86:55d3` 的 busid → `usbipd.exe attach --wsl --busid <它>` → `/dev/ttyACM0`。
- [ ] **Step 2: 烧 selftest**：`idf.py -DINKPULSE_VERIFY=1 -p /dev/ttyACM0 -b 460800 flash`，抓串口看局刷序列。
- [ ] **Step 3: 肉眼校准（对照 spec §6 清单）**：
  - 局刷**不闪**？整屏黑块走动平滑？→ 若整屏黑闪=波形没生效，改 `0xCF`→`0xFF` 重试；仍不行走自定义 LUT(0x32)。
  - 连续局刷后有无可见**残影**累积？到第 30 次前是否可接受？→ 调 `PARTIAL_BEFORE_FULL`。
  - **0x26 基准**对不对？关掉 0x26 同步会“旧块不消”即可反证。
- [ ] **Step 4: 波形调通后烧联网固件**：`idf.py -DINKPULSE_VERIFY=0 ... flash`，网页 Settings 设刷新间隔 60s，触发 `/api/refresh`，看真机时钟逐分钟局刷走字、不闪。
- [ ] **Step 5: 把真机定下的常量（波形值 / N）回写代码并提交**。

---

## Self-Review（已自查）

- **Spec 覆盖**：§3.1 驱动→Task 2/4；§3.2 接口→Task 1；§3.3 主循环三触发→Task 3；§3.4 hub→Task 5；§5 测试→各任务编译 + Task 4 selftest + Task 5 pytest；§6 真机→Task 6；§7 兜底（波形回退全刷）→Task 6 Step 3。无遗漏。
- **类型/命名一致**：`refresh_partial`（display.h / s_if / main 判定）、`ssd1677_update_partial` / `ssd1677_sync_old_ram` / `set_ram_counter`（internal.h 声明 ↔ ssd1677.c 定义 ↔ selftest 调用）、`PARTIAL_BEFORE_FULL`（main.c 定义+用）全对齐。
- **无占位**：各步给出实际代码/命令/预期。Task 6 是有意的交互式真机环节，非占位。
