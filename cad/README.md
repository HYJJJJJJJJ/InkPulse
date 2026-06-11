# InkPulse 外壳（CAD）

3D 打印楔形桌面外壳的**参数化建模**与校验脚本。屏面相对桌面仰角 60°，三件式打印 + 螺丝装配，外加一块抽拉盖板。

> 完整设计依据（尺寸、PCB 机械接口约定、公差）见 [外壳设计文档](../docs/superpowers/specs/2026-06-03-inkpulse-enclosure-design.md)。

## 工具链

- **建模库**：[build123d](https://github.com/gumyr/build123d) 0.10.0（Python 参数化 CAD）
- **校验**：numpy + matplotlib（干涉/装配/质心）
- 环境：Python 3.11+

```bash
conda create -n cad python=3.11
conda activate cad
pip install build123d numpy matplotlib
```

## 生成模型

```bash
cd cad
python3 enclosure.py        # 生成四件套 + 装配体，导出到 output/
```

所有尺寸是 `enclosure.py` 顶部的具名变量（与设计文档 §9 一一对应），改参数重跑即可。

## 零件（output/）

| 件 | 文件 | 作用 | 打印姿态 |
|---|---|---|---|
| 前框 bezel | `bezel.{stl,step}` | 正面开视窗露可视区，唇边压玻璃黑边 | 正面朝下（前表面最平整） |
| 后盖 back cover | `back_cover.{stl,step}` | 压紧玻璃、保护背面、开 FPC 过线槽 | 平放 |
| 底座 base | `base.{stl,step}` | 楔形，装 70×50 PCB，60° 斜接前框，后壁开 Type-C 口 | 平放 |
| 抽拉盖板 lid | `lid.{stl,step}` | 底座底盖，导轨 + 卡扣 detent + 防滑横条 | 平放 |
| 装配体 | `assembly.step` / `assembly_shell.step` | 60° 仰角姿态总装（含 PCB 与屏参考） | — |

**装配关系**：玻璃从背面放入前框 → 垫 0.5mm 泡棉 → 后盖螺丝压紧 → 屏框组件在 60° 斜接缝与底座拼接 → PCB 用 M3 锁在底座螺柱（柱心 ±30,±20）→ FPC 从屏框底经后盖线槽折入底座接显示排座。

**打印工艺**：PLA/PETG，层高 0.2mm，3 圈壁，配合间隙 0.4mm，目标免支撑/极少支撑。

## 校验脚本

这些脚本读取真实 `hardware/PCB1.step` 做几何校验，确保外壳与 PCB 配合：

| 脚本 | 作用 | 输出 |
|---|---|---|
| `analyze_pcb.py` | 从 PCB STEP 提取外形/板厚/孔位/高元件/连接器位置 | 机械接口结论 |
| `fitcheck.py` | 把真实 PCB 放入底座，检查配合间隙、螺柱对孔、Type-C 对位 | `output/fitcheck.png` |
| `check_interf.py` | 装配体各零件两两干涉体积检测（>1mm³ 报冲突） | 干涉表 |
| `fpc_reach.py` | 装配姿态下屏 FPC 出线点 → PCB 显示排座的走线距离是否够弯折 | 距离报告 |
| `verify_v3.py` | v3（PCB 前移后）关键复验：FPC 跨度 / base∩PCB / lid∩PCB / 盖板余量 / 螺柱位 | 验证清单 |
| `render_preview.py` | 4 个零件 STL 渲染成预览图 | `output/preview_parts.png` |

## 关键参数（节选）

```
SCREEN: 170.20 × 111.20 × 1.25mm，可视区 163.20 × 97.92mm
PCB:    70.10 × 50.04mm，M3 孔位 (±30, ±20)，最高元件 ≈3.7mm（ESP32 模块）
外壳:   壁厚 2.5mm，唇厚 1.2mm，仰角 60°
底座:   宽大底脚板 130 × 90 × 4mm（抗后倾），两片 60° 斜墙在 ±63
Type-C: 朝后（+Y，背向用户），开口 10×4mm，中心离内底 ≈7.3mm
```

> PCB 机械接口以**外壳为基准、PCB 跟随**；坐标原点=板几何中心，已用 `fitcheck.py` 将真实 PCB STEP 放入底座校验通过。
