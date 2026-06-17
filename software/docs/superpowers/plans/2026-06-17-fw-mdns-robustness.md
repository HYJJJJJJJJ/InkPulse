# mDNS 解析健壮化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让板子经 mDNS 单播应答稳定发现 hub，且失败后周期重试而非永久降级到失效的编译默认地址。

**Architecture:** 纯固件改动，全部集中在 `components/ip_channel/src/http_hub.c`。把 mDNS 查询从多播 PTR 改为单播应答（`MDNS_QUERY_UNICAST`）绕过出站多播丢失；把"开机解析一次"改为"未命中 mDNS 前每轮 fetch 重试"，并把离线重试间隔从 600s 收短到 30s。三级回退优先级（mDNS > NVS > 编译默认）不变。

**Tech Stack:** ESP-IDF v5.4.1, `espressif/mdns` 组件, C。构建经 `software/firmware/build.sh`（自动 source `IDF_PATH`）。

> **测试说明**：固件 C 逻辑强依赖 esp-mdns 与真实网络栈，无现成单测框架可隔离。本计划以**编译通过**（每个代码任务后）+ **真机串口集成验证**（Task 3）为验证手段，替代单元测试。这是经过权衡的有意决定，非偷懒。

> **环境前提**（执行机已具备，验证时确认）：
> - IDF: `IDF_PATH=$HOME/esp/v5.4.1/esp-idf`
> - 串口: `/dev/ttyACM0`（usbipd 已 attach，用户在 dialout 组）
> - hub 在 `192.168.10.217:8080`（systemd `inkpulse-hub.service` 运行中），mDNS 已注册 `_inkpulse._tcp`

---

## File Structure

- 修改：`software/firmware/components/ip_channel/src/http_hub.c`
  - 新增静态标志 `s_hub_via_mdns`
  - 新增函数 `try_mdns_resolve()`（只做单播 mDNS 查询）
  - 重构 `resolve_hub_base()`（复用 `try_mdns_resolve`）
  - `ch_fetch()` 加未命中时周期重试 + 离线缩短 `next_refresh_s`

单文件改动，无新增文件、无新依赖（`mdns.h` 已 include，`espressif/mdns` 已在 `idf_component.yml`）。

---

## Task 1: 单播 mDNS 查询 + 不永久降级的解析逻辑

**Files:**
- Modify: `software/firmware/components/ip_channel/src/http_hub.c`（替换 `resolve_hub_base`，约 53-84 行）

- [ ] **Step 1: 替换解析逻辑**

把现有的 `s_base` 声明（约 53-54 行）与 `resolve_hub_base()`（约 56-84 行）整段替换为：

```c
// 解析出的 hub base 地址(http://IP:port, 不含 /frame)
static char s_base[128] = "";
// 是否已通过 mDNS 命中 hub 地址; 命中后停止周期重查(见 ch_fetch)
static bool s_hub_via_mdns = false;

// 只做 mDNS 单播查询: 命中则写 s_base 返回 true, 否则不动 s_base 返回 false。
// 用单播应答(QU)请求 hub 直接单播回 IP, 绕过出站多播 —— 部分网络(WSL2 mirrored /
// 路由器多播转发)下 hub 的多播应答回不到设备, 单播可直达。
static bool try_mdns_resolve(void)
{
    // mdns_init 只能成功调用一次; 周期重试会多次进来, 故用守卫(否则第二次
    // 返回 ESP_ERR_INVALID_STATE, 查询永远不执行)。
    static bool s_mdns_inited = false;
    if (!s_mdns_inited) {
        if (mdns_init() != ESP_OK) return false;
        s_mdns_inited = true;
    }
    mdns_result_t *res = NULL;
    if (mdns_query_generic(NULL, "_inkpulse", "_tcp", MDNS_TYPE_PTR,
                           MDNS_QUERY_UNICAST, 2000, 4, &res) == ESP_OK && res) {
        for (mdns_ip_addr_t *a = res->addr; a; a = a->next) {
            if (a->addr.type == ESP_IPADDR_TYPE_V4) {
                snprintf(s_base, sizeof(s_base), "http://" IPSTR ":%u",
                         IP2STR(&a->addr.u_addr.ip4), res->port);
                mdns_query_results_free(res);
                ESP_LOGI(TAG, "hub 经 mDNS 发现: %s", s_base);
                return true;
            }
        }
        mdns_query_results_free(res);
    }
    return false;
}

// 解析优先级: mDNS 自动发现 > NVS 手动配 > 编译默认。结果写入 s_base。
// 开机调一次; 未命中 mDNS 时由 ch_fetch 周期重试。
static void resolve_hub_base(void)
{
    if (try_mdns_resolve()) { s_hub_via_mdns = true; return; }
    ESP_LOGW(TAG, "mDNS 未发现 hub, 降级");
    // 2) NVS 手动地址
    if (hub_addr_load(s_base, sizeof(s_base))) {
        ESP_LOGI(TAG, "hub 经 NVS 手动配置: %s", s_base);
        return;
    }
    // 3) 编译默认兜底
    strlcpy(s_base, HUB_DEFAULT_BASE, sizeof(s_base));
    ESP_LOGI(TAG, "hub 用编译默认: %s", s_base);
}
```

- [ ] **Step 2: 编译验证**

Run: `IDF_PATH=$HOME/esp/v5.4.1/esp-idf bash /home/zqx/workspace/InkPulse/software/firmware/build.sh build 2>&1 | tail -5`
Expected: `Project build complete` / `inkpulse.bin binary size ...`（无编译错误）。

> 若报 `MDNS_QUERY_UNICAST`/`mdns_query_generic` 未声明：确认 `#include "mdns.h"` 在文件顶部（已存在于第 7 行）。

- [ ] **Step 3: Commit**

```bash
cd /home/zqx/workspace/InkPulse
git add software/firmware/components/ip_channel/src/http_hub.c
git commit -m "feat(fw/net): mDNS 查询改单播应答 + 抽出 try_mdns_resolve(不永久降级)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: ch_fetch 周期重试 + 离线缩短重试间隔

**Files:**
- Modify: `software/firmware/components/ip_channel/src/http_hub.c`（`ch_fetch`，约 98-166 行）

- [ ] **Step 1: 加未命中时的周期重试**

在 `ch_fetch()` 函数体最开头（当前 `out->changed = false;` 那一行之前）插入：

```c
    // 还没用上 mDNS 地址(在 NVS/默认降级地址上)就每轮再试一次单播查询;
    // 命中即置位、之后不再查(在线稳态零额外开销)。必须在拼 url(用 s_base)前。
    if (!s_hub_via_mdns) s_hub_via_mdns = try_mdns_resolve();

```

此后紧接原有的：
```c
    out->changed = false;
    out->next_refresh_s = 600;
```

- [ ] **Step 2: 离线时缩短重试间隔**

找到 `esp_http_client_perform` 失败的 `else` 分支（当前约 154-156 行）：

```c
    } else {
        ESP_LOGW(TAG, "http perform 失败(离线?), 保留上一帧");
    }
```

改为：

```c
    } else {
        ESP_LOGW(TAG, "http perform 失败(离线?), 保留上一帧");
        s_next = 30;   // 离线: 缩短重试间隔(下轮含再查 mDNS), 而非干等默认 600s
    }
```

> `s_next` 在请求开头被重置为 600（约 123 行），成功 200 时由 `X-Next-Refresh` 经 `on_evt` 覆盖；这里仅在离线分支改它。函数末尾 `out->next_refresh_s = s_next;`（约 159 行）会带出。固件主循环对 `next < 30` 钳制到 30（`main.c:178`），故 30 正好不触发钳制。

- [ ] **Step 3: 编译验证**

Run: `IDF_PATH=$HOME/esp/v5.4.1/esp-idf bash /home/zqx/workspace/InkPulse/software/firmware/build.sh build 2>&1 | tail -5`
Expected: `Project build complete`（无编译错误）。

- [ ] **Step 4: Commit**

```bash
cd /home/zqx/workspace/InkPulse
git add software/firmware/components/ip_channel/src/http_hub.c
git commit -m "feat(fw/net): 未命中 mDNS 时每轮 fetch 重试, 离线重试间隔 600s→30s

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 真机集成验证

**Files:** 无代码改动（仅烧录与观测）。

- [ ] **Step 1: 确认环境就绪**

Run:
```bash
ls /dev/ttyACM0 && curl -s -m 3 -o /dev/null -w "hub .217 -> %{http_code}\n" http://192.168.10.217:8080/health
```
Expected: `/dev/ttyACM0` 存在；`hub .217 -> 200`。
> 若串口缺失：在 Windows 侧 `usbipd attach --wsl --busid <CH343 的 BUSID>`。若 hub 非 200：`sudo systemctl restart inkpulse-hub`。

- [ ] **Step 2: 烧录联网固件**

Run: `PORT=/dev/ttyACM0 IDF_PATH=$HOME/esp/v5.4.1/esp-idf bash /home/zqx/workspace/InkPulse/software/firmware/build.sh flash 2>&1 | tail -6`
Expected: `Hash of data verified.` / `Hard resetting via RTS pin...`

- [ ] **Step 3: 复位并读 40s 串口日志**

把以下脚本写入 `/tmp/read_ink.py` 并运行（非 root，复位板子触发开机解析）：

```python
import serial, time, sys
p = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
p.setDTR(False); p.setRTS(True);  time.sleep(0.12)
p.setDTR(False); p.setRTS(False); time.sleep(0.05)
p.reset_input_buffer()
end = time.time() + 40
while time.time() < end:
    line = p.readline()
    if line:
        sys.stdout.write(line.decode('utf-8','replace').rstrip()+"\n"); sys.stdout.flush()
p.close()
```

Run: `timeout 60 /home/zqx/.espressif/python_env/idf5.4_py3.10_env/bin/python /tmp/read_ink.py 2>&1 | grep -aiE "mDNS|hub|fetch|next=|连|connect"`

- [ ] **Step 4: 判定结果**

**成功判据**（mDNS 单播生效，治本成立）：
- 出现 `hub 经 mDNS 发现: http://192.168.10.217:8080`
- 随后 `fetch -> 新帧已刷` 或 `未变/未刷`（HTTP 200/304），屏上离线叉消失、拉到内容。

**部分成功**（首次未中但自愈）：
- 首轮 `mDNS 未发现 hub, 降级`，但约 30s 后下一轮出现 `hub 经 mDNS 发现`（验证周期重试 + 30s 间隔生效）。

**风险分支**（单播仍不命中）：
- 若持续 `mDNS 未发现 hub, 降级`、始终连不上 → 说明 hub 端 zeroconf 未以单播回应、此环境 mDNS 不可用。**此时不再改本代码**，回退到 NVS 手动配地址：长按板子重新配网，SoftAP 页面填 `http://192.168.10.217:8080`（写入 NVS，优先级高于编译默认）。记录该结论到 spec 的"风险"小节。

- [ ] **Step 5: 验证通过后收尾**

确认成功或部分成功后，本计划代码改动已在 Task 1/2 提交。无额外 commit。
> 若走风险分支，无代码可改，按 Step 4 风险分支处理并如实汇报。

---

## 完成标准

- `http_hub.c` 编译通过；mDNS 查询走单播；未命中前每轮 fetch 重试；离线重试 30s。
- 真机串口确认板子经 mDNS 发现 `.217` 并正常拉帧（或经周期重试自愈）；若不可用则明确回退 NVS 并记录。
