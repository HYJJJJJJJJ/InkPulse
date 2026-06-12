#include "ip_channel/channel.h"
#include "ip_config/net_config.h"
#include "ip_provisioning/provisioning.h"
#include "esp_http_client.h"
#include "esp_netif.h"
#include "mdns.h"
#include "esp_log.h"
#include <string.h>
#include <strings.h>   // strcasecmp
#include <stdio.h>
#include <stdlib.h>

static const char *TAG = "channel";

// 初始化后保存的帧规格
static size_t s_frame_bytes = 96000;  // 默认值,init 后覆盖

// ETag 持久化(跨 fetch 调用)
static char s_etag[80] = "";

// 本次请求的临时状态(on_evt 回调写入, ch_fetch 读取)
static char s_new_etag[80] = "";
static int  s_next = 600;
static uint8_t *s_buf = NULL;
static size_t   s_buf_len = 0;
static size_t   s_recv = 0;

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
        // 顺序填 buf[0..frame_bytes): black plane 在前, red plane 在后
        if (s_buf) {
            for (int i = 0; i < e->data_len && s_recv < s_frame_bytes; i++, s_recv++) {
                s_buf[s_recv] = ((uint8_t *)e->data)[i];
            }
        }
        break;
    default:
        break;
    }
    return ESP_OK;
}

// 解析出的 hub base 地址(http://IP:port, 不含 /frame), ch_init 时确定一次
static char s_base[128] = "";

// 解析优先级: mDNS 自动发现 > NVS 手动配 > 编译默认。结果写入 s_base。
static void resolve_hub_base(void)
{
    // 1) mDNS: 查询 _inkpulse._tcp, 取首个 IPv4 + 端口
    if (mdns_init() == ESP_OK) {
        mdns_result_t *res = NULL;
        if (mdns_query_ptr("_inkpulse", "_tcp", 2000, 4, &res) == ESP_OK && res) {
            for (mdns_ip_addr_t *a = res->addr; a; a = a->next) {
                if (a->addr.type == ESP_IPADDR_TYPE_V4) {
                    snprintf(s_base, sizeof(s_base), "http://" IPSTR ":%u",
                             IP2STR(&a->addr.u_addr.ip4), res->port);
                    mdns_query_results_free(res);
                    ESP_LOGI(TAG, "hub 经 mDNS 发现: %s", s_base);
                    return;
                }
            }
            mdns_query_results_free(res);
        }
        ESP_LOGW(TAG, "mDNS 未发现 hub, 降级");
    }
    // 2) NVS 手动地址
    if (hub_addr_load(s_base, sizeof(s_base))) {
        ESP_LOGI(TAG, "hub 经 NVS 手动配置: %s", s_base);
        return;
    }
    // 3) 编译默认兜底
    strlcpy(s_base, HUB_DEFAULT_BASE, sizeof(s_base));
    ESP_LOGI(TAG, "hub 用编译默认: %s", s_base);
}

static esp_err_t ch_init(const display_caps_t *caps)
{
    if (caps) {
        s_frame_bytes = caps->frame_bytes;
    }
    resolve_hub_base();   // 连网后调: 确定 hub base 地址
    return ESP_OK;
}

static esp_err_t ch_fetch(uint8_t *buf, size_t buf_len,
                           const sensor_env_t *env, channel_result_t *out)
{
    out->changed = false;
    out->next_refresh_s = 600;

    float t = (env && env->temp_valid)     ? env->temp_c  : -100.0f;
    float h = (env && env->humidity_valid) ? env->humidity : -100.0f;

    char url[256];
    snprintf(url, sizeof(url), "%s/frame?t=%.1f&h=%.1f", s_base, t, h);

    // 重置本次请求临时状态
    s_recv      = 0;
    s_new_etag[0] = 0;
    s_next      = 600;
    s_buf       = buf;
    s_buf_len   = buf_len;

    esp_http_client_config_t cfg = {
        .url           = url,
        .event_handler = on_evt,
        .timeout_ms    = 8000,
    };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    if (s_etag[0]) {
        esp_http_client_set_header(c, "If-None-Match", s_etag);
    }

    esp_err_t ret = ESP_FAIL;
    if (esp_http_client_perform(c) == ESP_OK) {
        int status = esp_http_client_get_status_code(c);
        if (status == 304) {
            // 内容未变,不需要刷屏
            out->changed = false;
            ret = ESP_OK;
        } else if (status == 200 && s_recv == s_frame_bytes) {
            // 新帧,更新 ETag
            strlcpy(s_etag, s_new_etag, sizeof(s_etag));
            out->changed = true;
            ret = ESP_OK;
        } else {
            ESP_LOGW(TAG, "status=%d recv=%u(期望%u)", status,
                     (unsigned)s_recv, (unsigned)s_frame_bytes);
            // out->changed 保持 false; 返回 ESP_FAIL 由 app 决定保留上一帧
        }
    } else {
        ESP_LOGW(TAG, "http perform 失败(离线?), 保留上一帧");
    }
    esp_http_client_cleanup(c);

    out->next_refresh_s = s_next;

    // 清理回调用的临时指针,避免悬空
    s_buf     = NULL;
    s_buf_len = 0;

    return ret;
}

static const channel_if_t s_if = { .init = ch_init, .fetch = ch_fetch };

const channel_if_t *http_hub_channel(void) { return &s_if; }
