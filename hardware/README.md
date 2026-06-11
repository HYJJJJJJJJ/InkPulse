# InkPulse 硬件（PCB）

InkPulse 驱动板的 **Altium Designer** 工程：ESP32-S3 主控 + UC8179 墨水屏接口 + HTU21D 温湿度 + USB-C 供电/烧录。板尺寸 **70.10 × 50.04mm**。

## 工程文件

| 文件 | 说明 |
|---|---|
| `PCB_Project.PrjPcb` | Altium 项目主文件（层定义/规则/工程树） |
| `PCB_Project.PrjPcbStructure` | 项目结构清单 |
| `Sheet1.SchDoc` | 原理图 |
| `PCB1.PcbDoc` | PCB 设计（布线/层/丝印） |
| `PCB1.step` | 3D STEP 导出，供 `cad/` 做装配/干涉校验 |

用 Altium Designer 打开 `PCB_Project.PrjPcb`。

## 元件库（submodule）

`library/` 是 git submodule，源 `https://github.com/HYJJJJJJJJ/AD_Library.git`，含 Altium PCB 封装库（`*.PcbLib`）与原理图库（`*.SchLib`）。首次克隆后初始化：

```bash
git submodule update --init --recursive
```

## 板上关键

| 模块 | 器件/说明 |
|---|---|
| 主控 | ESP32-S3 模组（YD-ESP32-S3），WiFi + BLE + PSRAM，板上最高元件 ≈3.7mm |
| 屏接口 | UC8179 4 线 SPI（SCL/SDA/CS/DC/RES/BUSY）+ 外部升压（GDR/RESE 驱动 MOSFET + 电感）；24-pin FPC 排座 |
| 传感器 | HTU21D 温湿度（I2C，地址 0x40，SCL=GPIO2 / SDA=GPIO1） |
| 供电 | USB-C 5V → LDO(CJ6107B33M) 3.3V，无电池 |
| 烧录 | CH343G USB 串口 + DTR/RTS 自动下载 |
| 输入 | BOOT / RESET 两键 + 1 个红色 LED |

**ESP32 ↔ 屏幕引脚映射**（固件 `main/pins.h`，以网表为准）：

| 信号 | GPIO | | 信号 | GPIO |
|---|---|---|---|---|
| SCL(CLK) | 41 | | DC | 39 |
| SDA(MOSI) | 42 | | RES(RST) | 38 |
| CSB(CS) | 40 | | BUSY_N | 37 |

## 机械接口（与外壳约定）

坐标原点 = 板几何中心；X = 长边方向；Y = Type-C(+) ↔ FPC(−) 方向。

| 项目 | 规格 | 位置 |
|---|---|---|
| 板外形 | 70.10 × 50.04，板厚 1.6mm | 中心对齐外壳 |
| 安装孔 ×4 | Φ3.2 (M3) | (±30, ±20) |
| Type-C 母座 16P | 供电/烧录 | Y− 长边中点 (0, −22)，**朝外壳后** |
| 24-pin 显示排座 | FPC 插座 | Y+ 长边中点 (0, +22)，朝屏 |

> 外壳为机械基准、PCB 跟随。详见 [外壳设计文档 §5](../docs/superpowers/specs/2026-06-03-inkpulse-enclosure-design.md)。`cad/analyze_pcb.py` 可从 `PCB1.step` 自动提取这些接口数据。
