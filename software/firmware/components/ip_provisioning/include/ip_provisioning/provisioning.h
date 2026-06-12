#pragma once
#include <stdbool.h>
#include <stddef.h>
typedef struct { bool (*run)(int timeout_s); } provisioning_if_t;
const provisioning_if_t *ble_provisioning(void);
const provisioning_if_t *softap_provisioning(void);
// 凭据(NVS namespace "inkpulse")
bool creds_load(char *ssid, size_t sl, char *pass, size_t pl);
void creds_save(const char *ssid, const char *pass);
