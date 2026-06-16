#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "ip_sensor/sensor.h"
#include "ip_display/display.h"
#include "ip_net/net.h"
#include "ip_provisioning/provisioning.h"
#include "ip_config/net_config.h"
#include "ip_channel/channel.h"
#include "ip_button/button.h"
#include "esp_system.h"   // esp_restart

static const char *TAG = "inkpulse";

#define PARTIAL_BEFORE_FULL 8    // 连续局刷达此次数 → 强制一次全刷洗残影/灰(过渡值, 待厂商波形)

static uint8_t s_framebuf[96000];

// 定义 INKPULSE_VERIFY(idf.py build -DINKPULSE_VERIFY=1 或在此 #define)
// 可跑阶段一 bring-up harness: 温湿度 + 白/黑/红, 不联网。
#ifdef INKPULSE_VERIFY

void app_main(void)
{
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "  InkPulse 合并验证: 温湿度 + 屏幕");
    ESP_LOGI(TAG, "==================================================");

    ESP_LOGI(TAG, "[1] HTU21D 温湿度:");
    const sensor_if_t *sensor = htu21d_sensor();
    sensor->init();
    for (int i = 0; i < 3; i++) {
        sensor_env_t env = {0};
        sensor->read(&env);
        if (env.temp_valid || env.humidity_valid)
            ESP_LOGI(TAG, "    温度=%.2f C (valid=%d)   湿度=%.2f %% (valid=%d)",
                     env.temp_c, env.temp_valid, env.humidity, env.humidity_valid);
        else
            ESP_LOGW(TAG, "    读取失败");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

    ESP_LOGI(TAG, "[2] 墨水屏: 初始化 + 白/黑/红/分屏/棋盘");
    const display_if_t *disp =
#if CONFIG_PANEL_SSD1677_BW_426
        ssd1677_driver();
#else
        uc8179_driver();
#endif
    disp->init();
    disp->selftest();
    ESP_LOGI(TAG, "=== 验证结束 ===");
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}

#else  // ---- 联网主循环(默认) ----

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

// 按键回调: 短按唤醒主循环立即刷新; 长按清凭据重启进配网。
static TaskHandle_t s_main_task;
static void on_btn_short(void) { if (s_main_task) xTaskNotifyGive(s_main_task); }
static void on_btn_long(void)  { creds_clear(); esp_restart(); }

void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    s_main_task = xTaskGetCurrentTaskHandle();
    button_init(on_btn_short, on_btn_long);
    const display_if_t  *disp   =
#if CONFIG_PANEL_SSD1677_BW_426
        ssd1677_driver();
#else
        uc8179_driver();
#endif
    const sensor_if_t   *sensor = htu21d_sensor();
    const channel_if_t  *chan   = http_hub_channel();
    disp->init();
    sensor->init();
    ip_net_init();
    ip_net_prepare_sta();   // STA netif 必须在连接前创建(有凭据直连 / 无凭据 mgr 配网都需要),
                            // 否则即使关联上 AP 也没 DHCP client、拿不到 IP。幂等。

    display_caps_t caps;
    disp->get_caps(&caps);

    char ssid[33]={0}, pass[65]={0};
    if (!creds_load(ssid,sizeof ssid,pass,sizeof pass)) {
        if (!ble_provisioning()->run(PROV_BLE_TIMEOUT_S)) {
            // BLE 超时/失败 → SoftAP 起网页, 等用户配网后内部 esp_restart
            softap_provisioning()->run(0);
            disp->clear();
            while (1) vTaskDelay(pdMS_TO_TICKS(1000));   // 等重启
        }
        // BLE 配网成功(凭据已存 NVS), 重读
        creds_load(ssid,sizeof ssid,pass,sizeof pass);
    }
    // 统一用 NVS 凭据连接(BLE 路径: 不 esp_restart, 故不会触发 App "Device disconnected";
    //   BLE 期间 mgr 已 auto-stop, 这里 STA 重连一次即可)
    if (ip_net_sta_connect(ssid,pass) != ESP_OK) {
        disp->clear(); while (1) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    disp->clear();   // 开机消残影
    chan->init(&caps);

    bool online = true;       // 连接状态, 仅在翻转时刷屏(避免 e-ink 频繁全刷)
    int  refresh_token = 0;   // hub 刷新令牌基线; 变化=web 请求真机刷新
    bool first_frame = true;   // 循环内首次出图 → 强制全刷, 建立 0x26 内容基准
    int  partial_count = 0;    // 已连续局刷次数
    while (1) {
        sensor_env_t env; sensor->read(&env);
        channel_result_t r = { .changed = false, .next_refresh_s = 600 };
        esp_err_t fr = chan->fetch(s_framebuf, sizeof s_framebuf, &env, &r);
        bool now_online = (fr == ESP_OK);

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

        ESP_LOGI(TAG, "fetch -> %s, next=%ds",
                 (now_online && r.changed) ? "新帧已刷" :
                 now_online                ? "未变/未刷" : "出错/离线",
                 r.next_refresh_s);
        int next = r.next_refresh_s < 30 ? 30 : r.next_refresh_s;
        // 分段等待: 每 10s 查 hub 刷新令牌, 令牌变化(web 请求刷新)或 BOOT 短按则提前刷新
        int waited = 0;
        while (waited < next) {
            int step = (next - waited) > 10 ? 10 : (next - waited);
            if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS((uint32_t)step * 1000))) break;  // BOOT 短按
            waited += step;
            int tok = http_hub_poll_token();
            if (tok >= 0 && tok != refresh_token) { refresh_token = tok; break; }
        }
    }
}

#endif
