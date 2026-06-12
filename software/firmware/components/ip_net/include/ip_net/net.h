#pragma once
#include <stdbool.h>
#include "esp_err.h"

// 一次性初始化: nvs/netif/event/wifi + 注册事件处理(内部事件组)
esp_err_t ip_net_init(void);

// 创建默认 STA netif(供配网与直连共用; 幂等)
esp_err_t ip_net_prepare_sta(void);

// 用凭据连接(WPA3-SAE + 带 2s 间隔循环重连); 成功 ESP_OK, 全部失败 ESP_FAIL
esp_err_t ip_net_sta_connect(const char *ssid, const char *pass);

bool      ip_net_is_up(void);
