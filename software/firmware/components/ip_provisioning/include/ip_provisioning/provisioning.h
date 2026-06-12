#pragma once
#include <stdbool.h>
#include <stddef.h>
typedef struct { bool (*run)(int timeout_s); } provisioning_if_t;
const provisioning_if_t *ble_provisioning(void);
const provisioning_if_t *softap_provisioning(void);
// 凭据(NVS namespace "inkpulse")
bool creds_load(char *ssid, size_t sl, char *pass, size_t pl);
void creds_save(const char *ssid, const char *pass);
void creds_clear(void);   // 清 ssid/pass(长按重新配网用)
// hub base 地址(同 namespace, key "hub", 如 http://192.168.1.5:8080)
// 跨网/公网时由 SoftAP 表单手动配; 留空则靠 mDNS 自动发现/编译默认。
bool hub_addr_load(char *out, size_t n);
void hub_addr_save(const char *url);
