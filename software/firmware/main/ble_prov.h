#pragma once
#include <stdbool.h>
// 启动 BLE 配网, 阻塞等待直到配网成功或超时(timeout_s 秒)。
// 成功: 凭据已写入 NVS namespace "inkpulse", 返回 true(调用方应 esp_restart)。
// 超时/启动失败: 返回 false(调用方应回退 SoftAP)。
// 前置: 调用前需已 esp_wifi_init + 创建默认 STA netif。
bool ble_prov_run(int timeout_s);
