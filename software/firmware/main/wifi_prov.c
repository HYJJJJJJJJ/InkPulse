#include "wifi_prov.h"
#include "net_config.h"
#include "ble_prov.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
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
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<h3>InkPulse 配网</h3>"
        "<form method=POST action=/save>"
        "SSID:<br><input name=ssid><br>密码:<br><input name=pass type=password><br><br>"
        "<button>保存并重启</button></form>";
    httpd_resp_send(r, html, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

static esp_err_t save_post(httpd_req_t *r)
{
    char buf[200] = {0};
    int n = httpd_req_recv(r, buf, sizeof(buf) - 1);
    if (n <= 0) return ESP_FAIL;
    char ssid[33] = {0}, pass[65] = {0};
    httpd_query_key_value(buf, "ssid", ssid, sizeof(ssid));
    httpd_query_key_value(buf, "pass", pass, sizeof(pass));

    nvs_handle_t h;
    if (nvs_open("inkpulse", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_str(h, "ssid", ssid);
        nvs_set_str(h, "pass", pass);
        nvs_commit(h);
        nvs_close(h);
    }
    httpd_resp_sendstr(r, "saved, rebooting...");
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
    return ESP_OK;
}

static void start_provision_ap(void)
{
    ESP_LOGW(TAG, "进入 SoftAP 配网: 连 %s, 浏览器开 http://192.168.4.1", PROV_AP_SSID);
    esp_netif_create_default_wifi_ap();
    wifi_config_t ap = { .ap = {
        .ssid_len = strlen(PROV_AP_SSID),
        .max_connection = 2,
        .authmode = WIFI_AUTH_WPA2_PSK,
    } };
    strcpy((char *)ap.ap.ssid, PROV_AP_SSID);
    strcpy((char *)ap.ap.password, PROV_AP_PASS);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_ERROR_CHECK(esp_wifi_start());

    httpd_handle_t srv = NULL;
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    if (httpd_start(&srv, &cfg) == ESP_OK) {
        httpd_uri_t u1 = { .uri = "/", .method = HTTP_GET, .handler = form_get };
        httpd_uri_t u2 = { .uri = "/save", .method = HTTP_POST, .handler = save_post };
        httpd_register_uri_handler(srv, &u1);
        httpd_register_uri_handler(srv, &u2);
    }
}

bool wifi_connect_or_provision(void)
{
    esp_err_t nv = nvs_flash_init();
    if (nv == ESP_ERR_NVS_NO_FREE_PAGES || nv == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi, NULL));

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

    esp_netif_create_default_wifi_sta();
    s_eg = xEventGroupCreate();
    wifi_config_t sta = {0};
    strlcpy((char *)sta.sta.ssid, ssid, sizeof(sta.sta.ssid));
    strlcpy((char *)sta.sta.password, pass, sizeof(sta.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_connect();

    EventBits_t b = xEventGroupWaitBits(s_eg, GOT_IP | FAILED, pdTRUE, pdFALSE,
                                        pdMS_TO_TICKS(15000));
    if (b & GOT_IP) {
        ESP_LOGI(TAG, "WiFi connected (SSID=%s)", ssid);
        return true;
    }
    ESP_LOGW(TAG, "连接失败, 进入配网");
    start_provision_ap();
    return false;
}
