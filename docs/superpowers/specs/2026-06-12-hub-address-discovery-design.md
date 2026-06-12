# Hub 地址通用化（自动发现 + 可配置）设计

日期：2026-06-12
状态：待评审

## 背景与问题

固件里 hub 服务器地址是编译期写死的宏：

```c
// components/ip_config/include/ip_config/net_config.h
#define HUB_FRAME_URL "http://172.27.73.66:8080/frame"
```

仅 `components/ip_channel/src/http_hub.c:66` 一处使用。换网络、换跑 hub 的机器、或 DHCP 导致 IP 变化，都要改源码重新编译烧录。本次把它通用化：换网/换 IP 不再需要重编重烧。

## 目标 / 非目标

**目标**
- 局域网内设备开机自动找到 hub，无需任何手动配置。
- 跨网/公网/云上场景，能给设备配一个固定 hub 地址并持久保存。
- 都失败时仍有编译默认值兜底，行为不比现在差。

**非目标**
- 不改 hub 的帧渲染/接口协议（路径仍是 `/frame?t=..&h=..`）。
- 不给 BLE 配网加自定义字段（YAGNI；BLE 用户靠 mDNS 自动发现，跨网时用 SoftAP 补配）。
- 不引入云端注册/反向通道等重型发现机制。

## 解析链（每次开机，按优先级）

设备启动联网后，按顺序解析出一个 **hub base URL**（形如 `http://<host>:<port>`，不含路径与 query）：

1. **mDNS 自动发现** — 查询服务 `_inkpulse._tcp.local`。命中则取第一条结果的 IP + 端口，拼成 base URL。超时约 1.5s。
2. **NVS 手动地址** — mDNS 未命中时，读 NVS namespace `inkpulse` 的 key `hub`（用户通过 SoftAP 表单配置）。非空则用。
3. **编译默认值** — 仍为空则用 `net_config.h` 的 `HUB_DEFAULT_BASE` 兜底（永远有值）。

解析出的 base URL 交给 `http_hub`，由它统一拼 `"%s/frame?t=%.1f&h=%.1f"`。任一级成功即停止；HTTP 拉取失败时保留上一帧（沿用现有行为）。

## 固件改动

- **`ip_config`（新增 hub 地址解析）**
  - 新增 `hub_addr_resolve(char *out, size_t n)`：实现上面三级链，封装 mDNS 查询 + NVS 读取 + 默认兜底。
  - `net_config.h`：把 `HUB_FRAME_URL` 改为 base 形式宏 `HUB_DEFAULT_BASE "http://172.27.73.66:8080"`（路径下沉到 http_hub）。
  - 依赖 `espressif/mdns`（新增 `idf_component.yml`）与 `nvs_flash`。
- **`ip_provisioning/creds_nvs.c`** — 新增 `hub_addr_load/ hub_addr_save`（同 namespace `inkpulse`，key `hub`），与现有 ssid/pass 并列。
- **`ip_provisioning/softap_prov.c`** — SoftAP 配网网页表单加一个**可选** “Hub 地址” 输入框；提交时若非空则 `hub_addr_save`。留空 = 仅靠 mDNS/默认。
- **`ip_channel/http_hub.c`** — 开机调用 `hub_addr_resolve` 得 base URL（缓存一次），URL 拼接改用它而非宏。

## hub 端改动（`software/hub/`）

- `pyproject.toml` 加依赖 `zeroconf>=0.130`。
- 启动时（uvicorn 起服务后）用 zeroconf 注册服务 `_inkpulse._tcp`，端口取自现有监听端口（默认 8080），实例名 `inkpulse-hub`。进程退出时注销。
- 服务地址用本机局域网 IP；端口/路径与现有 HTTP 服务一致。

## NVS schema

namespace `inkpulse`（已存在）：

| key  | 类型 | 含义 |
|------|------|------|
| ssid | str  | WiFi SSID（已有） |
| pass | str  | WiFi 密码（已有） |
| hub  | str  | 手动 hub base URL，如 `http://192.168.10.5:8080`（新增，可空/不存在） |

## 错误处理

- mDNS 组件初始化失败或查询超时：视为未命中，降级到下一级，仅 `ESP_LOGW`，不阻塞启动。
- NVS 无 `hub` key：正常情况，降级到默认。
- 三级链保证 base URL 必有值；后续 HTTP 失败沿用“保留上一帧 / 标记离线”逻辑。

## 测试

- **hub 端**：单测 zeroconf 注册成功且可被 `zeroconf` 客户端查询到 `_inkpulse._tcp`（实例名/端口正确）；注销后查询不到。
- **固件**：
  - `hub_addr_resolve` 三级降级逻辑（mDNS miss → NVS → 默认）以可注入的方式覆盖（mDNS/NVS 结果桩）。
  - 真机验证：宿舍 hub 跑起来后，设备开机日志应打印解析到的 base URL（来源标注 mDNS/NVS/默认）并成功拉帧。

## 落地顺序（第一步即“改掉”）

1. hub 端加 zeroconf 注册（先让 hub 可被发现）。
2. 固件加 `hub_addr_resolve`（mDNS + 默认两级先通），http_hub 接入 → 宿舍即可自动发现，立刻可用。
3. 再补 NVS 手动地址 + SoftAP 表单栏（跨网兜底）。
4. 真机回归：开机日志确认解析来源 + 成功拉帧。

## 风险

- 部分路由器/AP 开了 AP 隔离或屏蔽多播，mDNS 不通 → 此时退回 NVS 手动地址（正是保留该入口的原因）。
- `espressif/mdns` 为项目首个 managed component，`idf.py reconfigure` 需联网拉取一次。
