# InkPulse 蓝牙配网设计（BLE 为主 + SoftAP 兜底）

> 子系统②（固件）配网方式升级。在阶段二联网（SoftAP 配网 + 拉帧）已跑通的基础上，把配网主路径换成 BLE（ESP-IDF `wifi_provisioning` + 官方 App），SoftAP 网页保留为兜底。

## 目标

设备无 WiFi 凭据时，优先用 **BLE 配网**（手机装 Espressif 官方 "ESP BLE Provisioning" App 发送 SSID/密码）；BLE 超时无人配则**自动回退到现有 SoftAP 网页**配网。任一方式拿到凭据后存 NVS、重启走 STA 连接。现阶段为本人调试，BLE 客户端用官方 App；微信小程序作为未来体验升级（见末尾）。

## 背景与约束

- 现状：`wifi_prov.c` 实现「无凭据→SoftAP 网页(192.168.4.1 表单)→存 NVS namespace `inkpulse`→重启 STA」。拉帧客户端 `frame_client.c` 已跑通。
- ESP32-S3 支持 BLE；ESP-IDF `wifi_provisioning` 组件提供成熟的 BLE 配网（含官方 App、加密、PoP）。
- **体积约束**：当前 `inkpulse.bin` ≈922K，factory app 分区仅 1MB，余量 ~10%。加 BLE 协议栈必然超分区 → 必须改分区表。

## 配网状态机

统一入口 `wifi_connect_or_provision()`：

```
上电 → 读 NVS namespace "inkpulse" 的 ssid/pass
  ├─ 有凭据 → STA 连接（现有逻辑不变）
  └─ 无凭据 → 进入配网:
       ① 起 BLE 配网 (wifi_provisioning + NimBLE)，广播名 "PROV_InkPulse"
          官方 App 连接、发 SSID/密码
       ② 等待 BLE 配网，超时 180s(可调) 无人配成功
          → 停 BLE prov，起 SoftAP 网页兜底(现有 192.168.4.1 表单)
       ③ 任一方式拿到凭据 → 存回 "inkpulse" namespace → esp_restart()
          → 重启后走"有凭据"分支 STA 连接
```

**顺序而非并存**：BLE 配网期为 STA+BLE 共存，SoftAP 兜底需切到 AP 模式，两者 WiFi 模式冲突，故先 BLE、超时再 SoftAP。

## 凭据存储统一

两套配网都把结果写到**同一** NVS namespace `"inkpulse"` 的 `ssid`/`pass`，启动判断只读这一处（现有 `load_creds` 不变）。BLE 侧在 `WIFI_PROV_CRED_RECV` 事件回调里拿到凭据写入该 namespace。BLE 只是新增一个「写凭据来源」，与 SoftAP 对等，启动逻辑零改动。

## BLE 配网细节

- 组件：`wifi_provisioning`，scheme = `wifi_prov_scheme_ble`，协议栈 **NimBLE**（省 flash/RAM）。
- 安全：`security1` + 固定 PoP 口令 `"inkpulse"`（App 内输入一次）。如需更省事可降 `security0`（明文无口令）。
- 广播名：`PROV_InkPulse`。
- 客户端：Espressif 官方 "ESP BLE Provisioning"（iOS/Android 应用商店免费）。
- 配网成功事件后存凭据 + `esp_restart()`，不直接复用组件自动连接的状态，保持与现有「重启→STA」一致。

## SoftAP 兜底

保留现有 `wifi_prov.c` 的 SoftAP 网页（热点 `InkPulse-Setup` / 192.168.4.1 表单 / 存 NVS）。仅由 BLE 超时触发进入。

## 分区表 / 构建配置（硬前提）

新增自定义分区表 `partitions.csv`（8MB flash，app 扩到 2MB）：
```
# Name,   Type, SubType, Offset,   Size
nvs,      data, nvs,     0x9000,   0x6000
phy_init, data, phy,     0xf000,   0x1000
factory,  app,  factory, 0x10000,  0x200000
```
`sdkconfig.defaults` 追加：
```
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
CONFIG_BT_ENABLED=y
CONFIG_BT_NIMBLE_ENABLED=y
```

## 文件改动

| 文件 | 改动 |
|---|---|
| `partitions.csv` | 🆕 自定义分区表（app 2MB） |
| `sdkconfig.defaults` | 启用 NimBLE/BT + 自定义分区表 |
| `main/ble_prov.c/.h` | 🆕 BLE 配网模块（起停 `wifi_provisioning`、事件回调写 NVS `inkpulse`） |
| `main/wifi_prov.c` | 改 `wifi_connect_or_provision`：编排 BLE→超时→SoftAP；STA / SoftAP 网页 / NVS 保留 |
| `main/net_config.h` | 加 `PROV_BLE_NAME`、`PROV_POP`、`PROV_BLE_TIMEOUT_S` 常量 |
| `main/CMakeLists.txt` | REQUIRES 加 `wifi_provisioning`、`bt` |
| `software/firmware/README.md` | 配网说明：官方 App 名 + PoP + 兜底流程 |

把 BLE 独立成 `ble_prov.c/.h`，`wifi_prov.c` 只做编排，保持单一职责。

## 屏幕提示

配网期保持现有**白屏**，不在固件里画配网文字（固件无字体渲染，自实现位图字体不值当——YAGNI）。提示靠串口日志 + App 扫描发现设备。

## 错误处理

- BLE prov 启动失败 → 直接回退 SoftAP。
- BLE 超时（180s）无成功事件 → 停 BLE、起 SoftAP。
- 配网拿到的凭据为空/异常 → 不写 NVS，继续等待/回退。
- 重启后 STA 连不上（凭据错）→ 现有逻辑：连接超时再次进入配网。

## 验证方式（固件无单元测试）

1. 编译通过（含新分区表、NimBLE），`inkpulse.bin` ≤ 2MB 分区。
2. 官方 App BLE 配网跑通：扫描到 `PROV_InkPulse` → 输 PoP → 发 SSID/密码 → 设备重启连 WiFi → 拉帧上屏。
3. 兜底验证：BLE 阶段不配，等 180s → SoftAP `InkPulse-Setup` 出现 → 网页配网成功。
4. 重启后正常拉帧（与现有 STA 流程一致）。

## 未来增强：微信小程序配网（待办）

用微信小程序的 BLE 能力替代官方 App 配网：
- **动机**：人人有微信、免装陌生 App，配网体验更好。
- **成本**：纯本地蓝牙、无服务端 → 无服务器/流量费；微信侧个人主体注册免费（认证视权限需求，年费几十元级）；主要成本是**开发小程序端 BLE 配网逻辑 + 微信注册/审核流程**。
- **触发时机**：从「本人调试」转向「给普通用户的成品配网体验」时升级。
- 板子端 BLE GATT 协议需与小程序端对齐（可沿用 `wifi_provisioning` 的 protocomm 协议，或自定义简化 GATT）。
