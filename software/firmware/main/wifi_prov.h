#pragma once
#include <stdbool.h>
// 连接已保存的 WiFi; 无凭据/连不上则开 SoftAP 配网页, 配完重启。
// 返回是否已连上 STA。
bool wifi_connect_or_provision(void);
