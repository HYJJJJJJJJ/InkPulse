# BOOT 按键(GPIO0)：短按刷新 + 长按配网

日期：2026-06-12
状态：待评审

## 背景与目标

板载 BOOT 键（GPIO0，低电平有效，内部上拉）接入固件，赋予两个手势：
- **短按** → 手动刷新（立即拉新帧刷屏，不等下次定时 600s）。
- **长按** → 重新配网（清 NVS WiFi 凭据 + 重启进 BLE/SoftAP 配网，换 WiFi 不用接串口擦 NVS）。

双击切换显示本期不做（预留）。

## 设计

### ① 手势识别（新 component `ip_button`）
- GPIO0 配置输入 + 内部上拉，低=按下。
- 一个 FreeRTOS task 轮询（20ms 周期）+ 消抖，识别：
  - **短按**：按下→释放，总时长 `< 1000ms`。
  - **长按**：持续按住 `≥ 3000ms`，触发即回调（不等释放）。
- 接口：`button_init(on_short_cb, on_long_cb)`，识别到手势调对应回调。

### ② 动作（main 接回调）
- **短按 → 刷新**：`xTaskNotify` 主循环，打断其等待，立即 `ch_fetch` + 刷屏。
- **长按 → 配网**：`creds_clear()` 清 NVS 的 ssid/pass + `esp_restart()` → 开机无凭据走配网流程。

### ③ 主循环改造
- 现有 `vTaskDelay(next*1000)` → `ulTaskNotifyTake(timeout=next*1000)`，短按 notify 时提前唤醒（其余超时行为不变）。

### ④ `ip_provisioning` 加 `creds_clear()`
- `nvs_erase_key("ssid"/"pass")` + commit（只清凭据，hub 地址 key 保留）。

## 开机下载模式注意

GPIO0 是 BOOT 键：**开机瞬间按住会进下载模式**（bootloader 行为，不进 app）。本功能只在 app 运行时检测，不受影响；用户开机别按住即可，运行中长按正常配网。实现里 button task 在 app 启动后才创建，天然规避。

## 测试

- 手势识别核心抽成纯函数 `gesture_step(state, level, now_ms) -> event`，逻辑可推理验证（项目无 C 单测框架，主要靠真机）。
- 真机：短按 → 屏立即刷新（日志 fetch 提前）；长按 ≥3s → 设备重启进配网（广播 PROV_InkPulse）。

## 落地顺序

1. `ip_button` component（GPIO0 + 手势 task + 回调）。
2. `ip_provisioning`：`creds_clear()`。
3. `main`：主循环改 notify 等待 + 注册短按/长按回调。
4. 真机验证：短按刷新；长按进配网。

## 风险

- 长按阈值 3s / 短按 1s 凭手感，真机可微调。
- 短按打断刷新若恰逢上一次刷新未完成（e-ink 21s），需让 fetch/show 串行（主循环单线程本就串行，notify 只是提前唤醒，安全）。
