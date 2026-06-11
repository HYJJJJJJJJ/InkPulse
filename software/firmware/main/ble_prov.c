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
