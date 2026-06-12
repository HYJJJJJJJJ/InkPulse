#include "ip_provisioning/provisioning.h"
#include "nvs.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "creds";

// 从 NVS namespace "inkpulse" 读凭据。返回 ok && strlen(ssid)>0。
bool creds_load(char *ssid, size_t sl, char *pass, size_t pl)
{
    nvs_handle_t h;
    if (nvs_open("inkpulse", NVS_READONLY, &h) != ESP_OK) return false;
    bool ok = nvs_get_str(h, "ssid", ssid, &sl) == ESP_OK &&
              nvs_get_str(h, "pass", pass, &pl) == ESP_OK;
    nvs_close(h);
    return ok && strlen(ssid) > 0;
}

// 写凭据到 NVS namespace "inkpulse" 并 commit。
void creds_save(const char *ssid, const char *pass)
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
