#include "ip_net/net.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include <string.h>

static const char *TAG = "ip_net";

static EventGroupHandle_t s_eg;
#define GOT_IP  BIT0
#define FAILED  BIT1
#define STA_CONNECT_ATTEMPTS 15   // WPA3-SAE 直连不稳(reason 2/205 偶发), 带 2s 间隔循环重连

static bool s_up = false;         // 当前是否已拿到 IP

/* ─── 事件处理 ─────────────────────────────────────────────────── */

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
        ESP_LOGW(TAG, "STA 断开 reason=%d rssi=%d", d ? d->reason : -1, d ? d->rssi : 0);
        s_up = false;
        xEventGroupSetBits(s_eg, FAILED);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        s_up = true;
        xEventGroupSetBits(s_eg, GOT_IP);
    }
}

/* ─── ip_net_init ──────────────────────────────────────────────── */

esp_err_t ip_net_init(void)
{
    static bool s_inited = false;
    if (s_inited) return ESP_OK;

    // NVS 初始化(NO_FREE_PAGES / NEW_VERSION 时擦除重试)
    esp_err_t nv = nvs_flash_init();
    if (nv == ESP_ERR_NVS_NO_FREE_PAGES || nv == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));

    s_eg = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,       on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,   IP_EVENT_STA_GOT_IP,    on_wifi, NULL));

    s_inited = true;
    return ESP_OK;
}

/* ─── ip_net_prepare_sta ───────────────────────────────────────── */

esp_err_t ip_net_prepare_sta(void)
{
    static bool s_sta_created = false;
    if (s_sta_created) return ESP_OK;

    esp_netif_create_default_wifi_sta();
    s_sta_created = true;
    return ESP_OK;
}

/* ─── ip_net_sta_connect ───────────────────────────────────────── */

esp_err_t ip_net_sta_connect(const char *ssid, const char *pass)
{
    wifi_config_t sta = {0};
    strlcpy((char *)sta.sta.ssid,     ssid, sizeof(sta.sta.ssid));
    strlcpy((char *)sta.sta.password, pass, sizeof(sta.sta.password));

    // WPA3-SAE 支持: 允许 WPA2/WPA3 混合 + PMF + H2E
    sta.sta.threshold.authmode = WIFI_AUTH_WPA2_WPA3_PSK;
    sta.sta.pmf_cfg.capable    = true;
    sta.sta.sae_pwe_h2e        = WPA3_SAE_PWE_BOTH;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    ESP_ERROR_CHECK(esp_wifi_start());

    // WPA3-SAE 直连不稳: 带 2s 间隔循环重连, 每次给 8s 等握手
    for (int att = 1; att <= STA_CONNECT_ATTEMPTS; att++) {
        xEventGroupClearBits(s_eg, GOT_IP | FAILED);
        esp_wifi_connect();
        EventBits_t b = xEventGroupWaitBits(s_eg, GOT_IP | FAILED, pdTRUE, pdFALSE,
                                            pdMS_TO_TICKS(8000));
        if (b & GOT_IP) {
            ESP_LOGI(TAG, "WiFi connected (SSID=%s, 第%d次)", ssid, att);
            return ESP_OK;
        }
        ESP_LOGW(TAG, "连接尝试 %d/%d 失败, 2s 后重试", att, STA_CONNECT_ATTEMPTS);
        esp_wifi_disconnect();
        vTaskDelay(pdMS_TO_TICKS(2000));
    }

    ESP_LOGW(TAG, "连续 %d 次连接失败", STA_CONNECT_ATTEMPTS);
    return ESP_FAIL;
}

/* ─── ip_net_is_up ─────────────────────────────────────────────── */

bool ip_net_is_up(void)
{
    return s_up;
}
