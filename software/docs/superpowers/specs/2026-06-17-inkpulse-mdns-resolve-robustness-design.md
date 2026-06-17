# InkPulse mDNS 解析健壮化设计

**日期**: 2026-06-17
**范围**: 纯固件改动，单文件 `software/firmware/components/ip_channel/src/http_hub.c`
**目标**: 板子能稳定经 mDNS 发现 hub，不再因一次应答丢失而永久降级到失效的编译默认地址。

## 背景与根因（已抓包确证）

真机现象：板子联网后日志 `mDNS 未发现 hub, 降级` → 用编译默认 `http://192.168.10.64:8080`，而 hub 实际在 `192.168.10.217:8080`，导致 `Connection reset`、永久离线。

系统化调试确证（非固件逻辑 bug，非 hub 配置错）：

| 环节 | 证据 | 结论 |
|---|---|---|
| hub mDNS 注册 | 本机 zeroconf 浏览到 `inkpulse-hub._inkpulse._tcp → 192.168.10.217:8080` | ✅ 注册成功、IP 正确 |
| 服务名匹配 | 两端均 `_inkpulse._tcp` | ✅ 一致 |
| 板子查询发出 | 多播抓包：板子 `192.168.10.68` 在 t=11.7s、12.8s **两次** PTR QUERY | ✅ 到达 hub 网段 |
| hub 应答发出 | 抓包：`192.168.10.217` **两次** RESP 139B | ✅ 应答了 |
| **应答回到板子** | 板子日志仍"未发现" | ❌ **断点** |

**根因**：mDNS 协议交互双方正常（板子查、hub 答），但 hub 的**多播应答没回到板子**。入站多播通（WSL 能收到局域网其它设备广播 + 抓到板子查询），断在**出站多播**（hub 应答 WSL → 物理局域网 → 板子）——WSL2 mirrored 网络出站多播 / 路由器多播转发的典型问题。

**固件放大后果**：`resolve_hub_base()` 仅在 `ch_init()` 开机时调用一次、2s 超时、单次、失败即永久降级（`s_base` 注释"ch_init 时确定一次"），运行期不再重查 → 一次应答丢失即永久卡死在失效的 `.64`。

## 设计

改动集中在 `http_hub.c`，三处：

### 改动 1 — 查询改单播应答（直击根因）

`resolve_hub_base()` 内的查询：

```c
// 原:
mdns_query_ptr("_inkpulse", "_tcp", 2000, 4, &res)
// 改为:
mdns_query_generic(NULL, "_inkpulse", "_tcp", MDNS_TYPE_PTR /*0x000C*/,
                   MDNS_QUERY_UNICAST, 2000, 4, &res)
```

请求 hub 以**单播**（普通 UDP 直发板子 IP，源 `.217` → 目的板子 IP）回应，绕过当前丢包的出站多播环节。`mdns_query_generic` 与 `MDNS_QUERY_UNICAST` 由 `espressif/mdns` 组件提供（已在 `idf_component.yml` 依赖中）。

### 改动 2 — 不永久降级 + 周期重试

- 新增文件内静态标志 `static bool s_hub_via_mdns = false;`（是否已通过 mDNS 命中地址）。
- 抽出 `try_mdns_resolve(void) -> bool`：只做单播 mDNS 查询，命中则写 `s_base` 并返回 `true`，否则返回 `false`、不改 `s_base`。
- `resolve_hub_base()`（开机首次）：依序 `try_mdns_resolve()` → NVS 手动地址 → 编译默认，并据 mDNS 是否命中设置 `s_hub_via_mdns`。
- `ch_fetch()` 开头加：
  ```c
  if (!s_hub_via_mdns) s_hub_via_mdns = try_mdns_resolve();
  ```
  只要还没用上 mDNS 地址就每轮再试一次，命中后即停（在线稳态零额外开销，不会反复查 mDNS）。

### 改动 3 — 离线重试间隔收短

`ch_fetch()` 中 `esp_http_client_perform` 失败（离线 / 连不上）时，将 `out->next_refresh_s` 设为 `30`（原 600），让主循环约 30s 后重试（含再查 mDNS），而非干等 10 分钟。一旦命中 hub 正常拉帧，仍采用 hub 下发的 `X-Next-Refresh`。

## 错误处理与回退

三级回退优先级不变：**mDNS（单播）> NVS 手动配 > 编译默认 `.64`**。mDNS 持续失败时，板子用默认地址显示离线叉，但每 ~30s 重试一次，hub 一旦可达即自愈。

## 验证方法与风险

**验证**（真机串口 + hub 侧）：
1. 烧录联网固件，串口应出现 `hub 经 mDNS 发现: http://192.168.10.217:8080`，随后 `fetch -> 新帧已刷 / 未变`（HTTP 200/304），屏上拉到内容、离线叉消失。
2. 失败时应看到约每 30s 一次的重试，而非 600s 沉默。

**风险**：单播能否命中取决于 hub 端 zeroconf 是否尊重查询的 QU（unicast-response）位并以单播回应。若真机验证后仍不命中（zeroconf 坚持多播应答），则证明此 WSL mirrored 环境下 mDNS 确实不可用，**回退到 NVS 手动配地址**（板子已有机制：SoftAP 配网页填 `http://192.168.10.217:8080` → 写 NVS）。该分支在真机验证结果出来后再决定，不在本次代码改动内。

## 不做（YAGNI）

- mDNS 成功地址缓存到 NVS：本机 IP 会漂、缓存易过期，引入失效逻辑收益有限，真需要再加。
- 不修改编译默认 `.64`（保留近期 revert "不写死本机临时 IP" 的意图）。
- 不引入新依赖。

## 改动文件清单

- 修改：`software/firmware/components/ip_channel/src/http_hub.c`（`resolve_hub_base` / 新增 `try_mdns_resolve` / `ch_fetch`）

## 测试说明

固件 C 逻辑强依赖 esp-mdns 与真实网络栈，无现成单测框架可隔离。本次以**真机集成验证**为准：烧录后观察串口日志与屏幕行为（见"验证方法"），并可在 hub 侧用单播监听脚本交叉确认应答方向。
