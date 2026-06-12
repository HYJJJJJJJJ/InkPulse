#include "frame_client.h"
#include "ip_config/net_config.h"
#include "epd_uc8179.h"
#include "pins.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include <string.h>
#include <strings.h>   // strcasecmp
#include <stdio.h>
#include <stdlib.h>

static const char *TAG = "frame";

// 96KB 双 plane 缓冲放 .bss(内部 RAM 足够)
static uint8_t s_black[EPD_PLANE_BYTES];
static uint8_t s_red[EPD_PLANE_BYTES];
static char s_etag[80] = "";       // 上次成功的 ETag(用于 If-None-Match)

// 本次请求的临时状态
static char s_new_etag[80] = "";
static int s_next = 600;
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
        // 顺序填: black[0..48000) 再 red[0..48000)
        for (int i = 0; i < e->data_len && s_recv < 2 * EPD_PLANE_BYTES; i++, s_recv++) {
            uint8_t v = ((uint8_t *)e->data)[i];
            if (s_recv < EPD_PLANE_BYTES) s_black[s_recv] = v;
            else s_red[s_recv - EPD_PLANE_BYTES] = v;
        }
        break;
    default:
        break;
    }
    return ESP_OK;
}

int frame_fetch_and_show(float temp_c, float humidity, int *next_refresh_s)
{
    char url[256];
    snprintf(url, sizeof(url), "%s?t=%.1f&h=%.1f", HUB_FRAME_URL, temp_c, humidity);
    s_recv = 0;
    s_new_etag[0] = 0;
    s_next = 600;

    esp_http_client_config_t cfg = {
        .url = url,
        .event_handler = on_evt,
        .timeout_ms = 8000,
    };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    if (s_etag[0]) esp_http_client_set_header(c, "If-None-Match", s_etag);

    int ret = -1;
    if (esp_http_client_perform(c) == ESP_OK) {
        int status = esp_http_client_get_status_code(c);
        if (status == 304) {
            ret = 0;
        } else if (status == 200 && s_recv == 2 * EPD_PLANE_BYTES) {
            strlcpy(s_etag, s_new_etag, sizeof(s_etag));
            epd_display_planes(s_black, s_red);
            ret = 1;
        } else {
            ESP_LOGW(TAG, "status=%d recv=%u(期望%d)", status,
                     (unsigned)s_recv, 2 * EPD_PLANE_BYTES);
        }
    } else {
        ESP_LOGW(TAG, "http perform 失败(离线?), 保留上一帧");
    }
    esp_http_client_cleanup(c);
    *next_refresh_s = s_next;
    return ret;
}
