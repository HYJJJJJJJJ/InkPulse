# SSD1677 局部刷新（整屏快波形）设计

- 日期：2026-06-16
- 屏型：4.2″ SSD1677 BW（`bw_426`，480×800 竖版，控制器 RAM 800×480）
- 方案：**A — 整屏快波形局刷**（纯固件；区域脏矩形优化留二期，不在本 spec 范围）
- 关联：[2026-06-15 四寸屏支持设计](./2026-06-15-inkpulse-4.2inch-screen-support-design.md)

## 1. 背景与目标

SSD1677 当前驱动只有**全刷**（`0x22 0xF7 + 0x20`），每次刷新整屏黑白翻转一下（约 1.2s、有黑闪），且只写 `0x24`（新 RAM）、从不写 `0x26`（旧 RAM）。物理屏支持局部刷新，需把它用起来。

**目标**（按优先级）：

1. **消除黑闪** —— 内容变化时画面平滑切换，不再整屏翻转。
2. **刷新更快** —— 局刷快波形把单次刷新从 ~1.2s 降到 ~0.3s 量级。
3. **支持高频更新** —— 时钟可逐分钟走字，不担心伤屏/频繁黑闪。

**非目标**（本期不做）：

- 脏矩形「只刷变化区域」（方案 B）。整屏快波形已能达成上述 3 个目标；区域优化收益边际、真机调试量大，留二期。
- 灰阶/三色。本屏纯黑白。

## 2. 总体方案

整屏局刷：每次刷新仍把整帧写入 `0x24`，但用**快波形**做更新（差异翻转、不闪、快），并维护 `0x26` 旧 RAM 作为局刷基准。为抑制 e-ink 局刷固有的残影累积，周期性穿插一次**全刷**洗净。

刷新间隔（设备多久拉一次帧）**已经可配**（`refresh_periodic_s` ∈ RUNTIME_FIELDS，Settings 页「刷新间隔(秒)」，固件经 `X-Next-Refresh` 读取、下限 30s）。本期仅把 Config 默认值 600→60（不影响已存 `runtime.json`，老装置仍按其存值，用户可在网页改）。

**改动范围**：固件为主（驱动 + 主循环），hub 仅改一个默认常量。**对 7.5″ UC8179 零回归**。

## 3. 组件设计

### 3.1 驱动 `components/ip_display/src/ssd1677.c`

新增局刷路径，与现有全刷并存：

- **`ssd1677_update_partial(void)`** —— 快波形更新。
  - 首选 OTP 局刷：局刷边框设定（`0x3C`）→ `0x22 = 0xCF` → `0x20` → `wait_busy`。
  - 真机若 OTP 局刷无效/有重影，回退到自定义 LUT：经 `0x32` 写入手调局刷波形表（真机 bring-up 决定，见 §6）。
- **维护 `0x26` 旧 RAM** —— 局刷靠 `0x24`(新) 与 `0x26`(旧) 的差异翻转像素。约定：**每次更新（全刷或局刷）完成后，把刚显示的整帧再写入 `0x26`**，保证下一次局刷的基准 = 当前屏上内容。封装为 `ssd1677_sync_old_ram(const uint8_t *plane)`（行式流写，复用现有 `ssd1677_ram_row` 极性逻辑，目标寄存器 `0x26`）。
- 保留 **`ssd1677_update_full()`** 不变（周期洗残影 + 兜底）。
- `disp_show()` 不变（写 `0x24`）。

实现注意：`0x26` 写入同样需 set RAM counter（`0x4E/0x4F`）后发 `0x26`，与 `0x24` 流程对称；行缓冲复用 100B，不新增整屏 static（延续行式流写、不撑 DRAM 的既有约束）。

### 3.2 接口 `components/ip_display/include/ip_display/display.h`

`display_if_t` 增加可空成员：

```c
void (*refresh_partial)(void);   // 局刷; 为 NULL 表示驱动不支持(回退全刷)
```

- SSD1677 驱动填 `refresh_partial = ssd1677_update_partial`。
- UC8179 驱动**不填**（保持 NULL）→ 主循环回退全刷 → 7.5″ 零回归。
- `refresh`（全刷）语义不变。

### 3.3 主循环 `main/main.c`

刷新决策：内容变化时默认局刷，下列三种情况**强制全刷**（防残影 / 保正确性）：

1. **开机首帧** —— 上电后第一次出图走全刷（建立干净基准 + 同步 `0x26`）。
2. **离线→在线恢复** —— 网络恢复重新出图时全刷（期间可能多次未刷，基准不可信）。
3. **每 N 次局刷** —— `N = 30`。局刷计数到 30 触发一次全刷洗残影，计数清零。

实现：

- 维护 `static int s_partial_count;`，`s_partial_count` 计已连续局刷次数。
- 选择函数：
  ```
  bool force_full = first_frame || recovered_online || (s_partial_count >= 30);
  if (disp->refresh_partial && !force_full) { disp->refresh_partial(); s_partial_count++; }
  else { disp->refresh(); s_partial_count = 0; }
  ```
- `disp->show(frame)` 仍在 refresh 之前；mark_offline 叠加红/黑叉的流程不变（叉变化也属内容变化，照常局刷或被三触发收编为全刷）。
- `first_frame`/`recovered_online` 的判定复用主循环现有的 `online` 状态机：`first_frame` 是循环内**首次出图**（初始 `true`，第一次走 refresh 后置 `false`）；`recovered_online` 即 `now_online && !online` 的离线→在线沿。
- 启动时的 `disp->clear()` 把 `0x26` 同步为空白基准；但**循环内首次内容帧仍强制全刷**（`first_frame`），用真实内容重建 `0x26` 基准——二者不矛盾：clear 建空白基准、首帧全刷建内容基准。
- `N = 30` 以具名常量定义（`#define SSD_PARTIAL_BEFORE_FULL 30`），便于真机调。

### 3.4 hub

- `inkpulse_hub/config.py`：`refresh_periodic_s` 默认 `600 → 60`。其余不动（字段、Settings 页、`X-Next-Refresh` 下发链路均已就绪）。
- 不改协议、不改渲染、不动 web 构建。

## 4. 数据流

```
设备主循环:
  GET /frame (If-None-Match: ETag)
    ├─ 304 不变 → 不刷 (省刷新)
    └─ 200 新帧 → disp.show(写 0x24)
                  → force_full? 全刷 : 局刷
                  → 同步 0x26 = 当前帧
  等待 X-Next-Refresh(默认60s, 下限30s); 期间 10s 轮询 refresh-token / BOOT 短按可提前
```

## 5. 测试策略

### 5.1 编译可验证

- 两种 panel 变体（UC8179 / SSD1677）均编译通过（IDF v5.4.1）。
- UC8179 路径 `refresh_partial == NULL`，确认回退全刷、无行为变化。

### 5.2 selftest 扩展（真机肉眼校准）

在 `ssd1677_selftest` 增加局刷序列：

1. 全刷一张基准图案。
2. 连续局刷 ~35 次：每次只移动一个方块/递增一个计数字样。
3. 观察并记录：
   - 局刷**不闪**（无整屏黑白翻转）；
   - 连续局刷后是否出现可见**残影**累积；
   - 到第 30 次时触发全刷、是否**洗净**残影；
   - `0x26` 同步是否正确（无错位/重影）。

### 5.3 hub

- 已有 `refresh_periodic_s` 链路有测试覆盖；默认值改动补一条断言（默认 60）。

## 6. 真机 bring-up 校准清单

1. **局刷波形**：OTP `0x22=0xCF` 局刷能否直接出图、不闪、无重影？
   - 行 → 进入「自定义 LUT」分支：照 SSD1677 手册局刷波形经 `0x32` 写入，示波器/肉眼调到不闪不残。
2. **0x26 同步**：局刷基准正确？关掉同步会出现「旧内容不消」即可反证。
3. **残影阈值 N**：30 次是否过多（残影明显）或过少（全刷太频繁）？真机定标，调 `SSD_PARTIAL_BEFORE_FULL`。
4. **局刷耗时**：实测 `wait_busy` 时长，确认 ~0.3s 量级。

## 7. 风险与兜底

- **最大风险：局刷波形**。OTP 局刷不一定开箱即用，可能需手调 LUT（与当初全刷 bring-up 同性质的真机环节）。
  - **兜底**：`ssd1677_update_partial` 在波形未调通前可临时 `#define` 回退为全刷（`= ssd1677_update_full`），保证出图不受阻，波形调通再切回。
- **残影**：靠 §3.3 的每 30 次全刷兜底；真机不满意调 N。
- **零回归保障**：UC8179 `refresh_partial=NULL` + 主循环回退分支；hub 仅改默认常量，老装置 `runtime.json` 覆盖不受影响。
