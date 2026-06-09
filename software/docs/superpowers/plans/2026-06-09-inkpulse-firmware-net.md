# InkPulse 固件 — 联网拉帧计划（子系统②·阶段二）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务执行。`- [ ]` 复选框跟踪。
> **前置：阶段一(驱动 bring-up)必须已通过**——屏能清屏、测试图案正确、红 plane 极性已确定。本计划复用阶段一的 `epd_uc8179` 驱动。

**Goal:** 让设备联网，从 Hub 的 `GET /frame` 拉取 800×480 三色位图（黑/红双 plane），按确定的极性写入 UC8179 并刷新；ETag 去重、离线缓存上一帧、按 `X-Next-Refresh` 节拍循环；首次用 SoftAP 配网写入 NVS；并把 HTU21D 温湿度随请求上报。

**Architecture:** 复用阶段一 `epd_uc8179`。新增：`wifi_prov`(NVS凭据 + SoftAP配网页)、`htu21d`(I2C读温湿度)、`frame_client`(http拉帧+ETag+离线缓存)、主循环。瘦客户端：拉帧→变了才刷→等→循环。

**Tech Stack:** ESP-IDF v5.3.2、esp_wifi、esp_http_client、nvs_flash、esp_http_server(配网页)、driver/i2c。

**对接契约（来自计划①，勿改）：**
- `GET /frame`：body = 黑plane(48000B)+红plane(48000B)=96000B；行主序，每行100字节，MSB=最左像素；黑plane bit=1→黑、红plane bit=1→红。
- 响应头 `ETag`（带引号哈希）、`X-Next-Refresh`（秒）。请求带 `If-None-Match`，命中返回 `304`（无 body）。
- 设备上报温湿度：`GET /frame?t=<℃>&h=<%>`。

**关键映射（阶段一 bring-up 已确定的极性，在此落地）：**
- Hub 黑 plane：bit=1→黑。UC8179 的 0x10(B/W) 约定 1=白 0=黑 → **发送 `~black_byte`**。
- Hub 红 plane：bit=1→红。0x13(RED) 约定按阶段一结论：若 `1=红` 则直发；若 `1=不红` 则发 `~red_byte`。**用 `EPD_RED_INVERT` 宏承载阶段一结论**。

新增文件：
```
software/firmware/main/
  net_config.h         # Hub URL / WiFi 配网参数
  htu21d.h / htu21d.c  # I2C 温湿度
  wifi_prov.h / .c     # NVS 凭据 + SoftAP 配网
  frame_client.h / .c  # http 拉帧 + ETag + 离线缓存 + 写屏
  main.c               # 改为联网主循环
```

---

## Task 1: HTU21D 温湿度（I2C）

**Files:** Create `main/htu21d.h`、`main/htu21d.c`；Modify `main/CMakeLists.txt`(加 htu21d.c)

- [ ] **Step 1: `htu21d.h`**

```c
#pragma once
#include <stdbool.h>
// 读温湿度。成功返回 true，温度℃、湿度% 写入出参。
bool htu21d_read(float *temp_c, float *humidity);
void htu21d_init(void);
```

- [ ] **Step 2: `htu21d.c`（I2C: SCL=GPIO2, SDA=GPIO1；HTU21D 地址 0x40，触发不保持主机测量）**

```c
#include "htu21d.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#define HTU_SDA 1
#define HTU_SCL 2
#define HTU_ADDR 0x40
#define CMD_T_NOHOLD 0xF3
#define CMD_H_NOHOLD 0xF5

static const char *TAG = "htu21d";
static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;

void htu21d_init(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = HTU_SDA,
        .scl_io_num = HTU_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_bus));
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = HTU_ADDR,
        .scl_speed_hz = 100000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(s_bus, &dev_cfg, &s_dev));
}

static bool measure(uint8_t cmd, uint16_t *raw)
{
    if (i2c_master_transmit(s_dev, &cmd, 1, 100) != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(60));           // 14-bit 测量约 50ms
    uint8_t rx[3] = {0};
    if (i2c_master_receive(s_dev, rx, 3, 100) != ESP_OK) return false;
    *raw = ((uint16_t)rx[0] << 8 | rx[1]) & 0xFFFC;  // 去掉状态位
    return true;
}

bool htu21d_read(float *temp_c, float *humidity)
{
    uint16_t rt, rh;
    if (!measure(CMD_T_NOHOLD, &rt)) return false;
    if (!measure(CMD_H_NOHOLD, &rh)) return false;
    *temp_c = -46.85f + 175.72f * rt / 65536.0f;
    *humidity = -6.0f + 125.0f * rh / 65536.0f;
    ESP_LOGI(TAG, "T=%.1fC H=%.1f%%", *temp_c, *humidity);
    return true;
}
```

- [ ] **Step 3: build + 临时在 main 调一次打印验证读数合理（室温/湿度）**
Run: `idf.py build flash monitor` → 期望日志 `T=2x.xC H=xx.x%`，数值合理。

- [ ] **Step 4: Commit** `git commit -m "feat(fw): HTU21D温湿度I2C读取"`

---

## Task 2: WiFi 凭据(NVS) + SoftAP 配网

**Files:** Create `main/net_config.h`、`main/wifi_prov.h`、`main/wifi_prov.c`；Modify CMakeLists

- [ ] **Step 1: `net_config.h`**

```c
#pragma once
#define HUB_FRAME_URL "http://192.168.1.100:8080/frame"  // 改成你 Hub 的局域网地址
#define PROV_AP_SSID  "InkPulse-Setup"
#define PROV_AP_PASS  "inkpulse123"
```

- [ ] **Step 2: `wifi_prov.h`**

```c
#pragma once
#include <stdbool.h>
// 连接已保存的WiFi;无凭据则开SoftAP配网页,配完重启。返回是否已连上。
bool wifi_connect_or_provision(void);
```

- [ ] **Step 3: `wifi_prov.c`**

实现要点（用 esp_wifi + nvs + esp_http_server）：
1. `nvs_flash_init`，从 namespace `inkpulse` 读 `ssid`/`pass`
2. 有凭据 → STA 连接，超时(15s)未连上则进配网
3. 无凭据/连不上 → 启 SoftAP(`PROV_AP_SSID`) + `esp_http_server`：
   - `GET /` 返回一个填 SSID/密码的表单页
   - `POST /save` 存入 NVS → `esp_restart()`

```c
#include "wifi_prov.h"
#include "net_config.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include <string.h>

static const char *TAG = "wifi";
static EventGroupHandle_t s_eg;
#define GOT_IP BIT0
#define FAILED BIT1

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED)
        xEventGroupSetBits(s_eg, FAILED);
    else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP)
        xEventGroupSetBits(s_eg, GOT_IP);
}

static bool load_creds(char *ssid, char *pass)
{
    nvs_handle_t h;
    if (nvs_open("inkpulse", NVS_READONLY, &h) != ESP_OK) return false;
    size_t sl = 33, pl = 65;
    bool ok = nvs_get_str(h, "ssid", ssid, &sl) == ESP_OK &&
              nvs_get_str(h, "pass", pass, &pl) == ESP_OK;
    nvs_close(h);
    return ok && strlen(ssid) > 0;
}

static esp_err_t form_get(httpd_req_t *r)
{
    const char *html =
        "<form method=POST action=/save>"
        "SSID:<input name=ssid><br>密码:<input name=pass type=password><br>"
        "<button>保存并重启</button></form>";
    httpd_resp_send(r, html, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

static esp_err_t save_post(httpd_req_t *r)
{
    char buf[160] = {0};
    int n = httpd_req_recv(r, buf, sizeof(buf) - 1);
    if (n <= 0) return ESP_FAIL;
    char ssid[33] = {0}, pass[65] = {0};
    httpd_query_key_value(buf, "ssid", ssid, sizeof(ssid));
    httpd_query_key_value(buf, "pass", pass, sizeof(pass));
    nvs_handle_t h;
    nvs_open("inkpulse", NVS_READWRITE, &h);
    nvs_set_str(h, "ssid", ssid); nvs_set_str(h, "pass", pass);
    nvs_commit(h); nvs_close(h);
    httpd_resp_sendstr(r, "saved, rebooting...");
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
    return ESP_OK;
}

static void start_provision_ap(void)
{
    ESP_LOGW(TAG, "进入 SoftAP 配网: 连 %s 浏览器开 http://192.168.4.1", PROV_AP_SSID);
    esp_netif_create_default_wifi_ap();
    wifi_config_t ap = { .ap = { .ssid_len = strlen(PROV_AP_SSID),
        .max_connection = 2, .authmode = WIFI_AUTH_WPA2_PSK } };
    strcpy((char *)ap.ap.ssid, PROV_AP_SSID);
    strcpy((char *)ap.ap.password, PROV_AP_PASS);
    esp_wifi_set_mode(WIFI_MODE_AP);
    esp_wifi_set_config(WIFI_IF_AP, &ap);
    esp_wifi_start();
    httpd_handle_t srv = NULL;
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    httpd_start(&srv, &cfg);
    httpd_uri_t u1 = { .uri = "/", .method = HTTP_GET, .handler = form_get };
    httpd_uri_t u2 = { .uri = "/save", .method = HTTP_POST, .handler = save_post };
    httpd_register_uri_handler(srv, &u1);
    httpd_register_uri_handler(srv, &u2);
}

bool wifi_connect_or_provision(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_wifi_set_default_wifi_sta_handlers();  // 若链接报错可改手动 create_default_wifi_sta
    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));
    esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi, NULL);

    char ssid[33] = {0}, pass[65] = {0};
    if (!load_creds(ssid, pass)) { esp_netif_create_default_wifi_sta(); start_provision_ap(); return false; }

    esp_netif_create_default_wifi_sta();
    s_eg = xEventGroupCreate();
    wifi_config_t sta = {0};
    strcpy((char *)sta.sta.ssid, ssid);
    strcpy((char *)sta.sta.password, pass);
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &sta);
    esp_wifi_start();
    esp_wifi_connect();
    EventBits_t b = xEventGroupWaitBits(s_eg, GOT_IP | FAILED, pdFALSE, pdFALSE, pdMS_TO_TICKS(15000));
    if (b & GOT_IP) { ESP_LOGI(TAG, "WiFi connected"); return true; }
    ESP_LOGW(TAG, "连接失败, 进入配网"); start_provision_ap(); return false;
}
```

> 注：`esp_wifi_set_default_wifi_sta_handlers()` 在部分 IDF 版本签名不同；若编译报错改为只调 `esp_netif_create_default_wifi_sta()`。bring-up 时按编译器提示微调。

- [ ] **Step 4: build + 验证**：无凭据时看到 SoftAP，手机连上配网→重启→STA 连上打印 IP。
- [ ] **Step 5: Commit** `git commit -m "feat(fw): WiFi STA + NVS凭据 + SoftAP配网"`

---

## Task 3: 拉帧客户端（http + ETag + 离线缓存 + 写屏）

**Files:** Create `main/frame_client.h`、`main/frame_client.c`；Modify CMakeLists、`epd_uc8179.h/.c`（加从 plane 缓冲写屏的函数）

- [ ] **Step 1: `epd_uc8179` 增加"写双 plane 缓冲"接口**

`epd_uc8179.h` 加：
```c
#include <stdbool.h>
#define EPD_RED_INVERT 0   // 阶段一bring-up结论: 0x13红极性 1=红则置0,否则置1
// black/red 各 EPD_PLANE_BYTES; black bit=1->黑, red bit=1->红 (Hub /frame 约定)
void epd_display_planes(const uint8_t *black, const uint8_t *red);
```

`epd_uc8179.c` 加：
```c
void epd_display_planes(const uint8_t *black, const uint8_t *red)
{
    // 0x10(B/W): 1=白0=黑, Hub black bit=1->黑 => 发 ~black
    epd_send_cmd(0x10);
    {
        static uint8_t tmp[EPD_ROW_BYTES];
        for (int y = 0; y < EPD_HEIGHT; y++) {
            const uint8_t *src = black + y * EPD_ROW_BYTES;
            for (int i = 0; i < EPD_ROW_BYTES; i++) tmp[i] = ~src[i];
            epd_send_data_buf(tmp, EPD_ROW_BYTES);
        }
    }
    // 0x13(RED): 按极性结论
    epd_send_cmd(0x13);
    {
        static uint8_t tmp[EPD_ROW_BYTES];
        for (int y = 0; y < EPD_HEIGHT; y++) {
            const uint8_t *src = red + y * EPD_ROW_BYTES;
            for (int i = 0; i < EPD_ROW_BYTES; i++)
                tmp[i] = EPD_RED_INVERT ? (uint8_t)~src[i] : src[i];
            epd_send_data_buf(tmp, EPD_ROW_BYTES);
        }
    }
    epd_refresh();
}
```

- [ ] **Step 2: `frame_client.h`**

```c
#pragma once
#include <stdbool.h>
// 拉一帧: 带 If-None-Match(上次etag) + 温湿度查询。
// 返回: 1=有新帧已写屏, 0=304未变, -1=出错(保留上一帧)。next_refresh_s 写出下次间隔。
int frame_fetch_and_show(float temp_c, float humidity, int *next_refresh_s);
```

- [ ] **Step 3: `frame_client.c`**

要点：
- 静态缓冲 `black[48000]`、`red[48000]`、`etag[64]`（放 .bss 或 PSRAM；96KB 内部 RAM 也放得下）
- 用 `esp_http_client`，加请求头 `If-None-Match: <etag>`，URL 拼 `?t=&h=`
- 收 body 到 black+red（分界 48000）；读响应头 `ETag` 存起、`X-Next-Refresh` 解析
- 状态码 304 → 返回 0；200 → `epd_display_planes` 写屏，返回 1；其它/异常 → 返回 -1
- 离线缓存：保留上次成功的 black/red/etag；出错时不刷屏（屏自然留着上一帧）；可在角落画离线标记（可选，后续）

```c
#include "frame_client.h"
#include "net_config.h"
#include "epd_uc8179.h"
#include "pins.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "frame";
static uint8_t s_black[EPD_PLANE_BYTES];
static uint8_t s_red[EPD_PLANE_BYTES];
static char s_etag[80] = "";
static int s_status = 0, s_next = 600;
static char s_new_etag[80] = "";
static size_t s_recv = 0;

static esp_err_t on_evt(esp_http_client_event_t *e)
{
    switch (e->event_id) {
    case HTTP_EVENT_ON_HEADER:
        if (strcasecmp(e->header_key, "ETag") == 0)
            strlcpy(s_new_etag, e->header_value, sizeof(s_new_etag));
        else if (strcasecmp(e->header_key, "X-Next-Refresh") == 0)
            s_next = atoi(e->header_value);
        break;
    case HTTP_EVENT_ON_DATA:
        // 顺序填入 black(0..48000) 再 red(48000..96000)
        for (int i = 0; i < e->data_len && s_recv < 2 * EPD_PLANE_BYTES; i++, s_recv++) {
            if (s_recv < EPD_PLANE_BYTES) s_black[s_recv] = ((uint8_t *)e->data)[i];
            else s_red[s_recv - EPD_PLANE_BYTES] = ((uint8_t *)e->data)[i];
        }
        break;
    default: break;
    }
    return ESP_OK;
}

int frame_fetch_and_show(float temp_c, float humidity, int *next_refresh_s)
{
    char url[256];
    snprintf(url, sizeof(url), "%s?t=%.1f&h=%.1f", HUB_FRAME_URL, temp_c, humidity);
    s_recv = 0; s_new_etag[0] = 0; s_next = 600;

    esp_http_client_config_t cfg = { .url = url, .event_handler = on_evt, .timeout_ms = 8000 };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    if (s_etag[0]) esp_http_client_set_header(c, "If-None-Match", s_etag);

    int ret = -1;
    if (esp_http_client_perform(c) == ESP_OK) {
        s_status = esp_http_client_get_status_code(c);
        if (s_status == 304) { ret = 0; }
        else if (s_status == 200 && s_recv == 2 * EPD_PLANE_BYTES) {
            strlcpy(s_etag, s_new_etag, sizeof(s_etag));
            epd_display_planes(s_black, s_red);
            ret = 1;
        } else {
            ESP_LOGW(TAG, "status=%d recv=%u(期望96000)", s_status, (unsigned)s_recv);
        }
    } else {
        ESP_LOGW(TAG, "http perform 失败(离线?), 保留上一帧");
    }
    esp_http_client_cleanup(c);
    *next_refresh_s = s_next;
    return ret;
}
```

> 注：`strlcpy` 在 ESP-IDF 可用；若链接缺失改用 `strncpy`+手动补 `\0`。

- [ ] **Step 4: build 确认无误**
- [ ] **Step 5: Commit** `git commit -m "feat(fw): 拉帧客户端(ETag/304/离线) + plane写屏(极性映射)"`

---

## Task 4: 联网主循环

**Files:** Modify `main/main.c`、`main/CMakeLists.txt`(确保含全部 .c)

- [ ] **Step 1: `main.c`**

```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "epd_uc8179.h"
#include "htu21d.h"
#include "wifi_prov.h"
#include "frame_client.h"

static const char *TAG = "inkpulse";

void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    epd_hal_init();
    epd_init();
    htu21d_init();

    if (!wifi_connect_or_provision()) {
        // 进入配网模式, 不继续(配完会重启)
        epd_clear();   // 给个干净白屏提示
        while (1) vTaskDelay(pdMS_TO_TICKS(1000));
    }

    while (1) {
        float t = 0, h = 0;
        bool have_env = htu21d_read(&t, &h);
        int next = 600;
        int r = frame_fetch_and_show(have_env ? t : -100, have_env ? h : -100, &next);
        ESP_LOGI(TAG, "fetch -> %s, next=%ds",
                 r == 1 ? "新帧已刷" : r == 0 ? "未变(304)" : "出错/离线", next);
        if (next < 30) next = 30;          // 下限保护
        vTaskDelay(pdMS_TO_TICKS(next * 1000));
    }
}
```

- [ ] **Step 2: 端到端联调（需 Hub 在运行）**
1. 电脑跑 Hub（计划①）：`INKPULSE_CONFIG=... python -m inkpulse_hub`，记下局域网 IP，改 `net_config.h` 的 `HUB_FRAME_URL`
2. `idf.py build flash monitor`，首次走 SoftAP 配网连上家里 WiFi
3. 重启后应：连 WiFi → 拉帧 → 屏显示 Hub 渲染的仪表盘（状态/用量/待办/温湿度顶栏）
4. 验证：在 `/todos` 加一条待办 → 等下次刷新 → 屏上出现；ETag 未变时日志显示 `未变(304)` 不刷屏

- [ ] **Step 3: 核对颜色**：若红/黑反了，调 `EPD_RED_INVERT` 或 `epd_display_planes` 的 black 取反；与阶段一结论一致即可。

- [ ] **Step 4: Commit** `git commit -m "feat(fw): 联网主循环(温湿度上报+拉帧+节拍)"`

---

## 自检对照（spec/契约 → task）
- WiFi STA + 配网 → Task 2 ✅
- HTU21D 上报 → Task 1 + 主循环 ✅
- `/frame` 拉取 + If-None-Match/304 → Task 3 ✅
- 离线保留上一帧 → Task 3(出错不刷屏) ✅
- plane→UC8179 极性映射 → Task 3(`epd_display_planes`+`EPD_RED_INVERT`) ✅
- `X-Next-Refresh` 节拍 → Task 4 ✅

**已知待 bring-up 微调：** `EPD_RED_INVERT` 取值（阶段一结论）；`esp_wifi_set_default_wifi_sta_handlers`/`strlcpy` 的 IDF 版本差异；离线角标(可选增强)；深睡省电(常插电可不做)。

**完成后即闭环**：电脑出数据→渲染→设备显示，三个功能(Claude状态/用量、待办、照片)全部可见。
