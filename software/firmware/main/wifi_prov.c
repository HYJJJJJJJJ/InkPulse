#include "wifi_prov.h"
#include "ip_config/net_config.h"
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
#define STA_CONNECT_ATTEMPTS 15   // WPA3-SAE 直连不稳(reason 2/205 偶发), 主流程带 2s 间隔循环重连

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
        ESP_LOGW(TAG, "STA 断开 reason=%d rssi=%d", d ? d->reason : -1, d ? d->rssi : 0);
        xEventGroupSetBits(s_eg, FAILED);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_eg, GOT_IP);
    }
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
    esp_wifi_stop();   // 先停掉 BLE 配网/STA 残留的 WiFi 状态, 否则切 AP 模式可能失败
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
    s_eg = xEventGroupCreate();   // 提前创建: 配网分支收到 IP/断连事件时 on_wifi 也会用到它
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi, NULL));

    char ssid[33] = {0}, pass[65] = {0};
    if (!load_creds(ssid, pass)) {
        // wifi_provisioning 需要默认 STA netif
        esp_netif_create_default_wifi_sta();
        // ① 优先 BLE 配网。成功后 wifi_prov_mgr 已用凭据连上 WiFi:
        //    不重启, 复用该连接直接进主循环, 让 BLE 把"配网成功"回报给 App,
        //    避免 App 报 "Device disconnected"(过早 esp_restart 打断 BLE 收尾)。
        if (ble_prov_run(PROV_BLE_TIMEOUT_S)) {
            ESP_LOGI(TAG, "BLE 配网成功, 复用已建立连接(不重启)");
            xEventGroupClearBits(s_eg, FAILED);   // 清掉配网过程中的瞬断标志
            EventBits_t b = xEventGroupWaitBits(s_eg, GOT_IP, pdTRUE, pdFALSE,
                                                pdMS_TO_TICKS(15000));
            if (b & GOT_IP) {
                ESP_LOGI(TAG, "已联网(BLE 配网)");
                return true;
            }
            // 少见: mgr 连上但 DHCP 未拿到 IP → 重启用 NVS 凭据走 STA 兜底
            ESP_LOGW(TAG, "配网后未拿到 IP, 重启走 NVS-STA 兜底");
            esp_restart();
        }
        // ② BLE 超时/失败 → SoftAP 网页兜底
        ESP_LOGW(TAG, "回退 SoftAP 配网");
        start_provision_ap();
        return false;
    }

    esp_netif_create_default_wifi_sta();
    wifi_config_t sta = {0};
    strlcpy((char *)sta.sta.ssid, ssid, sizeof(sta.sta.ssid));
    strlcpy((char *)sta.sta.password, pass, sizeof(sta.sta.password));
    // 支持 WPA3-SAE(如小米热点): 允许 WPA2/WPA3 混合 + PMF + H2E。否则手动 STA 直连
    // 纯 WPA3 会在 SAE auth 阶段失败(BLE 配网走 wifi_prov_mgr 已默认支持, 此直连路径需显式开)。
    sta.sta.threshold.authmode = WIFI_AUTH_WPA2_WPA3_PSK;
    sta.sta.pmf_cfg.capable = true;
    sta.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    ESP_ERROR_CHECK(esp_wifi_start());

    // WPA3-SAE 直连不稳: 回调里立即重连太快, AP 会限速/拒绝(reason 205/2 交替)。
    // 改为主流程带 2s 间隔的循环重连, 每次给 8s 等握手, 比猛连可靠得多。
    for (int att = 1; att <= STA_CONNECT_ATTEMPTS; att++) {
        xEventGroupClearBits(s_eg, GOT_IP | FAILED);
        esp_wifi_connect();
        EventBits_t b = xEventGroupWaitBits(s_eg, GOT_IP | FAILED, pdTRUE, pdFALSE,
                                            pdMS_TO_TICKS(8000));
        if (b & GOT_IP) {
            ESP_LOGI(TAG, "WiFi connected (SSID=%s, 第%d次)", ssid, att);
            return true;
        }
        ESP_LOGW(TAG, "连接尝试 %d/%d 失败, 2s 后重试", att, STA_CONNECT_ATTEMPTS);
        esp_wifi_disconnect();
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
    ESP_LOGW(TAG, "连续 %d 次连接失败, 进入配网", STA_CONNECT_ATTEMPTS);
    start_provision_ap();
    return false;
}
