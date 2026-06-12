#include "ble_prov.h"
#include "ip_config/net_config.h"
#include "esp_log.h"
#include "esp_event.h"
#include "nvs.h"
#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_ble.h"
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "ble_prov";
static volatile bool s_got_creds;   // CRED_RECV 收到有效凭据即置位

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
        s_got_creds = true;
        break;
    }
    case WIFI_PROV_CRED_FAIL:
        ESP_LOGW(TAG, "凭据验证失败(密码错或连不上)");
        break;
    case WIFI_PROV_CRED_SUCCESS:
        ESP_LOGI(TAG, "BLE 配网成功");
        break;
    case WIFI_PROV_END:
        ESP_LOGI(TAG, "配网流程结束");
        break;
    default:
        break;
    }
}

static void on_timeout(TimerHandle_t t)
{
    ESP_LOGW(TAG, "BLE 配网超时, 停止 provisioning");
    wifi_prov_mgr_stop_provisioning();   // 使 wifi_prov_mgr_wait() 返回
}

bool ble_prov_run(int timeout_s)
{
    s_got_creds = false;
    esp_event_handler_register(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, prov_event_handler, NULL);

    wifi_prov_mgr_config_t cfg = {
        .scheme = wifi_prov_scheme_ble,
        .scheme_event_handler = WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BTDM,
    };
    if (wifi_prov_mgr_init(cfg) != ESP_OK) {
        ESP_LOGE(TAG, "prov mgr init 失败, 回退 SoftAP");
        esp_event_handler_unregister(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, prov_event_handler);
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
        esp_event_handler_unregister(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, prov_event_handler);
        return false;
    }
    ESP_LOGI(TAG, "BLE 广播名=%s PoP=%s 超时=%ds", PROV_BLE_NAME, PROV_POP, timeout_s);

    // 超时定时器: 到点 stop, 让下面的 wait() 返回
    TimerHandle_t to = xTimerCreate("provto", pdMS_TO_TICKS((uint32_t)timeout_s * 1000),
                                    pdFALSE, NULL, on_timeout);
    xTimerStart(to, 0);

    // 官方阻塞等待: 配网成功(auto-stop) 或超时(手动 stop) 后返回
    wifi_prov_mgr_wait();

    xTimerStop(to, 0);
    xTimerDelete(to, 0);
    wifi_prov_mgr_deinit();
    esp_event_handler_unregister(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, prov_event_handler);

    if (s_got_creds) {
        vTaskDelay(pdMS_TO_TICKS(500));   // 留时间让组件收尾
        return true;
    }
    ESP_LOGW(TAG, "未配网成功, 回退 SoftAP");
    return false;
}
