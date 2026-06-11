#pragma once
// Hub 局域网地址: 改成你电脑跑 inkpulse_hub 的 IP:端口
#define HUB_FRAME_URL "http://172.27.73.66:8080/frame"

// SoftAP 首次配网热点
#define PROV_AP_SSID  "InkPulse-Setup"
#define PROV_AP_PASS  "inkpulse123"

// BLE 配网(优先) 参数
#define PROV_BLE_NAME       "PROV_InkPulse"   // BLE 广播名(官方 App 扫描显示)
#define PROV_POP            "inkpulse"         // proof-of-possession 口令(App 输入)
#define PROV_BLE_TIMEOUT_S  180                // BLE 等待超时, 超时回退 SoftAP
