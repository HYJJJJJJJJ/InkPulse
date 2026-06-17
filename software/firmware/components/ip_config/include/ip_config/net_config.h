#pragma once
// Hub base 地址解析优先级: mDNS 自动发现 > NVS 手动配 > 此编译默认(兜底)。
// 不含 /frame 路径(由 http_hub 拼接)。默认值仅在前两者都失败时使用。
#define HUB_DEFAULT_BASE "http://192.168.10.64:8080"

// SoftAP 首次配网热点
#define PROV_AP_SSID  "InkPulse-Setup"
#define PROV_AP_PASS  "inkpulse123"

// BLE 配网(优先) 参数
#define PROV_BLE_NAME       "PROV_InkPulse"   // BLE 广播名(官方 App 扫描显示)
#define PROV_POP            "inkpulse"         // proof-of-possession 口令(App 输入)
#define PROV_BLE_TIMEOUT_S  180                // BLE 等待超时, 超时回退 SoftAP
