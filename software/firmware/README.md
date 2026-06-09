# InkPulse 固件（ESP32-S3 + UC8179 7.5" BWR 墨水屏）

阶段一：把屏驱动通（清屏 + 测试图案）。不联网。

## 环境

ESP-IDF v5.3.2 装在 `~/esp/esp-idf`，Python 走 conda 环境 `espidf`(py3.11)。
每开一个新终端先激活（顺序不能反）：

```bash
source ~/miniforge3/etc/profile.d/conda.sh && conda activate espidf
. ~/esp/esp-idf/export.sh
```

> 国内网络：工具链已走 `dl.espressif.cn` 镜像、源码走 gitee。`git lfs` 操作前需 `unset http_proxy https_proxy`（本工程不涉及 lfs）。

## 构建 / 烧录 / 看日志

```bash
cd software/firmware
idf.py set-target esp32s3      # 首次
idf.py build
idf.py -p /dev/cu.usbmodem5C682090591 flash monitor   # Ctrl+] 退出 monitor
```

## 引脚映射（原理图确认）

| 信号 | GPIO | | 信号 | GPIO |
|---|---|---|---|---|
| SCL(CLK) | 41 | | DC | 39 |
| SDA(MOSI) | 42 | | RES(RST) | 38 |
| CSB(CS) | 40 | | BUSY_N | 37 |

HTU21D: SCL=GPIO2, SDA=GPIO1（阶段一不涉及）。

## 当前行为（main.c）

启动 → `epd_init` → 清屏(白) → 依次显示 白/黑/红/上黑下红/棋盘（各停 4s）→ 深睡。

观察重点：
1. 清屏能否全刷成功（关键里程碑）
2. "红"图案是否真红——验证红 plane 极性（0x13 的 `1=红`）；若显示成白则极性相反，需在驱动里反转红 plane
3. 上黑下红 / 棋盘——验证原点在左上、行方向、X 字节序无错位

详见 `../docs/superpowers/plans/2026-06-09-inkpulse-firmware-driver.md` 的 bring-up 排查清单。
