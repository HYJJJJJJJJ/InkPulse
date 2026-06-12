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

static const char *TAG = "inkpulse";

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
    const display_if_t *disp = uc8179_driver();
    disp->init();
    disp->selftest();
    ESP_LOGI(TAG, "=== 验证结束 ===");
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}

#else  // ---- 联网主循环(默认) ----

void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    const display_if_t  *disp   = uc8179_driver();
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

    while (1) {
        sensor_env_t env; sensor->read(&env);
        channel_result_t r = { .changed = false, .next_refresh_s = 600 };
        esp_err_t fr = chan->fetch(s_framebuf, sizeof s_framebuf, &env, &r);
        if (fr == ESP_OK && r.changed) {
            disp->show(s_framebuf, caps.frame_bytes);
            disp->refresh();
        }
        ESP_LOGI(TAG, "fetch -> %s, next=%ds",
                 (fr == ESP_OK && r.changed) ? "新帧已刷" :
                 (fr == ESP_OK)              ? "未变/未刷" : "出错/离线",
                 r.next_refresh_s);
        int next = r.next_refresh_s < 30 ? 30 : r.next_refresh_s;
        vTaskDelay(pdMS_TO_TICKS((uint32_t)next * 1000));
    }
}

#endif
