#include "ip_provisioning/provisioning.h"
#include "ip_config/net_config.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "nvs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <ctype.h>
#include <stdlib.h>

static const char *TAG = "softap_prov";

// 表单 application/x-www-form-urlencoded 解码(in-place): %XX -> 字节, + -> 空格。
static void urldecode(char *s)
{
    char *o = s;
    for (; *s; s++) {
        if (*s == '%' && isxdigit((unsigned char)s[1]) && isxdigit((unsigned char)s[2])) {
            char hex[3] = { s[1], s[2], 0 };
            *o++ = (char)strtol(hex, NULL, 16);
            s += 2;
        } else if (*s == '+') {
            *o++ = ' ';
        } else {
            *o++ = *s;
        }
    }
    *o = 0;
}

static esp_err_t form_get(httpd_req_t *r)
{
    const char *html =
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<h3>InkPulse 配网</h3>"
        "<form method=POST action=/save>"
        "SSID:<br><input name=ssid><br>密码:<br><input name=pass type=password><br>"
        "Hub 地址(可选, 留空自动发现):<br><input name=hub placeholder=http://192.168.1.5:8080><br><br>"
        "<button>保存并重启</button></form>";
    httpd_resp_send(r, html, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

static esp_err_t save_post(httpd_req_t *r)
{
    char buf[300] = {0};
    int n = httpd_req_recv(r, buf, sizeof(buf) - 1);
    if (n <= 0) return ESP_FAIL;
    char ssid[33] = {0}, pass[65] = {0}, hub[129] = {0};
    httpd_query_key_value(buf, "ssid", ssid, sizeof(ssid));
    httpd_query_key_value(buf, "pass", pass, sizeof(pass));
    httpd_query_key_value(buf, "hub", hub, sizeof(hub));

    creds_save(ssid, pass);
    if (strlen(hub) > 0) { urldecode(hub); hub_addr_save(hub); }   // 留空则不写, 靠 mDNS/默认

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

// 非阻塞起 SoftAP 网页配网: 开 AP + httpd 后立即返回 false。
// 用户网页配网后由 save_post 内部 esp_restart; run 返回 false 表示"未当场完成配网"。
static bool softap_run(int timeout_s)
{
    (void)timeout_s;
    start_provision_ap();
    return false;
}

static const provisioning_if_t s_if = { .run = softap_run };
const provisioning_if_t *softap_provisioning(void){ return &s_if; }
