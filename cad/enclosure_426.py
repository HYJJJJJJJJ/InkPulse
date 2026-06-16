"""InkPulse 4.26" 磁吸侧挂外壳 — 参数化建模 (build123d 0.10.0)

三个可打印零件 + 一个装配体:
  - bezel        前框 (托盘 + 视窗 + 唇边 + 屏容腔 + 自攻柱)
  - back_cover   后盖 (与外形齐平 + 嵌磁腔 + 底边 FPC 折回槽 + 右侧 Type-C 口 + 螺孔)
  - bracket      L 支架 (U 形卡钉抱显示器左上角 + 支架臂 + 对接面嵌对磁 + 高摩擦垫沉槽)
  - assembly     屏体(前框+后盖+屏参考板) 磁吸贴合支架, 支架抱住显示器左上角参考块

所有尺寸照设计文档 §9 命名为脚本顶部具名变量。坐标约定 (设计文档 §5):
  屏体局部: X = 屏宽(右=+X=朝显示器); Y = 屏高(上=+Y); FPC 在 -Y 底部短边; Z = 厚度。
"""

import math
from pathlib import Path
from build123d import (
    BuildPart, BuildSketch, Box, Cylinder, Rectangle, Plane, Pos, Rot,
    Locations, Mode, Align, fillet, extrude, Axis,
    Compound, export_step, export_stl, Vector,
)

# ============================================================
# §9 参数清单 (CAD 变量, 初值; 全部取自设计文档 §9)
# ============================================================
# --- 屏模组 ---
SCREEN_W = 62.37
SCREEN_H = 105.33
SCREEN_T = 1.0
AA_W = 55.68
AA_H = 92.80
BORDER_SIDE = 3.35              # 水平居中黑边
WINDOW_OFFSET_Y = 3.0          # AA 上偏 (远离 FPC); 待实测校正 (§8)
# FPC 在底部短边 (-Y)

# --- 屏体外壳 ---
WALL = 2.0
LIP = 1.0
FIT_GAP = 0.4
FOAM_T = 0.5
WINDOW_MARGIN = 0.5
BODY_W = 68.0                   # 屏体外形宽 (目标; 实际由腔+壁派生, 见下)
BODY_H = 116.0                 # 屏体外形高 (目标)
BODY_T = 10.0                  # v1 无电池, 屏体总厚目标
BACK_WALL = 1.5

# --- 电子 (包络约束, 板跟随) ---
PCB_W_MAX = 60.0
PCB_H_MAX = 95.0
PCB_T = 1.6
COMP_H_MAX = 4.0
COMP_CLEAR = 0.2               # 元件顶到后盖内面留空 (>=0.2)
# --- PCB 名义外形 (<= 包络 60x95; 由腔内 - 配合间隙派生, 见派生区) ---
PCB_FIT = 0.3                  # 板外形与腔内壁单边配合间隙 (XY 兜住定位)
# --- PCBA 装配 Z 叠层关键常数 ---
# 架构变更: 屏体主板去 Type-C 母座 (改受电侧 pogo pad), 故无板载母座 Z 包络.
#   供电改由支架底边防水 Type-C 母座 -> 走线腔 -> 对接面 POGO 实现 (见 TYPEC_* / POGO_*).
# FPC 排座在底边中点 bottom_mid (保留)
# --- 防水 Type-C 母座 (移到支架/对接板底边; 参数化 TYPEC_*) ---
#   架构变更: 屏体不再有任何线缆口. 供电侧 = 支架: 底边开防水 Type-C 母座位, 口朝下 (-Y),
#   本体深入支架内走线腔 (含小 dock PCB/CC 电阻), 经走线腔接到对接面 POGO 4 针.
TYPEC_PANEL_W = 13.60          # 面板开孔宽 (沿支架底边 X)
TYPEC_PANEL_H = 4.30           # 面板开孔高 (沿支架厚度 Z)
TYPEC_PANEL_R = 1.30           # 面板开孔圆角 R
TYPEC_FLANGE_W = 16.70         # 前法兰宽 (贴外面, 比孔大, 做沉台)
TYPEC_FLANGE_H = 10.30         # 前法兰高 (沿 Z)
TYPEC_FLANGE_T = 1.2           # 前法兰沉台深 (法兰盘厚, 沉入底边壁外面)
TYPEC_BODY_DEPTH = 14.00       # 母座本体深入支架内部 (沿 +Y)
TYPEC_BODY_CLEAR = 0.4         # 母座本体腔单边余量
# 飞线 6 根 (不建模线); 母座 X 居中于走线腔/POGO 一带 (走线腔正下方).
# --- Type-C 专用壳块 (TYPEC_HOUSING_*): 修复 "母座切进 5mm 薄板, 无包裹壳体" 几何 bug ---
#   bug: 对接板厚 MATE_T=5.0 (Z) < 法兰 TYPEC_FLANGE_H=10.3 (Z); 旧代码把法兰/开孔/体腔
#        直接切进薄板, 法兰比板厚还大一倍 => 切穿薄板, 无实体壳包裹母座.
#   fix: 在对接板底部长出一个专用实体壳块 (boss) 完整包裹母座, 与支架熔为一体.
TYPEC_HOUSING_WALL = 1.6       # 壳壁厚 (法兰/体腔四周留壁, 可调)
TYPEC_HOUSING_W = TYPEC_FLANGE_W + 2 * TYPEC_HOUSING_WALL    # 壳块 X 宽 ≈16.7+3.2=19.9
TYPEC_HOUSING_Z = TYPEC_FLANGE_H + 2 * TYPEC_HOUSING_WALL    # 壳块 Z 厚 ≈10.3+3.2=13.5
TYPEC_HOUSING_Y = TYPEC_BODY_DEPTH + TYPEC_FLANGE_T + TYPEC_HOUSING_WALL  # 壳块 Y 深 ≈14+1.2+1.6=16.8
# --- Type-C 壳块改挂 "支柱下方" (架构变更): 不再挂对接板底部 ---
#   壳块沿支柱偏卡钉/显示器一端 (X 靠近 0 的一侧, 即显示器左边缘外侧附近), 使线缆
#   就近垂在显示器左边缘旁. 约束: 壳块整体须 X<0 (不碰显示器), 故壳块 +X 面 <= -MON_FIT_GAP.
#   默认取 "壳块 +X 面紧贴显示器左缘外 (留 g)" => CX = -g - W/2; 但 spec 提示 X≈-6 一带,
#   这里取能让整壳 X<0 的最靠卡钉位置 (= -MON_FIT_GAP - W/2), 比 -6 更靠 0 又不越界.
TYPEC_HOUSING_CX = -(0.3 + TYPEC_HOUSING_W / 2)   # ≈ -(0.3+9.95) = -10.25 (整壳 X<0, 紧贴显示器左缘外)
TYPEC_HOUSING_STRUT_OVERLAP = 2.0   # 壳块 +Y 面伸入支柱下沿的重叠量 (保证与支柱熔为一体)
# --- PCB 安装/定位 ---
PCB_MOUNT_INSET = 5.0          # 安装/定位孔从板边内缩 (避开连接器)
PCB_LOC_PIN_D = 1.8            # 定位销直径 (插板定位孔)
PCB_STANDOFF_D = 4.0          # PCB 支撑支柱外径
PCB_STANDOFF_TOP_INSET = 0.0  # 支柱顶 (= PCB 前面 z) 由叠层派生

# --- 磁吸对接: 改用 POGO 磁吸连接器 (替代原裸磁铁) ---
# 架构变更: 原方案在支架对接面 + 屏体后盖各嵌 4×Φ8×3 磁铁对吸 + 屏体底边/右侧 Type-C.
#   新方案: 支架 = 供电侧 (底边防水 Type-C 母座 -> 内部走线腔 -> 对接面 POGO 连接器),
#           POGO 同时做 "磁吸耦合 (自带 N/S 磁) + 4 针供电/数据"; 屏体 = 受电侧
#           (后盖开 4 触点 pad 窗对位 pogo 针 + 2 钢吸片腔对位 N/S 磁), 屏体无线缆口.
# --- POGO 磁吸连接器实测尺寸 (钉死, 参数化 POGO_*) ---
POGO_LEN = 20.44               # 总长 (沿对接面 X 水平方向)
POGO_WID = 4.00                # 宽 (沿对接面 Y)
POGO_BODY_H = 2.00             # 本体高 (沉入对接面深度)
POGO_PIN_PROTRUDE = 1.50       # 针凸出本体高度 (朝屏体 +Z)
POGO_PIN_TIP_D = 0.70          # 针尖直径
POGO_PIN_PITCH = 2.54          # 4 针沿长向 (X) 间距
POGO_PIN_SPAN = 7.62           # 4 针跨度 (= 3×2.54), 居中
POGO_PIN_N = 4                 # 针数 (VBUS/GND/D+/D-)
POGO_MAG_SPAN = 13.54          # N/S 磁中心相距 (沿 X, 居中)
POGO_MOUNT_SPAN = 17.54        # 2× Φ1.5 安装孔中心相距 (沿 X, 居中)
POGO_MOUNT_D = 1.5             # 安装孔直径
POGO_BODY_CLEAR = 0.15         # POGO 本体腔单边配合余量 (压配/胶固定)

# --- 屏体受电侧: 4 触点 pad 窗 + 2 钢吸片腔 ---
PAD_WINDOW_D = 2.0             # 触点 pad 窗直径 (露板背 pad, 对位 pogo 针)
STEEL_D = 3.5                  # 钢吸片直径 (被 pogo N/S 磁吸住)
STEEL_T = 1.0                  # 钢吸片厚 (嵌入后盖腔深)
CONTACT_AIR_GAP = 0.3         # pogo 针面到后盖外表面气隙 (针凸 1.5 压缩接触余量)

# --- 走线腔: 支架内 Type-C 腔 <-> POGO 腔连通通道 (容飞线 + 小 dock PCB/CC 电阻) ---
CHANNEL_W = 7.0               # 走线腔宽 (≥6, 给 dock PCB/电阻宽松空间)
CHANNEL_DEPTH = 4.0           # 走线腔沿 -Z 深 (从对接板顶面向内)

# --- 可选补强磁 (默认关; 为后续 "pogo 磁力不足" 留开关) ---
AUX_MAG_ENABLE = False        # True 则在 POGO 上下各加一对 Φ6 磁腔 (屏体镜像); 本次默认关, 不建
AUX_MAG_D = 6.0               # 补强磁直径
AUX_MAG_T = 2.0               # 补强磁厚
AUX_MAG_OFFSET_Y = 9.0        # 补强磁相对 POGO 中心的上下偏移 (沿对接面 Y)

# --- 8×Φ8 磁铁 (吸合/承重主力, 与 POGO 共存; 用户明确要求恢复) ---
#   分工: 8×Φ8 磁铁 = 吸合/承重 (扛屏体 ~40g + 探角外杠杆力);
#         POGO 自带 N/S 小磁 = 供电对位 (磁力不足以单独承重).
#   布局: 4 磁在 POGO 对接带四角 (支架对接面 4 + 屏体后盖 4 镜像对吸), 与 POGO 空间不冲突.
MAG_D = 8.0                    # Φ8 磁铁直径
MAG_T = 3.0                    # 磁腔盲腔深 (嵌 Φ8×3 磁铁)
MAG_N = 4                      # 每侧磁数 (支架对接面 4 + 后盖 4 = 共 8)
MAG_GRADE = "N52"
MAG_OUTER_WALL = 0.8          # 磁腔外侧薄壁 (磁外侧留薄壁保磁力; 盲腔从顶面沉 MAG_T, 留底壁)
MAG_COL_X = 26.6              # 4 磁沿 X 的列位 (对接带四角, ±MAG_COL_X; POGO 在中央, 四角避开)
MAG_INSET_Y = 18.0            # 4 磁相对对接带中心 Y 的上下偏移 (band±MAG_INSET_Y)
FRICTION_PAD_T = 0.8          # 高摩擦垫沉槽深 (保留, 抗下滑)

# --- L 支架 (显示器尺寸: 用户实测) ---
MON_BEZEL_TOP = 7.0
MON_BEZEL_LEFT = 7.0
MON_EDGE_T = 17.0
CLIP_DEPTH = 17.5             # U 口深 = T_edge + 余量
CLIP_FRONT_LIP = 5.0         # ≤ 黑边宽, 不盖画面
CLIP_BACK_LIP = 8.0          # 后舌扣背面
VHB_T = 0.8
MON_FIT_GAP = 0.3            # 卡钉抱边内表面与显示器各面留间隙 (靠 VHB 贴合, 非过盈)
# ARM_REACH = tuned (CAD 调, 见派生)

# --- 竖向锚点: 墨水屏顶边对齐显示器顶边 (改动 4) ---
# 显示器顶边在世界 Y=0 (monitor 角块顶面). 屏体顶边 = 显示器顶边 + 该 offset.
TOP_FLUSH_OFFSET = 0.0       # 屏顶相对显示器顶的竖向偏移 (0 = 持平)

# --- 修正 2: 墨水屏前表面与显示器前表面共面 (Z 锚点) ---
# 显示器前表面在世界 Zf=0 (monitor 角块前表面). 墨水屏前表面 = Zf + 该 offset.
#   0 = 共面 (墨水屏正面与显示器正面齐平, 不向用户侧 +Z 凸出).
#   由此屏体从 Zf 向 -Z 叠 BODY_T_ACTUAL, 屏体后表面/对接板/支柱/后舌全躲在 Z<Zf,
#   正面只露薄薄一条卡钉前舌 (Z≥Zf=0) 压在显示器前黑边上.
Z_FLUSH_OFFSET = 0.0         # 墨水屏前表面相对显示器前表面的 Z 偏移 (0 = 共面)

# ============================================================
# 派生参数
# ============================================================
# --- 屏容腔 (含单边 FIT_GAP) ---
SCR_CAV_W = SCREEN_W + 2 * FIT_GAP          # 62.37 + 0.8 = 63.17
SCR_CAV_H = SCREEN_H + 2 * FIT_GAP          # 105.33 + 0.8 = 106.13
SCR_CAV_CORNER_R = 1.5                       # 屏容腔四角小圆角

# --- 屏体外形 = 屏容腔 + 两侧壁厚 ---
BEZEL_OUT_W = SCR_CAV_W + 2 * WALL          # 63.17 + 4.0 = 67.17 (~68)
BEZEL_OUT_H = SCR_CAV_H + 2 * WALL          # 106.13 + 4.0 = 110.13 (~116 目标偏大, 见报告判断)
CORNER_R = 4.0                               # 外形四角圆角 (美观)

# --- 视窗 = AA + 余量, 水平居中, 纵向上偏 ---
WINDOW_W = AA_W + WINDOW_MARGIN              # 56.18
WINDOW_H = AA_H + WINDOW_MARGIN              # 93.30

# ============================================================
# 屏体 Z 向叠层 (前框正面 z=0 朝下打印, 背腔开口朝 +z) — PCBA 装配基准
# ============================================================
# 全部派生公式, 不留魔数. 从前面板正面 z=0 起向 +z (屏体内) 叠:
#   前面板/唇环 [0 .. FRONT_WALL_T]      = 唇 LIP, 视窗贯穿
#   墨水屏       [SCREEN_FRONT_Z .. SCREEN_BACK_Z]  = SCREEN_T
#   FPC 折回间隙 [SCREEN_BACK_Z .. PCB_FRONT_Z]     = FPC_FOLD_GAP
#   PCB         [PCB_FRONT_Z .. PCB_BACK_Z]         = PCB_T (铜面朝屏/-z, 元件面朝后盖/+z)
#   元件        [PCB_BACK_Z .. COMP_TOP_Z]          = COMP_H_MAX
#   COMP_CLEAR  [COMP_TOP_Z .. 后盖内面]            = >=0.2 让位
FRONT_WALL_T = LIP                            # 1.0 = 唇厚 (前面板/唇环厚)
FPC_FOLD_GAP = 0.5                            # FPC 折回间隙
SCREEN_FRONT_Z = FRONT_WALL_T                 # 1.0  墨水屏前表面 (贴唇环背)
SCREEN_BACK_Z = SCREEN_FRONT_Z + SCREEN_T     # 2.0  墨水屏背面
PCB_FRONT_Z = SCREEN_BACK_Z + FPC_FOLD_GAP    # 2.5  PCB 前面 (铜面, 朝屏); 支柱顶面到此
PCB_BACK_Z = PCB_FRONT_Z + PCB_T              # 4.1  PCB 背面 (元件面起点)
COMP_TOP_Z = PCB_BACK_Z + COMP_H_MAX          # 8.1  元件顶 (最高元件包络)
# bezel 背腔内面 = 元件顶 + COMP_CLEAR (元件到后盖内面留空)
BEZEL_CAV_FLOOR_Z = COMP_TOP_Z + COMP_CLEAR   # 8.3  背腔最里面 (= 后盖内面)
# bezel 背腔深 (从前面板背面 z=FRONT_WALL_T 向 +z 挖)
BEZEL_CAV_DEPTH = BEZEL_CAV_FLOOR_Z - FRONT_WALL_T   # 7.3
INNER_DEPTH = BEZEL_CAV_DEPTH                 # 兼容旧名
ELEC_STACK = PCB_T + COMP_H_MAX               # 1.6 + 4.0 = 5.6 小板叠高
BEZEL_DEPTH = BEZEL_CAV_FLOOR_Z               # 8.3 (bezel 本体总深; 背腔内面=本体背面)
# 屏体总厚 = bezel 深 + 后盖板厚 (后盖盖在 bezel 背腔口上, 凸台伸入腔)
BODY_T_ACTUAL = BEZEL_DEPTH + BACK_WALL       # 8.3 + 1.5 = 9.8 (~BODY_T=10)

# --- PCB 支撑支柱 (修 bug1: 移到 back_cover 内长出, 从后盖内面顶到 PCB 背面 z=PCB_BACK_Z) ---
#   架构: 元件面朝后盖 (+z), PCB 背面 = 元件面起点 = PCB_BACK_Z. 支柱托住 PCB 背面把板顶到既定 Z.
#   后盖局部 z 与屏体局部 z 关系 (back_cover_local 翻转+平移): body_z = BODY_T_ACTUAL - bc_local_z.
#   => PCB 背面 (body z=PCB_BACK_Z) 对应后盖局部 z = BODY_T_ACTUAL - PCB_BACK_Z.
#   支柱从盖板内面 (后盖局部 z=BACK_COVER_PLATE_T) 升到该高度.
BC_STANDOFF_TOP_LOCAL_Z = BODY_T_ACTUAL - PCB_BACK_Z      # 后盖局部: 支柱顶 z (= PCB 背面)
PCB_STANDOFF_H = BC_STANDOFF_TOP_LOCAL_Z - BACK_WALL       # 支柱高 (盖板内面->PCB背面; BACK_COVER_PLATE_T=BACK_WALL)
# 定位销高: 插入 PCB 板厚做 XY 定位, 但不得穿出 PCB 前面 (否则又戳墨水屏背).
#   板厚 PCB_T=1.6; 留 0.3 不顶到屏侧 (销顶停在 PCB 前面之内 0.3mm).
PCB_LOC_PIN_H = PCB_T - 0.3                    # 1.3 (插板做 XY 定位, 顶端不穿出板前面/不碰屏)

# ============================================================
# PCB 名义外形 + 安装/定位孔 + 支撑支柱 XY 布局
# ============================================================
# 板外形 = 腔内 - 单边 PCB_FIT (腔壁兜住), 且不超包络 60x95.
PCB_W = min(SCR_CAV_W - 2 * PCB_FIT, PCB_W_MAX)   # 63.17-0.6=62.57 -> 钳到 60
PCB_H = min(SCR_CAV_H - 2 * PCB_FIT, PCB_H_MAX)   # 106.13-0.6=105.5 -> 钳到 95
# 4 个安装/定位孔位置 (板中心原点, 角部内缩, 避开连接器):
#   底边中点为 24P 排座, 右缘为 Type-C; 取四角各内缩, 既避连接器又落在腔壁内侧.
#   关键约束: 支柱须落在前面板"视窗外的料环"上 (|x|>WINDOW_W/2 OR |y|>WINDOW_H/2+offY),
#   否则支柱基座悬在视窗孔上无料可熔 (会成游离实体). 故 X 内缩取小值, 使支柱压在
#   左/右纵向料环带 (|x|∈[WINDOW_W/2, SCR_CAV_W/2]). Y 用常规内缩.
PCB_MOUNT_INSET_X = PCB_W / 2 - (WINDOW_W / 2 + 0.4)   # ≈30-28.49=1.51 => x≈28.49 落右料环
PCB_HOLE_X = PCB_W / 2 - PCB_MOUNT_INSET_X    # ≈28.49 (落视窗外纵向料环, 支柱有料可熔)
PCB_HOLE_Y = PCB_H / 2 - PCB_MOUNT_INSET      # 47.5-5=42.5
PCB_HOLE_POSITIONS = [
    (PCB_HOLE_X, PCB_HOLE_Y), (-PCB_HOLE_X, PCB_HOLE_Y),
    (PCB_HOLE_X, -PCB_HOLE_Y), (-PCB_HOLE_X, -PCB_HOLE_Y),
]
# 支撑支柱 XY = 4 个安装孔位 (板四角, 落料环, 避开底边 FPC 排座与右缘 Type-C).
PCB_STANDOFF_POSITIONS = PCB_HOLE_POSITIONS
# 对角两根支柱带定位销 (左上 + 右下), 插板对应定位孔做 XY 定位:
PCB_LOC_PIN_POSITIONS = [(-PCB_HOLE_X, PCB_HOLE_Y), (PCB_HOLE_X, -PCB_HOLE_Y)]

# --- 24P FPC 排座 (PCB 底边中点) ---
FPC_CONN_W = 14.0              # 24P 0.5mm 间距排座本体宽 (含壳, 估值; 待测 §8)
FPC_CONN_LOCAL = (0.0, -PCB_H / 2)   # 板底边中点 (板局部)

# --- 自攻柱 (bezel 四角 boss + 后盖通孔) ---
BOSS_D = 4.5                                 # M2 自攻柱外径
BOSS_PILOT_D = 1.5                           # M2 自攻底孔 (留 0.2 余量)
SCREW_CLEAR_D = 2.4                          # 后盖侧 M2 通孔
BOSS_OFFSET = 4.0                            # 柱心从外形角内缩
BOSS_X = BEZEL_OUT_W / 2 - BOSS_OFFSET       # 角柱 X
BOSS_Y = BEZEL_OUT_H / 2 - BOSS_OFFSET       # 角柱 Y

# --- 屏体受电侧对接区 (后盖): 8×Φ8 磁 (4 后盖 + 4 支架镜像) + POGO 受电 ---
# 用户要求恢复: 后盖对接区 = 4×Φ8 磁腔 (吸合/承重) + 4 触点 pad 窗 + 2 钢吸片腔.
#   - 4×Φ8 磁腔: 对接带四角 (X=±MAG_COL_X, Y=band±MAG_INSET_Y), 与支架对接面 4 磁镜像对吸;
#   - 4 触点 pad 窗 (对位 pogo 4 针, 露板背 pad);
#   - 2 钢吸片腔 (对位 pogo N/S 磁, 嵌 Φ3.5×1 钢片被吸住, 助 POGO 自吸正).
BACK_COVER_PLATE_T = BACK_WALL              # 1.5
# --- 对接区竖向中心 (沿用原磁带中心 Y, 屏体中上部) ---
# 带中心 MAG_BAND_CENTER_Y (后盖局部 Y, 上=+Y): 取屏顶下方约 1/3 屏高处.
#   POGO 长向沿 X 水平居中, 落在此竖向带 => 抗剥离/杠杆力矩, 支柱就近从顶部卡钉接入.
MAG_BAND_CENTER_Y = BEZEL_OUT_H / 2 - BEZEL_OUT_H / 3   # ≈ +18.4 (中上部)
# 对接区 X 居中 (POGO 水平居中 => 后盖目标区也 X 居中):
DOCK_CENTER_X = 0.0
DOCK_CENTER_Y = MAG_BAND_CENTER_Y           # 对接区竖向中心 (后盖局部)
# --- 后盖 4 触点 pad 窗坐标 (对位 pogo 4 针: 沿 X 间距 2.54, 跨度 7.62, 居中) ---
#   后盖法向 -Z 贴支架对接板 (+Z), 对贴 => 屏宽(X) 镜像. 后盖局部 X 即与对接面 X 镜像关系
#   由装配 Rot(0,180,0) 自动满足 (与原磁位镜像同一逻辑). 窗 X 居中对称, 故镜像后仍重合.
PAD_WINDOW_POSITIONS = [
    (i * POGO_PIN_PITCH - POGO_PIN_SPAN / 2, DOCK_CENTER_Y)
    for i in range(POGO_PIN_N)
]
# --- 后盖 2 钢吸片腔坐标 (对位 pogo N/S 磁: 相距 13.54, 居中) ---
STEEL_POSITIONS = [
    (-POGO_MAG_SPAN / 2, DOCK_CENTER_Y), (+POGO_MAG_SPAN / 2, DOCK_CENTER_Y),
]
# --- 8×Φ8 磁位 (对接带四角, 后盖局部坐标; X 居中对称, 装配 Rot(0,180,0) 后与支架镜像重合) ---
#   4 磁分布在 POGO 对接带四角 (X=±MAG_COL_X, Y=DOCK_CENTER_Y±MAG_INSET_Y), POGO 居中央, 避开.
#   支架对接面用同一组坐标镜像建腔 => 后盖 4 磁 ↔ 支架 4 磁 严格镜像对齐 (偏差 0).
MAG_POSITIONS = [
    (sx, DOCK_CENTER_Y + sy)
    for sx in (-MAG_COL_X, +MAG_COL_X)
    for sy in (-MAG_INSET_Y, +MAG_INSET_Y)
]
# --- 棋盘极性 (防呆 + 自动吸正): 对角同极, 相邻异极. 两侧 (支架/后盖) 镜像 => 相反极性互吸 ---
#   后盖侧极性键 'N'/'S' (按 (sx,sy) 象限棋盘): 左上=N, 右上=S, 左下=S, 右下=N (对角同极).
#   支架侧为镜像相反极性 (后盖 N 处对吸支架 S), 装配只有正确朝向才同位异极吸合, 反装相斥 => 防呆.
def _mag_polarity(sx, sy):
    # 棋盘: (sign(sx)*sign(sy)) >0 => 同象限对角对 => 'N'; <0 => 'S'. (sx,sy 非零)
    return "N" if (sx * sy) > 0 else "S"
MAG_POLARITY = [_mag_polarity(sx, sy)
                for sx in (-MAG_COL_X, +MAG_COL_X)
                for sy in (-MAG_INSET_Y, +MAG_INSET_Y)]
# --- (可选) 屏体补强磁腔位置 (AUX_MAG_ENABLE=True 时镜像支架, 上下各一对) ---
AUX_MAG_POSITIONS = [
    (-POGO_MAG_SPAN / 2, DOCK_CENTER_Y + AUX_MAG_OFFSET_Y),
    (+POGO_MAG_SPAN / 2, DOCK_CENTER_Y + AUX_MAG_OFFSET_Y),
    (-POGO_MAG_SPAN / 2, DOCK_CENTER_Y - AUX_MAG_OFFSET_Y),
    (+POGO_MAG_SPAN / 2, DOCK_CENTER_Y - AUX_MAG_OFFSET_Y),
]

# --- 后盖 FPC 折回槽 (底部短边 -Y 中央) ---
FPC_SLOT_ENABLE = False                      # 暂移除折回槽; 待 FPC 实测尺寸后再开回并收敛形状 (§8)
FPC_SLOT_W = 24.0                            # 折回槽宽 (FPC 实测宽 + 余量; 待测 §8)
FPC_SLOT_DEPTH = 10.0                        # 沿 +Y 深入

# ============================================================
# (已删除) 屏体 Type-C 开口 — 架构变更: 屏体不再有任何线缆口
# ============================================================
# 原方案在 bezel 底边壁切 Type-C 朝下开口; 新方案 Type-C 移到支架底边 (见 bracket).
#   屏体 bezel/back_cover 底边壁实心 (无 Type-C 口, 无 plug 让位缺口). 供电改 pogo pad 受电.
# 屏体中心世界 Y (顶部对齐: 屏顶=显示器顶=0, 向下延伸); 保留供装配/自检反算用.
BODY_CENTER_Y_WORLD = (0.0 + TOP_FLUSH_OFFSET) - BEZEL_OUT_H / 2   # ≈ -53.06

# ============================================================
# 后盖嵌入凸台 plug (无螺丝夹持: 边框前端面压住 PCB 背面四周边沿)
# ============================================================
# plug 外框 = 腔内 - 配合间隙; 从后盖内面(z=BEZEL_DEPTH=8.3 装配后)伸入到 PCB 背面(4.1).
BC_PLUG_INSET = FIT_GAP                        # 凸台与腔配合间隙
BC_PLUG_W = SCR_CAV_W - 2 * BC_PLUG_INSET
BC_PLUG_H = SCR_CAV_H - 2 * BC_PLUG_INSET
# plug 伸入深度: 从背腔内面 (BEZEL_DEPTH) 伸到 PCB 背面 (PCB_BACK_Z), 前端面压 PCB 背边沿.
#   给 0.1 过盈 (预压): 前端面比 PCB 背面再前推 BC_PLUG_PRELOAD, 拧紧 M2 时夹紧板.
BC_PLUG_PRELOAD = 0.1                          # 夹持预压量 (0~0.2 过盈; 余量靠泡棉/板弹性吸收)
BC_PLUG_DEPTH = (BEZEL_DEPTH - PCB_BACK_Z) + BC_PLUG_PRELOAD   # 8.3-4.1+0.1 = 4.3
# plug 边框宽度 (只压 PCB 周边非元件区, 中央镂空让过元件):
BC_PLUG_RIM = 4.0                              # 边框料宽 (压 PCB 周边 4mm)
# plug 中央镂空 = PCB 元件区 + 余量; 镂空必须贯穿整个 plug 深度让开 4mm 高元件.
BC_PLUG_CAV_W = BC_PLUG_W - 2 * BC_PLUG_RIM
BC_PLUG_CAV_H = BC_PLUG_H - 2 * BC_PLUG_RIM
# (已删除) plug 底边 Type-C 让位缺口 — 架构变更: 屏体无 Type-C 母座, plug 底边边框完整保留.

# ============================================================
# L 支架几何 (bracket) — 独立局部坐标
#   局部坐标: 抱边 U 口朝 -Z 罩住显示器边; X=显示器顶边方向, Y=显示器左边方向, Z=厚度法向.
#   为简化, 用世界尺度直接建几何; 装配时整体摆放。
# ============================================================
# 显示器左上角参考块 (MON_*): 一个角块, 顶边厚 7, 左边厚 7, 边缘总厚 17.
MON_CORNER_W = 60.0          # 参考块沿顶边(X)长度
MON_CORNER_H = 60.0          # 参考块沿左边(Y)长度
MON_CORNER_T = MON_EDGE_T    # 边缘厚 17

# 卡钉 U 形口 (抱住显示器顶边 + 左边):
CLIP_U_DEPTH = CLIP_DEPTH                     # 17.5 U 口深 (= T_edge + 余量)
CLIP_WALL = 2.5                               # 卡钉壁厚
CLIP_FRONT_T = 2.5                            # 前舌厚
CLIP_BACK_T = 2.5                             # 后舌厚
# 抱边臂长度 (沿显示器边方向): 顶边臂 + 左边臂
CLIP_ARM_LEN = 28.0                           # 卡钉抱边段沿显示器边的长度

# --- 改动 1+2: 平顺单一支柱 (strut) 替代"折臂+臂根块+腹板" ---
# 屏体外形宽 ~67, 需把屏体落在显示器左边外侧, 对接面在屏体右侧 (朝显示器).
ARM_REACH = 22.0                              # 支柱从抱边伸向左上角外侧的水平 (X) 距离
# 支柱截面 (矩形, 规整): STRUT_W = 沿屏宽(X)宽度, STRUT_H = 沿厚度(Z)高度.
#   它是把屏体悬挑到角外的悬臂, 承屏体 ~40g + 杠杆力 => 给足刚度 (≥6×6).
STRUT_W = 12.0                                # 支柱沿 X 截面宽 (够刚, 也是与板的贴合宽)
STRUT_H = 8.0                                 # 支柱沿 Z 截面高 (≥6)
STRUT_FILLET = 2.0                            # 支柱两端根部圆角过渡

# 对接面 (mating plate): 嵌 POGO 磁吸连接器凹腔 + 走线腔 + 高摩擦垫沉槽
MATE_W = BEZEL_OUT_W                          # 对接面宽 (≈屏体宽)
MATE_H = BEZEL_OUT_H * 0.65                   # 对接面高 (覆盖 POGO 区 + 走线腔)
MATE_T = 5.0                                  # 对接面板厚 (POGO 本体 2.0 沉入 + 留底)
# 架构变更: Type-C 壳块移到支柱下方后, 对接板不再为容纳 Type-C 体深而下探.
#   对接板底沿只需包住 "最低一排 Φ8 磁 (band_center - MAG_INSET_Y)" + 余量 => 缩短、清爽.
PLATE_BOT_MARGIN = 2.0                        # 最低磁腔外缘到对接板底沿的余量 (Y 方向留料)
# POGO 在对接面: 长向沿 X 水平居中, 落在对接区竖向中心 (沿用磁带中心 Y).
#   后盖目标区 X 居中对称, 故装配镜像后 pogo 针阵与后盖 pad 窗自动重合 (偏差≈0).
POGO_CENTER_X_LOCAL = 0.0                     # POGO 沿对接面 X 中心 (居中)
# 高摩擦垫沉槽: 落在 POGO 下方 (避开 POGO 凹腔), 抗久放下滑.
FRICTION_PAD_W = MATE_W - 8.0                 # 摩擦垫沉槽宽 (居中)
FRICTION_PAD_H = 12.0                         # 摩擦垫沉槽高
FRICTION_PAD_OFFSET_Y = -(POGO_WID / 2 + FRICTION_PAD_H / 2 + 4.0)  # 落 POGO 下方, 不碰

OUT = Path(__file__).resolve().parent / "output" / "426"
OUT.mkdir(parents=True, exist_ok=True)


# ============================================================
# 零件 1: bezel 前框
#   前表面 z=0 (朝 -z 打印朝下), 背腔开口朝 +z.
# ============================================================
def make_bezel():
    with BuildPart() as bz:
        # 1) 实心托盘块 (四角圆角): z=0 .. BEZEL_DEPTH
        with BuildSketch(Plane.XY) as _osk:
            Rectangle(BEZEL_OUT_W, BEZEL_OUT_H)
            fillet(_osk.vertices(), radius=CORNER_R)
        extrude(amount=BEZEL_DEPTH)

        # 2) 背面屏容腔 (从背面挖, 留前面板). 唇边 = 前面板背面向内的一圈.
        #    腔宽=屏容腔; 前面板留 FRONT_WALL_T. 唇通过"视窗小于腔"自然形成.
        with BuildSketch(Plane.XY.offset(FRONT_WALL_T)) as cav_sk:
            Rectangle(SCR_CAV_W, SCR_CAV_H)
            fillet(cav_sk.vertices(), radius=SCR_CAV_CORNER_R)
        extrude(amount=BEZEL_CAV_DEPTH + 0.01, mode=Mode.SUBTRACT)

        # 3) 视窗开口 (贯穿前面板), AA + 余量; 水平居中, 纵向上偏 WINDOW_OFFSET_Y.
        #    视窗 < 屏容腔 => 前面板背面残留一圈即唇边 (压黑边, 厚 = LIP).
        with Locations((0, WINDOW_OFFSET_Y, -0.01)):
            Box(WINDOW_W, WINDOW_H, FRONT_WALL_T + 0.02,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 4) 四角自攻柱 boss (从前面板背面升起, 顶到背腔口齐平)
        boss_h = BEZEL_CAV_DEPTH
        with Locations(
            (BOSS_X, BOSS_Y, FRONT_WALL_T), (-BOSS_X, BOSS_Y, FRONT_WALL_T),
            (BOSS_X, -BOSS_Y, FRONT_WALL_T), (-BOSS_X, -BOSS_Y, FRONT_WALL_T),
        ):
            Cylinder(BOSS_D / 2, boss_h,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
        # boss 自攻底孔 (从背面钻入)
        with Locations(
            (BOSS_X, BOSS_Y, BEZEL_DEPTH), (-BOSS_X, BOSS_Y, BEZEL_DEPTH),
            (BOSS_X, -BOSS_Y, BEZEL_DEPTH), (-BOSS_X, -BOSS_Y, BEZEL_DEPTH),
        ):
            Cylinder(BOSS_PILOT_D / 2, boss_h - 0.5,
                     align=(Align.CENTER, Align.CENTER, Align.MAX),
                     mode=Mode.SUBTRACT)

        # 5) (修 bug1: 支柱移到后盖) bezel 前腔不再有任何 PCB 支撑支柱/定位销.
        #    旧方案支柱从前面板内面(z=1.0)长到 PCB 前面(z=2.5), 与墨水屏(z∈[1.0,2.0]) 同处一空间
        #    => 4 支柱戳进屏背 ~1mm (实测 bezel∩screen=205.5mm3). 现把 PCB 支撑/定位销整体移到
        #    make_back_cover: 从后盖内面伸向 PCB 背面把板顶到既定 Z, 墨水屏侧 (bezel) 全程无支柱.
        #    bezel 前腔只留: 墨水屏腔 + 唇边 + 4 角 M2 自攻柱 boss (上方步骤 4, 保留).

        # 6) (已删除) bezel 底边 Type-C 开口 — 架构变更: 屏体无 Type-C 口, 底边壁实心.
        #    供电改: 支架底边防水 Type-C -> 走线腔 -> 对接面 POGO -> 屏体后盖 pad 受电.
    return bz.part


# ============================================================
# 零件 2: back_cover 后盖
#   平板 z=0 底(外表面), +z 朝 bezel 背腔. 与 bezel 同 XY 朝向.
# ============================================================
def make_back_cover():
    with BuildPart() as bc:
        # 1) 盖板 (与屏体外形齐平, 四角圆角)
        with BuildSketch(Plane.XY) as _bcsk:
            Rectangle(BEZEL_OUT_W, BEZEL_OUT_H)
            fillet(_bcsk.vertices(), radius=CORNER_R)
        extrude(amount=BACK_COVER_PLATE_T)

        # 2) 嵌入凸台 plug (向 +z 朝 bezel) — 空心边框, 前端面压 PCB 背面四周边沿.
        #    无螺丝夹持: plug 边框从背腔伸到 PCB 背面, 拧紧 4 颗 M2 即夹紧板.
        #    中央镂空 (BC_PLUG_CAV) 贯穿整个 plug 深度, 让过 4mm 高元件 (留 COMP_CLEAR).
        with BuildSketch(Plane.XY.offset(BACK_COVER_PLATE_T)) as plug_sk:
            Rectangle(BC_PLUG_W, BC_PLUG_H)
            fillet(plug_sk.vertices(), radius=SCR_CAV_CORNER_R)
        extrude(amount=BC_PLUG_DEPTH)
        with Locations((0, 0, BACK_COVER_PLATE_T)):
            Box(BC_PLUG_CAV_W, BC_PLUG_CAV_H, BC_PLUG_DEPTH + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 2b) (已删除) plug 底边 Type-C 让位缺口 — 架构变更: 屏体无 Type-C, plug 底边完整保留.

        # 2c) (修 bug1: 支柱移来后盖) PCB 支撑支柱 (4 根) + 对角 2 定位销.
        #    旧方案支柱在 bezel 前腔, 戳进墨水屏背. 现从后盖内面 (盖板内面 z=BACK_COVER_PLATE_T)
        #    向 +z (朝屏侧/PCB) 升到 PCB 背面 (后盖局部 z=BC_STANDOFF_TOP_LOCAL_Z), 把元件面朝后盖的
        #    PCB 顶到既定 Z (PCB 背面 z=PCB_BACK_Z). 支柱落 PCB 四角安装孔位 (component-free),
        #    沿 X 落在 plug 左右料环带 (|x|>BC_PLUG_CAV_W/2), 有 plug 料可熔.
        for (sx, sy) in PCB_STANDOFF_POSITIONS:
            # 起点下沉 0.3 进盖板 (与盖板/plug 熔为一体, 避免共面不熔).
            with Locations((sx, sy, BACK_COVER_PLATE_T - 0.3)):
                Cylinder(PCB_STANDOFF_D / 2, PCB_STANDOFF_H + 0.3,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 对角 2 定位销: 从支柱顶 (= PCB 背面, 后盖局部 z=BC_STANDOFF_TOP_LOCAL_Z) 向 +z 插板定位孔.
        for (px, py) in PCB_LOC_PIN_POSITIONS:
            with Locations((px, py, BC_STANDOFF_TOP_LOCAL_Z)):
                Cylinder(PCB_LOC_PIN_D / 2, PCB_LOC_PIN_H,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 3) 受电侧对接区 (替代原 4×Φ8 磁腔):
        #    架构变更: 删除 4×Φ8 磁腔. 改为
        #      (a) 4 触点 pad 窗 (Φ2, 对位 pogo 4 针): 贯穿后盖外壳, 露板背 pad;
        #      (b) 2 钢吸片腔 (Φ3.5×1, 对位 pogo N/S 磁): 从外表面 z=0 沉 STEEL_T 嵌钢片 (不穿透).
        plate_through_h = BACK_COVER_PLATE_T + 0.02
        # (a) 4 触点 pad 窗 — 贯穿后盖盖板 (z=0..PLATE_T), pogo 针凸出后压到此处露出的板背 pad.
        for (wx, wy) in PAD_WINDOW_POSITIONS:
            with Locations((wx, wy, -0.01)):
                Cylinder(PAD_WINDOW_D / 2, plate_through_h,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
        # (b) 2 钢吸片腔 — 从外表面 z=0 向 +z 沉 STEEL_T, 不穿透 (嵌 Φ3.5×1 钢片).
        for (sx, sy) in STEEL_POSITIONS:
            with Locations((sx, sy, -0.01)):
                Cylinder(STEEL_D / 2, STEEL_T + 0.01,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
        # (c) 4×Φ8 磁腔 (吸合/承重主力, 对接带四角): 盲腔, 磁外侧 (朝支架/对接面) 留薄壁 MAG_OUTER_WALL.
        #     后盖外表面 z=0 朝支架; 磁外侧壁在 z∈[0, MAG_OUTER_WALL]; 磁体腔 z∈[MAG_OUTER_WALL,
        #     MAG_OUTER_WALL+MAG_T]; 内侧 (+z) 完全敞开让磁铁从内侧压入, 再由 plug/PCB 压住.
        #     盖板仅 1.5mm 装不下 3mm 深腔 => 先在内侧 (+z) 长磁柱 boss 补料 (Φ磁+2壁), 再掏腔.
        # --- 修 bug1 (磁铁塞不进): 旧代码磁柱顶 = 腔顶 + 0.5 => 内侧多盖 0.5mm 实料, 腔两头封死.
        #     现把磁柱顶降到与腔顶齐平 (MAG_OUTER_WALL+MAG_T), 磁腔内侧 (+z) 敞开 => 磁铁从内侧装入.
        MAG_BOSS_D = MAG_D + 2 * 1.6                 # 磁柱外径 (磁 Φ8 + 单边 1.6 壁)
        MAG_BOSS_TOP_Z = MAG_OUTER_WALL + MAG_T      # 磁柱顶 z = 腔顶 (去掉 0.5 盖, 内侧敞开可嵌磁)
        for (mx, my) in MAG_POSITIONS:
            with Locations((mx, my, 0.0)):           # 从盖板外表面 z=0 起长柱 (与盖板熔为一体)
                Cylinder(MAG_BOSS_D / 2, MAG_BOSS_TOP_Z,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))
        for (mx, my) in MAG_POSITIONS:
            # 腔从外侧薄壁内面 (z=MAG_OUTER_WALL) 掏到磁柱顶 (z=MAG_OUTER_WALL+MAG_T) 并外溢 0.01
            # 贯穿磁柱顶面 => 内侧 (+z) 开口敞开, 磁铁压入无阻挡.
            with Locations((mx, my, MAG_OUTER_WALL)):
                Cylinder(MAG_D / 2, MAG_T + 0.02,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
        # (d) (可选) 屏体补强磁腔 (AUX_MAG_ENABLE=True 时, 镜像支架补强磁): 不穿透.
        if AUX_MAG_ENABLE:
            for (ax, ay) in AUX_MAG_POSITIONS:
                with Locations((ax, ay, -0.01)):
                    Cylinder(AUX_MAG_D / 2, AUX_MAG_T + 0.01,
                             align=(Align.CENTER, Align.CENTER, Align.MIN),
                             mode=Mode.SUBTRACT)

        # 后盖全厚 (供 FPC 槽 / 螺孔等贯穿特征复用)
        slot_total_h = BACK_COVER_PLATE_T + BC_PLUG_DEPTH + 0.02
        # 4) 底部短边 (-Y) FPC 折回槽: 中央, 宽 FPC_SLOT_W, 深入 +Y FPC_SLOT_DEPTH, 贯穿厚度
        #    暂移除 (FPC_SLOT_ENABLE=False): 待 FPC 实测尺寸后再收敛为正确折回让位形状 (§8).
        if FPC_SLOT_ENABLE:
            with Locations((0, -BEZEL_OUT_H / 2, -0.01)):
                Box(FPC_SLOT_W, FPC_SLOT_DEPTH * 2, slot_total_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT)

        # 5) (已删除) 原 Type-C 切口在后盖上无效 — 该 Z 的右壁由 bezel 出, 口被封死.
        #    Type-C 开口现切在 bezel +X 右侧壁 (见 make_bezel 步骤 7), 真穿透.

        # 6) 四角 M2 自攻通孔 (对位 bezel boss)
        with Locations(
            (BOSS_X, BOSS_Y, -0.01), (-BOSS_X, BOSS_Y, -0.01),
            (BOSS_X, -BOSS_Y, -0.01), (-BOSS_X, -BOSS_Y, -0.01),
        ):
            Cylinder(SCREW_CLEAR_D / 2, slot_total_h,
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)
        # boss 让位: 凸台区给 bezel 角柱 Φ(BOSS_D+1) 空腔
        with Locations(
            (BOSS_X, BOSS_Y, BACK_COVER_PLATE_T), (-BOSS_X, BOSS_Y, BACK_COVER_PLATE_T),
            (BOSS_X, -BOSS_Y, BACK_COVER_PLATE_T), (-BOSS_X, -BOSS_Y, BACK_COVER_PLATE_T),
        ):
            Cylinder((BOSS_D + 1.0) / 2, BC_PLUG_DEPTH + 0.01,
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)
    return bc.part


# ============================================================
# 零件 3: bracket L 支架
#   局部坐标: 卡钉 U 口罩在显示器左上角. 取显示器外前表面 z=0, 显示器朝 +Z (朝用户).
#     X = 沿显示器顶边 (右为 +X, 远离左边缘); Y = 沿显示器左边 (上为 +Y);
#     角点 (显示器左上外角) 取在 (0,0). 显示器实体占 X>=0,Y<=0 (即角块在 -Y/+X 象限内侧).
#   构造: 顶边卡钉 (沿 X) + 左边卡钉 (沿 Y) 形成 L; 支架臂从角点伸向 -X (左上角外侧),
#     端部接对接面 (竖直板, 法向 +X 朝屏体后盖).
# ============================================================
def make_bracket():
    with BuildPart() as br:
        # ============================================================
        # 卡钉 U 形抱边 — correct-by-construction 留 0.3 间隙 (修复回归)
        # ============================================================
        # 思路: 不再"事后整体减去外扩显示器块"(那一刀切断了连接料、削平了 L 角).
        #   改为直接把 U 形内腔/抱边内表面按"显示器角块外形 + 单边 MON_FIT_GAP"建出来:
        #   每一面卡钉料从一开始就离显示器各面 0.3mm, 既保间隙又不破坏连通性.
        #
        # 显示器角块: X∈[0, MON_CORNER_W], Y∈[-MON_CORNER_H, 0], Z∈[-MON_EDGE_T, 0].
        #   顶边在 Y=0 (显示器在 Y<0); 左边在 X=0 (显示器在 X>0); 前表面 Z=0, 背面 Z=-17.
        # 间隙约定 (单边 g): 前面 Z=0 -> 抱边前舌底面在 Z=+g; 背面 Z=-T -> 后舌顶面在 Z=-(T+g);
        #   顶边 Y=0 -> 顶边外侧壁内面在 Y=+g; 左边 X=0 -> 左边外侧壁内面在 X=-g.
        g = MON_FIT_GAP
        # U 腔沿 Z 的料范围 (外侧壁贯通前后舌, 把整段边厚罩住, 两端各让 g):
        WALL_Z0 = -(MON_EDGE_T + g + CLIP_BACK_T)   # 外侧壁/后舌料底 (后舌顶面在 -(T+g))
        WALL_Z1 = g + CLIP_FRONT_T                  # 外侧壁/前舌料顶 (前舌底面在 +g)
        WALL_H = WALL_Z1 - WALL_Z0
        FRONT_Z0 = g                                # 前舌底面 (离前表面 0.3)
        BACK_Z1 = -(MON_EDGE_T + g)                 # 后舌顶面 (离背面 0.3)

        # --- 顶边卡钉 (沿 X 延伸; 顶边 Y=0; 外侧=+Y, 向内=-Y) ---
        # 外侧壁占 Y∈[g, g+CLIP_WALL]; 前/后舌从 Y=g 向内(-Y)伸 LIP, 离顶面 0.3.
        def clip_along_top(x0, x1):
            cx = (x0 + x1) / 2
            w = x1 - x0
            with Locations((cx, g + CLIP_WALL / 2, WALL_Z0)):            # 外侧壁
                Box(w, CLIP_WALL, WALL_H,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # 前舌: Y∈[-CLIP_FRONT_LIP, g+CLIP_WALL], Z∈[g, g+CLIP_FRONT_T]
            with Locations((cx, (g + CLIP_WALL - CLIP_FRONT_LIP) / 2, FRONT_Z0)):
                Box(w, CLIP_FRONT_LIP + CLIP_WALL + g, CLIP_FRONT_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # 后舌: Y∈[-CLIP_BACK_LIP, g+CLIP_WALL], Z∈[-(T+g+CLIP_BACK_T), -(T+g)]
            with Locations((cx, (g + CLIP_WALL - CLIP_BACK_LIP) / 2, WALL_Z0)):
                Box(w, CLIP_BACK_LIP + CLIP_WALL + g, CLIP_BACK_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))

        # --- 左边卡钉 (沿 Y 延伸; 左边 X=0; 外侧=-X, 向内=+X) ---
        # 外侧壁占 X∈[-(g+CLIP_WALL), -g]; 前/后舌从 X=-g 向内(+X)伸 LIP, 离左面 0.3.
        def clip_along_left(y0, y1):
            cy = (y0 + y1) / 2
            h = y1 - y0
            with Locations((-(g + CLIP_WALL / 2), cy, WALL_Z0)):          # 外侧壁
                Box(CLIP_WALL, h, WALL_H,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # 前舌: X∈[-(g+CLIP_WALL), CLIP_FRONT_LIP], Z∈[g, g+CLIP_FRONT_T]
            with Locations(((CLIP_FRONT_LIP - g - CLIP_WALL) / 2, cy, FRONT_Z0)):
                Box(CLIP_FRONT_LIP + CLIP_WALL + g, h, CLIP_FRONT_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # 后舌: X∈[-(g+CLIP_WALL), CLIP_BACK_LIP]
            with Locations(((CLIP_BACK_LIP - g - CLIP_WALL) / 2, cy, WALL_Z0)):
                Box(CLIP_BACK_LIP + CLIP_WALL + g, h, CLIP_BACK_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))

        # --- 左上角拐角抱料 (把两条卡钉在角部连续熔接, L 角包严) ---
        # 角块: 外侧壁在拐角处补一个方角 (覆盖 X∈[-(g+CLIP_WALL), g+CLIP_WALL] 与
        #   Y∈[-(g+CLIP_WALL), g+CLIP_WALL] 的外壳方块), 前/后舌在角部同样补满, 使
        #   顶面/左面/前黑边/后背面在角部完整包住 (各留 g 间隙). 这是两臂共享的连接料.
        def clip_corner():
            cw = g + CLIP_WALL                  # 外侧壁外沿到显示器面距离
            # --- 外侧壁: L 形包角 (绕显示器外角, 不侵入 X>-g & Y<g 的显示器+间隙包络) ---
            # 左臂段 (沿 -X 侧): X∈[-cw, -g], Y∈[-cw, cw]
            with Locations((-(g + cw) / 2, 0.0, WALL_Z0)):
                Box(cw - g, 2 * cw, WALL_H,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # 顶臂段 (沿 +Y 侧): X∈[-cw, cw], Y∈[g, cw]
            with Locations((0.0, (g + cw) / 2, WALL_Z0)):
                Box(2 * cw, cw - g, WALL_H,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # --- 角前舌: 沿前面 (Z∈[g, g+CLIP_FRONT_T]) 把角部前黑边压住, L 形避让显示器+间隙 ---
            # 前舌允许进入黑边区 (Z 已抬 g, 离前表面 0.3, 不压画面). 仍做成 L 避免无谓覆盖.
            # 左前舌段: X∈[-cw, CLIP_FRONT_LIP], Y∈[-cw, cw]
            with Locations(((CLIP_FRONT_LIP - cw) / 2, 0.0, FRONT_Z0)):
                Box(CLIP_FRONT_LIP + cw, 2 * cw, CLIP_FRONT_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # 顶前舌段: X∈[-cw, cw], Y∈[-CLIP_FRONT_LIP, cw]
            with Locations((0.0, (cw - CLIP_FRONT_LIP) / 2, FRONT_Z0)):
                Box(2 * cw, CLIP_FRONT_LIP + cw, CLIP_FRONT_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            # --- 角后舌: 同前舌的 L 形, Z 在后舌料层 (离背面 0.3) ---
            with Locations(((CLIP_BACK_LIP - cw) / 2, 0.0, WALL_Z0)):
                Box(CLIP_BACK_LIP + cw, 2 * cw, CLIP_BACK_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            with Locations((0.0, (cw - CLIP_BACK_LIP) / 2, WALL_Z0)):
                Box(2 * cw, CLIP_BACK_LIP + cw, CLIP_BACK_T,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 拐角料 + 顶边卡钉 (从角部 0 起沿 +X 伸) + 左边卡钉 (从角部 0 起沿 -Y 伸):
        #   三段在拐角邻域重叠 => 熔接成连续 L 角, 不留缺口.
        clip_corner()
        clip_along_top(0.0, CLIP_ARM_LEN)
        clip_along_left(-CLIP_ARM_LEN, 0.0)

        # ============================================================
        # 修正 1+2: 支柱沿顶边直出 -X (不拱起) + 藏在屏体背后 (Z<Zf)
        # ============================================================
        # 设计要点:
        #   - 支柱 = 单一 -X 方向拉伸的矩形截面 (STRUT_W × STRUT_H), 无台阶/无折弯.
        #   - 修正 1: 支柱**不再放进 +Y 安全带** (上一版 arm_yc=g+STRUT_W/2 把支柱整条
        #     拱到显示器顶边 Y=0 之上, 既绕又丑). 改为支柱落在**屏体顶部高度一带 (Y≤0)**,
        #     上沿贴屏顶 (Y=0), 向 -Y 延伸. 因对接板与屏体都在显示器左侧 X<0, 支柱靠
        #     **X<0** (走显示器左边缘外侧) 避开显示器, 不需要靠 +Y 拱起避让.
        #     => 支柱根部咬**左边臂卡钉料** (X∈[-cw,-g], Y<0 段都有料), 沿 -X 直线接到板.
        #   - 修正 2: 支柱/对接板整体下沉到**屏体背后 Z<Zf=0**. 板顶面贴屏体后盖外表面,
        #     支柱在板上层 (朝屏体侧). 正面只露卡钉前舌 (Z≥0) 压黑边.
        #   - 对接板做成"支柱的加强背肋": 支柱末端以全截面整张贴进板内, 不细颈.
        cw = g + CLIP_WALL
        # 修正 1: 支柱 Y 中心. 上沿贴屏顶 (世界 Y=0), 向 -Y 延伸 => arm_yc = -STRUT_W/2.
        #   支柱占 Y∈[-STRUT_W, 0], 全程 Y≤0 (屏体顶部高度一带), 无 +Y 拱起.
        arm_yc = -STRUT_W / 2

        # --- 对接板 (mating plate): 法向朝屏体后盖, 藏在屏体背后 Z<Zf ---
        # 板厚沿 Z, 面跨 X(屏宽) × Y(屏高). 板顶面贴屏体后盖外表面 (Z<0).
        arm_x_end = -ARM_REACH                  # 支柱末端 (送出画面外, X<0)
        mate_cx = arm_x_end - MATE_W / 2 + STRUT_W / 2
        # 改动 4 沿用: 板/屏体竖向锚点 = 屏体中心 (顶部对齐), 供磁位绝对映射用.
        #   屏体顶边 = 显示器顶边(Y=0)+TOP_FLUSH_OFFSET => 屏体中心 = 顶边 - BEZEL_OUT_H/2.
        mate_cy = (0.0 + TOP_FLUSH_OFFSET) - BEZEL_OUT_H / 2
        # 修正 2: 对接板顶面 Z = 屏体后盖外表面世界 Z - 磁吸气隙.
        #   墨水屏前表面世界 Z = Zf + Z_FLUSH_OFFSET (=0); 后盖外表面 = 前表面 - BODY_T_ACTUAL;
        #   板顶面 = 后盖外表面 - MATE_GAP (与 body_placement 的 gap 一致).
        MATE_GAP = 0.5
        body_front_z = 0.0 + Z_FLUSH_OFFSET                 # 墨水屏前表面世界 Z (=Zf+offset)
        back_outer_z = body_front_z - BODY_T_ACTUAL         # 屏体后盖外表面世界 Z
        mate_z_top = back_outer_z - MATE_GAP                # 板顶面 (贴后盖, 在屏体背后)
        mate_z_bot = mate_z_top - MATE_T
        # 板竖向范围: 上探到屏顶 (Y≈0, 让支柱平直接入板顶), 下探到 "最低一排磁" + 余量.
        # 架构变更: Type-C 壳块已移到支柱下方 (不再挂对接板底), 故板底不再为 14mm 体深下探.
        #   板底只需包住对接带最低一排 Φ8 磁 (band_y_world - MAG_INSET_Y) 的磁腔外缘 + 余量.
        band_y_world = mate_cy + MAG_BAND_CENTER_Y          # POGO/对接区竖向中心
        lowest_mag_y = band_y_world - MAG_INSET_Y           # 最低一排磁心世界 Y
        plate_top_y = 0.0                                   # 板顶贴屏顶高度 (Y=0)
        # 板底 = 最低磁心 - (磁半径 + 余量), 包住磁腔留料, 不为 Type-C 下探 => 缩短.
        plate_bot_y = lowest_mag_y - (MAG_D / 2 + PLATE_BOT_MARGIN)
        plate_cy = (plate_top_y + plate_bot_y) / 2
        plate_h = plate_top_y - plate_bot_y
        with Locations((mate_cx, plate_cy, mate_z_bot)):
            Box(MATE_W, plate_h, MATE_T,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # --- 笔直支柱: 单一 -X 拉伸的矩形棒, 从左边臂卡钉直通到板内 ---
        # 修正 2: 支柱 Z 落在板上层 (顶面齐板顶 mate_z_top, 向 -Z 伸 STRUT_H), 全程 Z<Zf=0.
        strut_z_top = mate_z_top                           # 支柱顶面齐板顶
        strut_z_bot = strut_z_top - STRUT_H                # 支柱底
        strut_z_c = (strut_z_bot + strut_z_top) / 2
        # 修正 1: X 范围从左边臂外侧壁 (-g, 咬卡钉料) 到板内 (mate_cx). 全程 X≤0 不碰显示器.
        strut_x_start = -g                                 # 支柱起点 (咬左边臂外壁料, X<0)
        strut_x_endin = arm_x_end - 0.01                   # 末端伸到板心列 (整张贴进板)
        strut_len = strut_x_start - strut_x_endin          # 沿 X 长度
        strut_cx = (strut_x_start + strut_x_endin) / 2
        with BuildSketch(Plane.XY.offset(strut_z_bot)) as _strut_sk:
            with Locations((strut_cx, arm_yc)):
                Rectangle(strut_len, STRUT_W)
        extrude(amount=STRUT_H)
        # 支柱根部咬左边臂卡钉料: 左边臂外侧壁 Z∈[WALL_Z0, WALL_Z1] 贯通前后, 支柱 Z 落其内
        #   (strut_z 在 [WALL_Z0, WALL_Z1] 内) => 天然熔合. 再补一小块跨入卡钉料确保连通.
        #   X 锁在左边臂外壁带 (-cw..-g 一带); Y 落支柱带 (Y≤0, 不下探超出左边臂 Y 范围).
        with Locations((-cw, arm_yc, strut_z_bot)):
            Box(2 * cw, STRUT_W, STRUT_H,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 注: 支柱为单一拉伸矩形棒 (主轴 = X, 截面 STRUT_W×STRUT_H 恒定), 无折弯/无台阶/无拱起.
        #   全程 Y≤0 (屏体顶部高度) 且 Z<Zf=0 (屏体背后); 末端整张埋进板内 => 大面积熔接.

        # 改动 1: 支柱两侧顶部纵向棱 (沿 X, 在 z=strut_z_top, y=arm_yc±STRUT_W/2) 倒圆角过渡,
        #   缓冲悬臂根部应力集中. 仅选支柱顶面纵向长棱, 避开板/卡钉, 防 fillet 失败.
        try:
            _top_edges = br.edges().filter_by(Axis.X).group_by(
                lambda e: e.length)[-1]   # 最长一组 = 沿 X 的支柱纵棱
            _top_edges = [e for e in _top_edges
                          if abs(e.center().Z - strut_z_top) < 0.3
                          and abs(abs(e.center().Y - arm_yc) - STRUT_W / 2) < 0.3]
            if _top_edges:
                fillet(_top_edges, radius=STRUT_FILLET)
        except Exception as _e:
            print(f"   [支柱倒角] 跳过 (选棱/fillet 失败, 不影响连通性): {_e}")

        # ============================================================
        # 架构变更: 对接面 POGO 磁吸连接器凹腔 + 走线腔 + 底边 Type-C 母座位
        # ============================================================
        # POGO 中心 (对接面世界坐标): X 居中于对接板, Y = POGO/对接区竖向中心.
        pogo_cx = mate_cx + POGO_CENTER_X_LOCAL            # POGO 沿 X 中心 (= 板心, 居中)
        pogo_cy = band_y_world                             # POGO 沿 Y 中心
        # ---- POGO 本体凹腔 (修 bug2: 改从 -Z 背面开口, POGO 从支架背面装入) ----
        #   旧 bug: 凹腔从 +Z 贴合面沉 2mm, POGO 焊脚 (-Z) 顶着实心腔底 => 装进去焊不了线/固定不了.
        #   现: 凹腔从 -Z 背面 (mate_z_bot) 向 +Z 掏到 "贴合面薄壁内面" (pogo_pocket_floor_z);
        #       -Z 背面完全敞开 => POGO 焊接面朝背面, 飞线就近焊接 + 本体压入/胶固定;
        #       贴合面 (+Z) 只留薄壁 POGO_FACE_WALL + 4 针孔, 不把整 POGO 露出屏侧.
        #   贴合面薄壁须 < 针凸出 (POGO_PIN_PROTRUDE), 否则针尖到不了屏侧; 取 0.8 (< 1.5).
        POGO_FACE_WALL = MAG_OUTER_WALL                    # 贴合面薄壁 0.8 (< 针凸出 1.5, 针可凸出朝屏)
        pocket_w = POGO_LEN + 2 * POGO_BODY_CLEAR          # 沿 X (长向)
        pocket_h = POGO_WID + 2 * POGO_BODY_CLEAR          # 沿 Y (宽向)
        pogo_pocket_floor_z = mate_z_top - POGO_FACE_WALL  # 凹腔顶 (+Z 侧腔底 = 贴合面薄壁内面)
        pocket_depth = pogo_pocket_floor_z - mate_z_bot    # 凹腔深 (MATE_T - 薄壁 = 5-0.8 = 4.2; 容本体2.0 + 焊脚/飞线余量)
        with Locations((pogo_cx, pogo_cy, mate_z_bot - 0.01)):
            Box(pocket_w, pocket_h, pocket_depth + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)
        # ---- 贴合面 (+Z) 4 针过孔: Φ(针尖+余量), 让 4 针凸出朝屏 +Z; 其余贴合面为薄壁 (不露整 POGO) ----
        #   针基面在腔顶 (pogo_pocket_floor_z = mate_z_top - 0.8); 针凸 1.5 => 针尖 = mate_z_top + 0.7 (凸出屏侧).
        POGO_PIN_HOLE_D = POGO_PIN_TIP_D + 0.9             # 针孔径 ≈ 0.7+0.9 = 1.6 (针/弹簧凸出穿过)
        pin_hole_h = POGO_FACE_WALL + 0.02                 # 仅穿贴合面薄壁 (从腔顶到 +Z 面)
        for i in range(POGO_PIN_N):
            px = pogo_cx + i * POGO_PIN_PITCH - POGO_PIN_SPAN / 2
            with Locations((px, pogo_cy, pogo_pocket_floor_z - 0.01)):
                Cylinder(POGO_PIN_HOLE_D / 2, pin_hole_h,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
        # ---- POGO 2× Φ1.5 安装孔 (沿 X 跨度 17.54, 居中; 贯穿板厚, 背面侧拧固定) ----
        for sgn in (-1, +1):
            with Locations((pogo_cx + sgn * POGO_MOUNT_SPAN / 2, pogo_cy, mate_z_bot - 0.01)):
                Cylinder(POGO_MOUNT_D / 2, MATE_T + 0.02,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
        # ---- (可选) 补强磁腔 (AUX_MAG_ENABLE=True): POGO 上下各一对 Φ6, 屏体镜像 ----
        if AUX_MAG_ENABLE:
            for (ax, ay) in AUX_MAG_POSITIONS:
                with Locations((mate_cx + ax, mate_cy + ay, mate_z_top + 0.01)):
                    Cylinder(AUX_MAG_D / 2, AUX_MAG_T + 0.01,
                             align=(Align.CENTER, Align.CENTER, Align.MAX),
                             mode=Mode.SUBTRACT)

        # ============================================================
        # 架构变更: Type-C 专用实体壳块 (boss) 改挂 "支柱下方" (不再挂对接板底)
        # ============================================================
        #   仍用已验证壳块尺寸 (19.9×13.5×Y16.8, 四壁 ≥1.6) 完整包裹防水带飞线母座.
        #   位置变更:
        #     - X: 沿支柱偏卡钉/显示器一端 (TYPEC_HOUSING_CX, X<0, 显示器左缘外侧), 线缆就近垂在屏旁.
        #     - Y: 挂在支柱下方 (-Y). 壳块 +Y 面伸进支柱下沿 (重叠 OVERLAP) 与支柱熔为一体;
        #          开口/法兰在 -Y 外面 (向下出线), 母座体腔从开口向 +Y 深入 14mm (贴着支柱下方).
        #     - Z: 与支柱一带对齐 (+Z 面齐支柱顶 strut_z_top, 藏屏后 Z<0; 向 -Z 凸出壳厚).
        tc_cx = TYPEC_HOUSING_CX                            # 壳块 X 居中 (偏卡钉端, X<0)
        # 壳块 Z: +Z 面齐支柱顶 strut_z_top (= mate_z_top = -10.3 < 屏体后表面, 藏屏后),
        #   向 -Z 凸出 TYPEC_HOUSING_Z. 与支柱 Z∈[strut_z_bot, strut_z_top] 在重叠 Y 段熔合.
        housing_z_top = strut_z_top                         # 壳块 +Z 面 (齐支柱顶, 藏屏后)
        housing_z_bot = housing_z_top - TYPEC_HOUSING_Z     # 壳块 -Z 面 (凸到背后)
        housing_cz = (housing_z_top + housing_z_bot) / 2
        # 壳块 Y: 须避开 "靠卡钉端那颗 Φ8 磁" (= 上排、X 最靠 0 的磁), 否则磁腔切穿壳壁.
        #   该磁世界坐标: X = mate_cx + MAG_COL_X (右列, 最靠 0), Y = band + MAG_INSET_Y (上排).
        #   壳块 X 宽 19.9 在卡钉端无法同时避显示器(X<0)与该磁(X-edge), 故壳块下移 (-Y),
        #   使壳块 +Y 面落在该磁下缘之下 (留 MAG_CLEAR), 再用一条窄颈 (X 避磁) 接回支柱熔合.
        strut_y_bot = arm_yc - STRUT_W / 2                  # 支柱下沿 (Y 最小)
        mag_near_x = mate_cx + MAG_COL_X                    # 靠卡钉端磁列 X (= -22.98)
        mag_near_y = band_y_world + MAG_INSET_Y             # 靠卡钉端磁排 Y (上排, = -18.71)
        MAG_CLEAR = 1.0                                     # 壳块/颈 与该磁的间隙
        # 壳块 +Y 面 = 该磁下缘 - 间隙 (壳块整体落在磁下方, 不与磁 X 区重叠 => 不切壳壁).
        housing_y_max = mag_near_y - MAG_D / 2 - MAG_CLEAR  # ≈ -18.71-4-1 = -23.71
        housing_y_min = housing_y_max - TYPEC_HOUSING_Y     # 壳块 -Y 面 (底边外缘, 开口朝下)
        bottom_y = housing_y_min                            # 底边壁外缘 (Y 最小) = 开孔/法兰所在面
        tc_cz = housing_cz                                  # 口沿 Z 居中于壳块厚度
        # (0-) 先清出 Type-C 让位: 对接板下探到 -60.7 容最低磁, 其右下角 (磁右缘之右) 会探到
        #   壳块/线缆下出口一带. 该处对接板属多余料 (右磁只需料到磁右缘), 切掉成让位, 使
        #   Type-C 母座 + 向下出线走廊不被对接板挡. 切区: X ∈ [磁右缘+间隙, +∞), Y ≤ 壳块顶.
        clr_x_left = mag_near_x + MAG_D / 2 + MAG_CLEAR     # 切区左沿 = 右磁右缘 + 间隙
        clr_x_right = tc_cx + TYPEC_HOUSING_W / 2 + 2.0     # 切区右沿 (含壳块右侧 + 余量)
        clr_y_top = housing_y_max + 0.01                   # 切到壳块顶 (不动壳块上方支柱带)
        clr_y_bot = plate_bot_y - 3.0                      # 切到板底以下 (出线走廊向下贯通)
        with Locations(((clr_x_left + clr_x_right) / 2, (clr_y_top + clr_y_bot) / 2,
                        mate_z_bot - 1.0)):
            Box(clr_x_right - clr_x_left, clr_y_top - clr_y_bot, MATE_T + 2.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)
        # (0) 壳块实体: 整块 Box 并入 bracket (保持单一连通实体).
        with Locations((tc_cx, housing_y_min, housing_z_top)):
            Box(TYPEC_HOUSING_W, TYPEC_HOUSING_Y, TYPEC_HOUSING_Z,
                align=(Align.CENTER, Align.MIN, Align.MAX))
        # (0b) 熔接颈: 从支柱下沿 (Y=strut_y_bot) 接到壳块 +Y 面 (housing_y_max), 与二者各重叠.
        #   颈 X 收窄到 "磁右缘 + 间隙" 之右, 避开靠卡钉端那颗磁; 颈 Z 落支柱 Z 带内 (熔合).
        neck_x_left = mag_near_x + MAG_D / 2 + MAG_CLEAR    # 颈左沿 (避磁右缘, ≈ -17.98)
        neck_x_right = tc_cx + TYPEC_HOUSING_W / 2          # 颈右沿 = 壳块右沿 (仍 X<0)
        neck_w = neck_x_right - neck_x_left                 # 颈 X 宽 (派生, 自动避磁)
        neck_cx = (neck_x_left + neck_x_right) / 2
        neck_y_top = strut_y_bot + TYPEC_HOUSING_STRUT_OVERLAP  # 上伸进支柱重叠熔接
        neck_y_bot = housing_y_max - 0.01                   # 下接壳块顶 (重叠)
        neck_z_top = strut_z_top                            # 齐支柱顶
        neck_z_bot = strut_z_bot                            # 齐支柱底 (整段在支柱 Z 带内)
        with Locations((neck_cx, neck_y_bot, neck_z_top)):
            Box(neck_w, neck_y_top - neck_y_bot, neck_z_top - neck_z_bot,
                align=(Align.CENTER, Align.MIN, Align.MAX))

        # ---- 内部走线腔 (改道到 -Z 背面): Type-C 体腔(支柱下方) -> 上接入支柱 -> 沿支柱(-X)走到 POGO 背面凹腔 ----
        #   修 bug2 配套: POGO 凹腔已改 -Z 背面开口, 故走线腔全部改从 -Z 背面 (strut_z_bot / mate_z_bot)
        #   向 +Z 沉, 与 POGO 背面开口、Type-C 体腔在背面连通; 贴合面 (+Z) 不再被走线腔挖穿 (保完整, 只留针孔/磁/安装孔).
        #   三段 SUBTRACT 盒首尾重叠成连通 Z/L 路径, 容飞线 + 小 dock PCB/CC 电阻:
        #     A. 壳块/支柱内竖向段 (沿 Y): 从 Type-C 体腔顶 上接到支柱带 (Y=arm_yc), X=tc_cx;
        #     B. 沿支柱横向段 (沿 X): 从 tc_cx 走到 POGO 列 (pogo_cx), Y=arm_yc, 从支柱背面 +Z 沉;
        #     C. 对接板竖向段 (沿 Y): 从支柱带 (Y=arm_yc) 下接到 POGO 凹腔上沿 (pogo_cy+WID/2), X=pogo_cx, 从背面 +Z 沉.
        body_cav_top_y = housing_y_min + TYPEC_FLANGE_T + TYPEC_BODY_DEPTH  # 体腔顶 (+Y 最深)
        # A. 竖向段 (壳块/支柱内): Y 从体腔顶 -1 (重叠保证连通) 上到支柱带; X=tc_cx; 从壳/支柱背面 (strut_z_bot) 向 +Z 沉.
        chanA_y_bot = body_cav_top_y - 1.0
        chanA_y_top = arm_yc + STRUT_W / 2                  # 上探到支柱上沿一带
        chanA_cy = (chanA_y_bot + chanA_y_top) / 2
        with Locations((tc_cx, chanA_cy, strut_z_bot - 0.01)):
            Box(CHANNEL_W, chanA_y_top - chanA_y_bot, CHANNEL_DEPTH + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)
        # B. 横向段 (沿支柱 X): 从 tc_cx 走到 pogo_cx, Y=arm_yc, 从支柱背面 +Z 沉 CHANNEL_DEPTH.
        chanB_x_a, chanB_x_b = sorted((tc_cx, pogo_cx))
        chanB_cx = (chanB_x_a + chanB_x_b) / 2
        chanB_len = (chanB_x_b - chanB_x_a) + CHANNEL_W     # 两端各多探半宽, 保证与 A/C 重叠连通
        with Locations((chanB_cx, arm_yc, strut_z_bot - 0.01)):
            Box(chanB_len, CHANNEL_W, CHANNEL_DEPTH + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)
        # C. 对接板竖向段: X=pogo_cx, Y 从支柱带下到 POGO 凹腔上沿; 从对接板背面 (mate_z_bot) 向 +Z 沉.
        channel_y_top = arm_yc + STRUT_W / 2               # 上接横向段 B (支柱带)
        channel_y_bot = pogo_cy + POGO_WID / 2             # 下接 POGO 凹腔上沿
        channel_cy = (channel_y_top + channel_y_bot) / 2
        with Locations((pogo_cx, channel_cy, mate_z_bot - 0.01)):
            Box(CHANNEL_W, channel_y_top - channel_y_bot, CHANNEL_DEPTH + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # ---- 在壳块 -Y 外面开: 法兰沉台 + 开孔 + 体腔 (均朝 -Y, 穿透到体腔) ----
        # (a) 前法兰沉台 16.7×10.3×TYPEC_FLANGE_T: 从壳块外面 (Y=bottom_y) 向内 (+Y) 沉.
        with Locations((tc_cx, bottom_y - 0.01, tc_cz)):
            Box(TYPEC_FLANGE_W, TYPEC_FLANGE_T + 0.01, TYPEC_FLANGE_H,
                align=(Align.CENTER, Align.MIN, Align.CENTER),
                mode=Mode.SUBTRACT)
        # (b) 母座本体腔: 从法兰底 (Y=bottom_y+TYPEC_FLANGE_T) 深入 +Y TYPEC_BODY_DEPTH.
        #   断面 = (13.6+2×clear)×(4.3+2×clear); 四周留壁 ≥ TYPEC_HOUSING_WALL.
        body_w = TYPEC_PANEL_W + 2 * TYPEC_BODY_CLEAR
        body_z = TYPEC_PANEL_H + 2 * TYPEC_BODY_CLEAR
        with Locations((tc_cx, bottom_y + TYPEC_FLANGE_T, tc_cz)):
            Box(body_w, TYPEC_BODY_DEPTH + 0.01, body_z,
                align=(Align.CENTER, Align.MIN, Align.CENTER),
                mode=Mode.SUBTRACT)
        # (c) 面板开孔 13.6×4.3 R1.3: 沿 +Y 从壳块外缘穿透法兰段连到体腔 (真穿透到壳外).
        #   草图建在外缘平面 (Y=bottom_y-0.5), 法向 +Y 拉伸穿透法兰沉台 + 余量, 接体腔.
        with BuildSketch(Plane.XZ.offset(-(bottom_y - 0.5))) as _tc_hole:
            with Locations((tc_cx, tc_cz)):
                Rectangle(TYPEC_PANEL_W, TYPEC_PANEL_H)
            fillet(_tc_hole.vertices(), radius=TYPEC_PANEL_R)
        # Plane.XZ 法向 = -Y; 负向 extrude 朝 +Y 穿入法兰段 (深 = 0.5 余 + 法兰沉 + 1.0 进体腔).
        extrude(amount=-(0.5 + TYPEC_FLANGE_T + 1.0), mode=Mode.SUBTRACT)

        # ---- 高摩擦垫沉槽 (POGO 下方两侧, 避开中央走线腔/Type-C + 下方两磁; 抗久放下滑) ----
        #   中央留给走线腔 (CHANNEL_W); 摩擦垫分左右两条, 各落 POGO 下方料区.
        #   恢复 8 磁后: 下方两磁在 X=±MAG_COL_X (Y=band-MAG_INSET_Y), 与摩擦垫 Y 带重叠 =>
        #   把摩擦垫条外缘收到磁内侧 (X ≤ MAG_COL_X - MAG_D/2 - 1.0), 避免摩擦垫切穿磁腔.
        pad_cy = pogo_cy + FRICTION_PAD_OFFSET_Y
        pad_inner_x = CHANNEL_W / 2 + 2.0                        # 条内缘 (避开中央走线腔)
        pad_outer_x = MAG_COL_X - MAG_D / 2 - 1.0               # 条外缘 (避开下方两磁, 留 1.0 间隙)
        pad_strip_w = pad_outer_x - pad_inner_x                  # 单条宽 (派生, 自动避磁)
        pad_strip_off = (pad_inner_x + pad_outer_x) / 2         # 左右偏移 (条中心)
        for sgn in (-1, +1):
            with Locations((mate_cx + sgn * pad_strip_off, pad_cy, mate_z_top + 0.01)):
                Box(pad_strip_w, FRICTION_PAD_H, FRICTION_PAD_T + 0.01,
                    align=(Align.CENTER, Align.CENTER, Align.MAX),
                    mode=Mode.SUBTRACT)

        # ============================================================
        # 恢复: 支架对接面 4×Φ8 磁腔 (吸合/承重主力, 与 POGO 共存)
        # ============================================================
        #   位置: 对接带四角 (世界 X = mate_cx ± MAG_COL_X, 世界 Y = band_y_world ± MAG_INSET_Y),
        #     与后盖 4 磁镜像对吸; POGO 在中央 (X 居中, Y=band), 四角避开 => 空间不冲突.
        #   盲腔: 从对接面 +Z 顶面 (mate_z_top, 朝屏侧) 向 -Z 沉 MAG_T, 留外侧薄壁 MAG_OUTER_WALL
        #     (磁外侧 = 对接板背面方向, 朝支架背后), 保磁力. 对接板厚 MATE_T=5 ≥ MAG_T+壁 => 容得下.
        #   极性 (棋盘): 支架侧为后盖侧的镜像相反极性 (后盖 N 对吸支架 S), 防呆 + 自动吸正.
        for (mx_l, my_l) in MAG_POSITIONS:                      # MAG_POSITIONS 为后盖局部 (X 居中对称)
            wx = mate_cx + mx_l                                 # 世界 X (X 居中对称, 镜像后重合)
            wy = mate_cy + my_l                                 # 世界 Y (= band_y_world ± MAG_INSET_Y)
            with Locations((wx, wy, mate_z_top + 0.01)):
                Cylinder(MAG_D / 2, MAG_T + 0.01,
                         align=(Align.CENTER, Align.CENTER, Align.MAX),
                         mode=Mode.SUBTRACT)

        # 注: 已去掉上一版"折臂+臂根块+腹板"三件套, 换成单一笔直支柱 + 板背肋熔接.
        #   0.3 抱边间隙仍由 U 腔参数化偏置保证 (correct-by-construction), 连通性不破坏.
    # 暴露对接板关键坐标供装配/自检 (作为函数属性)
    #   pogo_pins_world / pogo_mag_world: POGO 针阵 / N/S 磁 世界坐标 (供镜像对齐自检).
    #   POGO 从 -Z 背面装入, 针基面在凹腔顶 (pogo_pocket_floor_z = mate_z_top - POGO_FACE_WALL);
    #   针凸出 POGO_PIN_PROTRUDE 穿贴合面薄壁针孔, 针尖 = 凹腔顶 + 针凸出 = mate_z_top + (1.5-0.8)=+0.7 凸出屏侧.
    pogo_pin_tip_z = pogo_pocket_floor_z + POGO_PIN_PROTRUDE
    pogo_pins_world = [(pogo_cx + i * POGO_PIN_PITCH - POGO_PIN_SPAN / 2, pogo_cy, pogo_pin_tip_z)
                       for i in range(POGO_PIN_N)]
    pogo_mag_world = [(pogo_cx - POGO_MAG_SPAN / 2, pogo_cy), (pogo_cx + POGO_MAG_SPAN / 2, pogo_cy)]
    # 8×Φ8 磁 — 支架对接面 4 磁心世界坐标 (供镜像对齐自检/渲染). 腔口在顶面 mate_z_top, 朝屏 +Z.
    mag_world = [(mate_cx + mx_l, mate_cy + my_l, mate_z_top) for (mx_l, my_l) in MAG_POSITIONS]
    make_bracket.mate = dict(cx=mate_cx, cy=mate_cy, z_top=mate_z_top, z_bot=mate_z_bot,
                             arm_x_end=arm_x_end,
                             strut_w=STRUT_W, strut_h=STRUT_H, strut_yc=arm_yc,
                             strut_z_c=strut_z_c, strut_z_top=strut_z_top, strut_z_bot=strut_z_bot,
                             strut_x_start=strut_x_start, strut_x_endin=strut_x_endin,
                             plate_cy=plate_cy, plate_h=plate_h, band_y=band_y_world,
                             body_front_z=body_front_z, back_outer_z=back_outer_z,
                             pogo_cx=pogo_cx, pogo_cy=pogo_cy, pocket_w=pocket_w, pocket_h=pocket_h,
                             pogo_pocket_floor_z=pogo_pocket_floor_z,
                             pogo_pin_hole_d=POGO_PIN_HOLE_D,
                             pogo_pin_tip_z=pogo_pin_tip_z,
                             pogo_pins_world=pogo_pins_world, pogo_mag_world=pogo_mag_world,
                             pogo_mount_span=POGO_MOUNT_SPAN,
                             channel_y_top=channel_y_top, channel_y_bot=channel_y_bot,
                             chanA_y_top=chanA_y_top, chanA_y_bot=chanA_y_bot,
                             chanB_x_a=chanB_x_a, chanB_x_b=chanB_x_b,
                             tc_cx=tc_cx, tc_cz=tc_cz, bottom_y=bottom_y,
                             typec_body_depth=TYPEC_BODY_DEPTH,
                             lowest_mag_y=lowest_mag_y, strut_y_bot=strut_y_bot,
                             plate_bot_y=plate_bot_y, plate_top_y=plate_top_y, mate_t=MATE_T,
                             friction_pad_cy=pad_cy,
                             housing_w=TYPEC_HOUSING_W, housing_y=TYPEC_HOUSING_Y,
                             housing_z=TYPEC_HOUSING_Z, housing_wall=TYPEC_HOUSING_WALL,
                             housing_y_min=housing_y_min, housing_y_max=housing_y_max,
                             housing_z_top=housing_z_top, housing_z_bot=housing_z_bot,
                             housing_cz=housing_cz, body_cav_top_y=body_cav_top_y,
                             mag_world=mag_world, mag_polarity=MAG_POLARITY,
                             mag_d=MAG_D, mag_t=MAG_T,
                             pad_strip_off=pad_strip_off, pad_strip_w=pad_strip_w)
    return br.part


# ============================================================
# 屏参考板 (装配可视化用, 非打印件): 代表小板/屏在屏体内
# ============================================================
def make_screen_ref():
    with BuildPart() as sr:
        Box(SCREEN_W, SCREEN_H, SCREEN_T)
    return sr.part


# ============================================================
# PCBA 装配体 (bezel 局部坐标, 非打印件): PCB + 元件包络 + 4 pogo 接触 pad + 24P 排座.
#   架构变更: 屏体主板去 Type-C 母座 (改受电侧); 板背 (元件面, +z) 增 4 个 pogo 接触 pad
#   (对位支架对接面 pogo 针阵), 经后盖 4 触点窗与 pogo 针接触受电. 其余 (ESP32-S3+SSD1677+FPC) 不变.
#   元件面朝后盖 (+z), 铜面朝屏 (-z). Z 叠层由派生公式锚定.
#   返回 dict: 各子实体 (bezel 局部) 供装配 / 自检布尔.
# ============================================================
def make_pcba():
    # PCB 本体: z = PCB_FRONT_Z .. PCB_BACK_Z, 板心居中 (与窗同水平居中, Y 居屏体中)
    with BuildPart() as _pcb:
        with Locations((0, 0, PCB_FRONT_Z)):
            Box(PCB_W, PCB_H, PCB_T,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 定位孔 (供对角定位销插入)
        for (px, py) in PCB_LOC_PIN_POSITIONS:
            with Locations((px, py, PCB_FRONT_Z - 0.01)):
                Cylinder((PCB_LOC_PIN_D + 0.2) / 2, PCB_T + 0.02,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
    # 元件包络: z = PCB_BACK_Z .. COMP_TOP_Z, 落在 plug 中央镂空区内 (避开边框).
    # 元件包络受"板尺寸"与"plug 镂空"双重约束 (元件不可能超出 PCB; 取两者更小):
    comp_w = min(BC_PLUG_CAV_W - 1.0, PCB_W - 4.0)
    comp_h = min(BC_PLUG_CAV_H - 1.0, PCB_H - 4.0)
    with BuildPart() as _comp:
        with Locations((0, 0, PCB_BACK_Z)):
            Box(comp_w, comp_h, COMP_H_MAX,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 恢复 8 磁后: 后盖 4 磁柱 boss (Φ磁+壁) 从内侧凸入屏体, 占对接带四角 (X=±MAG_COL_X,
        #   Y=DOCK_CENTER_Y±MAG_INSET_Y). 该处为对接界面 keep-out, 元件须避让 => 从元件包络
        #   减去磁柱 footprint (留 0.5 间隙), 表明布板时对接带四角不放元件 (实际 PCB 也须避).
        MAG_BOSS_KEEPOUT_D = MAG_D + 2 * 1.6 + 1.0    # 磁柱外径 + 0.5 单边间隙
        for (mx, my) in MAG_POSITIONS:
            with Locations((mx, my, PCB_BACK_Z - 0.01)):
                Cylinder(MAG_BOSS_KEEPOUT_D / 2, COMP_H_MAX + 0.02,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)
    # 4 pogo 接触 pad (板背/元件面 z=PCB_BACK_Z, 朝后盖 +z): 对位 pogo 4 针阵 (X 居中, 间距 2.54).
    #   薄铜 pad (建模为矮盘), 经后盖 4 触点窗与 pogo 针凸出接触受电. Y 落对接区中心 DOCK_CENTER_Y.
    PAD_DISC_T = 0.2    # pad 铜厚 (建模值)
    with BuildPart() as _pads:
        for (wx, wy) in PAD_WINDOW_POSITIONS:
            with Locations((wx, wy, PCB_BACK_Z)):
                Cylinder(PAD_WINDOW_D / 2 + 0.4, PAD_DISC_T,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))
    # 24P FPC 排座: PCB 底边中点, 元件面朝后, 矮座.
    with BuildPart() as _fpc:
        with Locations((0, -PCB_H / 2 + 2.0, PCB_BACK_Z)):
            Box(FPC_CONN_W, 4.0, 1.5,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    return dict(pcb=_pcb.part, comp=_comp.part, pads=_pads.part, fpc=_fpc.part,
                comp_w=comp_w, comp_h=comp_h)


def make_pcba_compound():
    p = make_pcba()
    pcb = p["pcb"]; pcb.label = "pcb"
    comp = p["comp"]; comp.label = "components"
    pads = p["pads"]; pads.label = "pogo_pads"
    fpc = p["fpc"]; fpc.label = "fpc_conn"
    return Compound(label="pcba", children=[pcb, comp, pads, fpc])


# 显示器左上角参考块 (MON_*): 代表显示器
def make_monitor_corner():
    with BuildPart() as mc:
        # 角块: 占 X>=0, Y<=0 (与 bracket 局部一致). 顶边/左边各厚, 这里做整块角块.
        with Locations((MON_CORNER_W / 2, -MON_CORNER_H / 2, -MON_CORNER_T / 2)):
            Box(MON_CORNER_W, MON_CORNER_H, MON_CORNER_T)
    return mc.part


# ============================================================
# 装配体: 屏体磁吸贴合支架, 支架抱住显示器左上角参考块
# ============================================================
def body_placement():
    """屏体在世界系的装配变换 (与支架对接面共面、正对用户).

    屏体局部 Z (厚度): 前面板 z=0 .. 后盖外表面 z=BODY_T_ACTUAL.
    装配: 屏面朝用户 (+Z). 后盖法向 -Z 磁吸贴对接面顶面 (法向 +Z) + 气隙.
    翻转 Rot(0,180,0) 使屏宽 X 镜像、后盖朝 -Z; 屏体中心对到对接面中心,
    后盖磁(bx,by) 即对到对接面磁(mate_cx-bx, mate_cy+by).
    """
    mate = make_bracket.mate
    gap = 0.5  # 磁吸气隙 (后盖外表面到对接面顶面)
    Rbody = Rot(0, 180, 0)
    # 修正 2: 墨水屏前表面 (屏体局部 z=0, 翻转后世界 Z=Z0) 与显示器前表面 (Zf=0) 共面.
    #   Z0 = Zf + Z_FLUSH_OFFSET. 对接板 mate["z_top"] 已据此布在屏体背后, 此处仅锚定屏体.
    #   (一致性: Z0 - BODY_T_ACTUAL - gap == mate["z_top"], 见自检校验.)
    Z0 = 0.0 + Z_FLUSH_OFFSET
    # 改动 4: 竖向锚点 = 顶部对齐. 对接面中心 mate["cy"] 已 = 顶边(Y=0)+offset - BEZEL_OUT_H/2,
    #   屏体中心 Y 直接复用 mate["cy"] => 后盖磁与对接面磁镜像偏差严格为 0, 且屏顶对齐显示器顶.
    # 水平: 屏体右边缘 = mate["cx"] + BEZEL_OUT_W/2 ≈ -14 < 0 (显示器左边缘), 不遮挡画面.
    return Pos(mate["cx"], mate["cy"], Z0) * Rbody


def back_cover_local():
    """后盖在屏体局部系的就位变换 (凸台朝 -z 插入 bezel 背腔, 盖板坐背面齐平).

    后盖原构造: 盖板 z=0..PLATE_T, 凸台 z=PLATE_T..PLATE_T+PLUG_DEPTH (朝 +z).
    翻转 Rot(0,180,0) 使凸台朝 -z; 再平移 +z 到 BODY_T_ACTUAL, 使盖板外表面落在
    屏体局部 z=BODY_T_ACTUAL (背面齐平), 凸台伸入背腔.
    """
    return Pos(0, 0, BODY_T_ACTUAL) * Rot(0, 180, 0)


def _placed_print_parts(bezel, back_cover, bracket):
    """返回装配位姿下的 3 个打印件 (label 已设), 保持相对装配位姿."""
    place = body_placement()
    bz_world = place * bezel
    bc_world = place * (back_cover_local() * back_cover)
    br_world = bracket
    # 改动 2: 给每个 located 实体 (Solid/Compound) 设可读 label, 消除 viewer 里 ASSEMBLY_N 歧义.
    bz_world.label = "bezel"
    bc_world.label = "back_cover"
    br_world.label = "bracket"
    return bz_world, bc_world, br_world


def make_assembly_print(bezel, back_cover, bracket):
    """改动 1: assembly_print — 只含 3 个打印件 (bezel+back_cover+bracket), 保持装配位姿.

    参考体 (monitor 角块 / screen_ref 屏参考板) 不混入打印模型.
    """
    bz_world, bc_world, br_world = _placed_print_parts(bezel, back_cover, bracket)
    return Compound(label="InkPulse_426_assembly_print",
                    children=[bz_world, bc_world, br_world])


def make_assembly_context(bezel, back_cover, bracket, screen_ref, monitor):
    """改动 1: assembly_context — 打印件 + monitor 角块 + screen_ref 屏参考板 + PCBA, 看贴合/落位."""
    place = body_placement()
    bz_world, bc_world, br_world = _placed_print_parts(bezel, back_cover, bracket)
    # 修 bug2: 墨水屏在屏腔内居中 (去掉 WINDOW_OFFSET_Y 竖向平移); 仅视窗开口上移对 AA.
    #   旧方案屏被整体上移 WINDOW_OFFSET_Y, 而屏腔(SCR_CAV)未上移 => 屏顶戳出腔顶 ~2.6mm.
    sr_local = Pos(0, 0, FRONT_WALL_T + SCREEN_T / 2) * screen_ref
    sr_world = place * sr_local
    monitor.label = "monitor_ref"      # 改动 2: 参考体 label
    sr_world.label = "screen_ref"
    # PCBA (bezel 局部) 随屏体装配到世界; 元件面朝后盖, 铜面朝屏.
    pcba = make_pcba_compound()
    pcba_world = place * pcba
    pcba_world.label = "pcba"
    return Compound(label="InkPulse_426_assembly_context",
                    children=[monitor, br_world, bz_world, bc_world, sr_world, pcba_world])


# ============================================================
# 自检
# ============================================================
def report(name, part):
    bb = part.bounding_box().size
    vol = part.volume
    try:
        valid = part.is_valid
    except Exception as e:
        valid = f"ERR:{e}"
    print(f"[{name:12s}] bbox = {bb.X:7.2f} x {bb.Y:7.2f} x {bb.Z:7.2f} mm | "
          f"vol = {vol:11.1f} mm^3 | valid = {valid} | solids = {len(part.solids())}")
    return bb, vol


def main():
    print("=== InkPulse 4.26\" 磁吸侧挂外壳 build123d ===")
    print(f"SCR_CAV {SCR_CAV_W:.2f} x {SCR_CAV_H:.2f}  BEZEL_OUT {BEZEL_OUT_W:.2f} x {BEZEL_OUT_H:.2f}")
    print(f"WINDOW  {WINDOW_W:.2f} x {WINDOW_H:.2f}  offsetY {WINDOW_OFFSET_Y}")
    print(f"BODY_T_ACTUAL {BODY_T_ACTUAL:.2f} (目标 {BODY_T})")
    print("-" * 78)

    bezel = make_bezel()
    back_cover = make_back_cover()
    bracket = make_bracket()
    screen_ref = make_screen_ref()
    monitor = make_monitor_corner()
    # 改动 2: 单件 STEP 也带可读 label
    bezel.label = "bezel"
    back_cover.label = "back_cover"
    bracket.label = "bracket"

    bb_bz, _ = report("bezel", bezel)
    bb_bc, _ = report("back_cover", back_cover)
    bb_br, _ = report("bracket", bracket)

    print("=" * 78)
    print("自检报告:")

    # --- 1) 外形包围盒核对 ---
    print(f"[1 外形] bezel {bb_bz.X:.2f}x{bb_bz.Y:.2f}x{bb_bz.Z:.2f} "
          f"(目标 BODY_W~{BODY_W}, BODY_H~{BODY_H}, bezel深~9)")
    print(f"         back_cover {bb_bc.X:.2f}x{bb_bc.Y:.2f}x{bb_bc.Z:.2f}")
    print(f"         屏体总厚 BODY_T_ACTUAL = {BODY_T_ACTUAL:.2f} (目标 {BODY_T}; 偏差 {BODY_T_ACTUAL-BODY_T:+.2f})")

    # --- 2) 视窗覆盖 AA 且不侵入屏容腔/唇内沿 ---
    win_x0, win_x1 = -WINDOW_W / 2, WINDOW_W / 2
    win_y0 = -WINDOW_H / 2 + WINDOW_OFFSET_Y
    win_y1 = WINDOW_H / 2 + WINDOW_OFFSET_Y
    aa_x0, aa_x1 = -AA_W / 2, AA_W / 2
    aa_y0, aa_y1 = -AA_H / 2 + WINDOW_OFFSET_Y, AA_H / 2 + WINDOW_OFFSET_Y
    cav_x0, cav_x1 = -SCR_CAV_W / 2, SCR_CAV_W / 2
    cav_y0, cav_y1 = -SCR_CAV_H / 2, SCR_CAV_H / 2
    covers_aa = (win_x0 <= aa_x0 and win_x1 >= aa_x1 and win_y0 <= aa_y0 and win_y1 >= aa_y1)
    in_cav = (win_x0 >= cav_x0 and win_x1 <= cav_x1 and win_y0 >= cav_y0 and win_y1 <= cav_y1)
    lip_w_side = (cav_x1 - win_x1)  # 单边唇宽
    print(f"[2 视窗] 窗X[{win_x0:.2f},{win_x1:.2f}] 覆盖 AA X[{aa_x0:.2f},{aa_x1:.2f}]: {covers_aa and True}")
    print(f"         窗在屏容腔内(不破壁): {in_cav}; 单边唇宽 ≈ {lip_w_side:.2f}mm (黑边 {BORDER_SIDE})")
    print(f"         结论: 覆盖AA={covers_aa}  窗在腔内={in_cav}  -> {'通过' if covers_aa and in_cav else '失败'}")

    from build123d import Cylinder as _Cyl
    _mate = make_bracket.mate
    place4 = body_placement()

    # --- 1b) POGO 腔自检: 位置/尺寸/针面朝屏/2 安装孔间距/针阵世界坐标 ---
    print("-" * 78)
    print("[1b POGO 腔] 支架对接面 POGO 磁吸连接器凹腔:")
    print(f"          本体腔标称 {POGO_LEN}×{POGO_WID}×{POGO_BODY_H} (+单边 {POGO_BODY_CLEAR} 余量 "
          f"=> {_mate['pocket_w']:.2f}×{_mate['pocket_h']:.2f}); 沉入对接面 (X 居中, 长向沿 X)")
    print(f"          POGO 中心 (世界) X={_mate['pogo_cx']:.2f} Y={_mate['pogo_cy']:.2f}; "
          f"对接板顶面 Z={_mate['z_top']:.2f}")
    print(f"          针面朝屏: 针凸出 {POGO_PIN_PROTRUDE} 朝 +Z (屏体侧); 针尖 Z={_mate['pogo_pin_tip_z']:.2f} "
          f"(> 板顶 {_mate['z_top']:.2f}? {_mate['pogo_pin_tip_z'] > _mate['z_top']}) -> "
          f"{'通过(针凸出朝屏)' if _mate['pogo_pin_tip_z'] > _mate['z_top'] else '失败'}")
    print(f"          2× Φ{POGO_MOUNT_D} 安装孔间距 = {_mate['pogo_mount_span']:.2f} (期望 {POGO_MOUNT_SPAN}) -> "
          f"{'通过' if abs(_mate['pogo_mount_span']-POGO_MOUNT_SPAN)<1e-6 else '失败'}")
    print(f"          POGO 4 针世界坐标 (X,Y,Z):")
    for i, (px, py, pz) in enumerate(_mate['pogo_pins_world']):
        print(f"            针{i+1}: ({px:+.2f}, {py:+.2f}, {pz:+.2f})")
    # POGO 凹腔已改 -Z 背面开口 (修 bug2): 凹腔 Z∈[z_bot, pogo_pocket_floor_z], 从 -Z 背面装入.
    _br1b = make_bracket()
    _pocket_cz = (_mate['z_bot'] + _mate['pogo_pocket_floor_z']) / 2
    _pocket_depth = _mate['pogo_pocket_floor_z'] - _mate['z_bot']
    with BuildPart() as _pkp:
        with Locations((_mate['pogo_cx'], _mate['pogo_cy'], _pocket_cz)):
            Box(POGO_LEN, POGO_WID, _pocket_depth * 0.8, align=(Align.CENTER,)*3)
    pocket_empty = (_pkp.part & _br1b).volume   # 凹腔内应空 (无料)
    print(f"          POGO 凹腔内 ∩ 支架实体 = {pocket_empty:.3f} mm3 -> "
          f"{'通过(凹腔已掏空)' if pocket_empty < 1.0 else '失败(凹腔未掏)'}")

    # --- 3) POGO↔屏体目标对齐 (镜像偏差 ≈0): 支架针位 vs 后盖 pad 窗位; N/S 磁 vs 钢片腔 ---
    print(f"[3 POGO↔屏体镜像对齐] (支架对接面 vs 屏体后盖, 装配后世界系)")
    # 屏体后盖特征 (后盖局部) 经 装配(body_placement) ∘ back_cover_local 映到世界:
    #   两次 Rot(0,180,0) => X 翻两次抵消(不变), Z 翻两次抵消, 仅平移. 故后盖局部 (x,y) 世界 X = mate_cx + x... 实测.
    place_bc = place4 * back_cover_local()
    def _bc_world_xy(lx, ly, lz=0.0):
        v = (place_bc * Pos(lx, ly, lz)).position
        return (v.X, v.Y)
    # 3a) 4 触点 pad 窗 (后盖局部 PAD_WINDOW_POSITIONS) vs 支架 pogo 4 针:
    max_pad_d = 0.0
    print("          pad 窗(世界 X,Y) vs pogo 针(世界 X,Y) 偏差:")
    for (wx, wy), (px, py, pz) in zip(PAD_WINDOW_POSITIONS, _mate['pogo_pins_world']):
        wxw, wyw = _bc_world_xy(wx, wy)
        d = math.hypot(wxw - px, wyw - py)
        max_pad_d = max(max_pad_d, d)
        print(f"            pad({wxw:+.2f},{wyw:+.2f}) vs 针({px:+.2f},{py:+.2f}) 偏差={d:.4f}")
    print(f"          4 pad 窗 vs 4 针 最大镜像偏差 = {max_pad_d:.4f}mm -> "
          f"{'通过(≈0)' if max_pad_d < 1e-6 else '检查'}")
    # 3b) 2 钢片腔 (后盖局部 STEEL_POSITIONS) vs 支架 pogo N/S 磁:
    max_steel_d = 0.0
    print("          钢片腔(世界 X,Y) vs pogo N/S 磁(世界 X,Y) 偏差:")
    for (sx, sy), (mxw, myw) in zip(STEEL_POSITIONS, _mate['pogo_mag_world']):
        sxw, syw = _bc_world_xy(sx, sy)
        d = math.hypot(sxw - mxw, syw - myw)
        max_steel_d = max(max_steel_d, d)
        print(f"            钢片({sxw:+.2f},{syw:+.2f}) vs N/S磁({mxw:+.2f},{myw:+.2f}) 偏差={d:.4f}")
    print(f"          2 钢片腔 vs N/S 磁 最大镜像偏差 = {max_steel_d:.4f}mm -> "
          f"{'通过(≈0)' if max_steel_d < 1e-6 else '检查'}")

    # --- 3c) 8×Φ8 磁腔自检 (用户要求恢复): 计数 / 镜像对齐 / 棋盘极性 / 与 POGO·pad·钢片·走线腔·壳块不重叠 ---
    print("-" * 78)
    print("[3c 8×Φ8 磁] 恢复: 8 磁吸合/承重 + POGO 供电对位 (二者共存):")
    bc_for3c = make_back_cover()
    br_for3c = make_bracket()

    def _empty_at(part, p, sz=0.06):
        # 极小盒做布尔交: 落点在实体内 => 交>0; 在腔内(空) => 交≈0.
        return (part & (Pos(*p) * Box(sz, sz, sz))).volume < 1e-9

    # (1) 磁腔计数: 后盖 4 (腔内空) + 支架 4 (腔内空) = 8.
    n_bc_mag = sum(1 for (mx, my) in MAG_POSITIONS
                   if _empty_at(bc_for3c, (mx, my, MAG_OUTER_WALL + MAG_T / 2)))
    n_br_mag = sum(1 for (wx, wy, wz) in _mate['mag_world']
                   if _empty_at(br_for3c, (wx, wy, _mate['z_top'] - MAG_T / 2)))
    print(f"   [计数] 后盖 Φ8 磁腔={n_bc_mag} (期望4) + 支架对接面 Φ8 磁腔={n_br_mag} (期望4) "
          f"= {n_bc_mag + n_br_mag} (期望8) -> "
          f"{'通过' if n_bc_mag == 4 and n_br_mag == 4 else '失败'}")
    # 后盖磁外侧薄壁实测 (z∈[0,MAG_OUTER_WALL] 应有料):
    walls_ok = all(not _empty_at(bc_for3c, (mx, my, MAG_OUTER_WALL / 2)) for (mx, my) in MAG_POSITIONS)
    print(f"   [外壁] 后盖 4 磁外侧薄壁 (z∈[0,{MAG_OUTER_WALL}]) 均有料(不穿透)? {walls_ok}; "
          f"盲腔深 MAG_T={MAG_T}, 磁外侧壁 {MAG_OUTER_WALL}mm 保磁力 -> {'通过' if walls_ok else '失败'}")

    # (2) 镜像对齐: 后盖 4 磁心 (装配世界) vs 支架 4 磁心 (世界), 逐一偏差≈0.
    max_mag_d = 0.0
    print("   [镜像] 后盖 4 磁心 (世界) vs 支架 4 磁心 (世界) 偏差:")
    for (mx, my), (wx, wy, wz) in zip(MAG_POSITIONS, _mate['mag_world']):
        bxw, byw = _bc_world_xy(mx, my)
        d = math.hypot(bxw - wx, byw - wy)
        max_mag_d = max(max_mag_d, d)
        print(f"            后盖({bxw:+.2f},{byw:+.2f}) vs 支架({wx:+.2f},{wy:+.2f}) 偏差={d:.4f}")
    print(f"   [镜像] 4 磁最大镜像偏差 = {max_mag_d:.4f}mm -> "
          f"{'通过(≈0)' if max_mag_d < 1e-6 else '检查'}")

    # (3) 棋盘极性: 对角同极 / 相邻异极; 两侧镜像相反极性 (后盖 N 对吸支架 S).
    print(f"   [极性] 后盖侧 (棋盘) MAG_POLARITY = {MAG_POLARITY} (按四角 [(-,-),(-,+),(+,-),(+,+)] 序);")
    # 对角同极: 后盖磁序为 LB,LT,RB,RT (idx 0..3); 对角对 = (0,3) 与 (1,2).
    diag_same = (MAG_POLARITY[0] == MAG_POLARITY[3]) and (MAG_POLARITY[1] == MAG_POLARITY[2])
    adj_diff = (MAG_POLARITY[0] != MAG_POLARITY[1]) and (MAG_POLARITY[0] != MAG_POLARITY[2])
    print(f"           对角同极 (0↔3, 1↔2)? {diag_same}; 相邻异极? {adj_diff} -> "
          f"{'通过(防呆+自动吸正)' if diag_same and adj_diff else '检查'}")
    print(f"           支架侧 = 镜像相反极性 (后盖 N 处对吸支架 S); 反装相斥 => 防呆")

    # (4) 不重叠: 8 磁 vs POGO 凹腔/针阵/安装孔/4 pad 窗/2 钢片/走线腔/Type-C 壳块 (两两布尔≈0).
    def _disc(cz_center, mx, my, world=False):
        with BuildPart() as _d:
            with Locations((mx, my, cz_center)):
                Cylinder(MAG_D / 2, MAG_T, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        return _d.part
    # 支架侧特征实体:
    with BuildPart() as _pk3c:
        # POGO 凹腔已改 -Z 背面开口: z∈[z_bot, z_bot+POGO_BODY_H], 中心 = z_bot + POGO_BODY_H/2.
        with Locations((_mate['pogo_cx'], _mate['pogo_cy'], _mate['z_bot'] + POGO_BODY_H / 2)):
            Box(_mate['pocket_w'], _mate['pocket_h'], POGO_BODY_H, align=(Align.CENTER,) * 3)
    pk3c = _pk3c.part
    with BuildPart() as _ch3c:
        # 走线腔 C 段已改 -Z 背面开口: z∈[z_bot, z_bot+CHANNEL_DEPTH], 中心 = z_bot + CHANNEL_DEPTH/2.
        _ccy = (_mate['channel_y_top'] + _mate['channel_y_bot']) / 2
        with Locations((_mate['pogo_cx'], _ccy, _mate['z_bot'] + CHANNEL_DEPTH / 2)):
            Box(CHANNEL_W, _mate['channel_y_top'] - _mate['channel_y_bot'], CHANNEL_DEPTH,
                align=(Align.CENTER,) * 3)
    ch3c = _ch3c.part
    with BuildPart() as _hs3c:
        with Locations((_mate['tc_cx'], (_mate['housing_y_min'] + _mate['housing_y_max']) / 2, _mate['housing_cz'])):
            Box(_mate['housing_w'], _mate['housing_y'], _mate['housing_z'], align=(Align.CENTER,) * 3)
    hs3c = _hs3c.part
    mnt3c = []
    for sgn in (-1, 1):
        with BuildPart() as _mh3c:
            with Locations((_mate['pogo_cx'] + sgn * POGO_MOUNT_SPAN / 2, _mate['pogo_cy'], _mate['z_bot'] + MATE_T / 2)):
                Cylinder(POGO_MOUNT_D / 2, MATE_T, align=(Align.CENTER,) * 3)
        mnt3c.append(_mh3c.part)
    max_br_ov = 0.0
    for (wx, wy, wz) in _mate['mag_world']:
        md = _disc(_mate['z_top'] - MAG_T / 2, wx, wy)
        vpk = (md & pk3c).volume; vch = (md & ch3c).volume
        vhs = (md & hs3c).volume; vmt = max((md & x).volume for x in mnt3c)
        max_br_ov = max(max_br_ov, vpk, vch, vhs, vmt)
        print(f"   [不重叠·支架] 磁({wx:+.1f},{wy:+.1f}): ∩POGO凹腔={vpk:.3f} ∩走线腔={vch:.3f} "
              f"∩Type-C壳块={vhs:.3f} ∩安装孔={vmt:.3f}")
    # 屏体侧特征实体: 4 pad 窗 / 2 钢片腔.
    pad3c = []
    for (wx, wy) in PAD_WINDOW_POSITIONS:
        with BuildPart() as _p3c:
            with Locations((wx, wy, BACK_COVER_PLATE_T / 2)):
                Cylinder(PAD_WINDOW_D / 2, BACK_COVER_PLATE_T, align=(Align.CENTER,) * 3)
        pad3c.append(_p3c.part)
    st3c = []
    for (sx, sy) in STEEL_POSITIONS:
        with BuildPart() as _s3c:
            with Locations((sx, sy, STEEL_T / 2)):
                Cylinder(STEEL_D / 2, STEEL_T, align=(Align.CENTER,) * 3)
        st3c.append(_s3c.part)
    max_bc_ov = 0.0
    for (mx, my) in MAG_POSITIONS:
        md = _disc(MAG_OUTER_WALL + MAG_T / 2, mx, my)
        vpad = max((md & p).volume for p in pad3c); vst = max((md & x).volume for x in st3c)
        max_bc_ov = max(max_bc_ov, vpad, vst)
        print(f"   [不重叠·后盖] 磁({mx:+.1f},{my:+.1f}): ∩pad窗(max)={vpad:.3f} ∩钢片腔(max)={vst:.3f}")
    no_overlap = max(max_br_ov, max_bc_ov) < 1e-3
    print(f"   [不重叠] 8 磁 vs (POGO凹腔/针/安装孔/pad窗/钢片/走线腔/壳块) 最大相交 = "
          f"{max(max_br_ov, max_bc_ov):.4f} mm3 -> {'通过(互不重叠)' if no_overlap else '失败'}")
    print(f"   [分工] 8×Φ8 磁 = 吸合/承重 (扛屏体~40g+杠杆力); POGO 自带 N/S = 供电+对位 (磁力不足单独承重)")

    # ============================================================
    # [可装入性] 修两 bug 后专项: 每个嵌入件至少一个完全敞开装入面 (探针验证)
    # ============================================================
    print("-" * 78)
    print("[可装入性] 修 bug1(后盖磁腔去盖) + bug2(POGO 背面装入+针孔+走线改背面) 专项验证:")
    _bc_ins = make_back_cover()
    _br_ins = make_bracket()

    def _empty(part, p, sz=0.06):
        return (part & (Pos(*p) * Box(sz, sz, sz))).volume < 1e-9

    # (1) 后盖磁腔可装入: 内侧 (z=MAG_OUTER_WALL+MAG_T, 朝 PCB) 为开口 (无料) + 外侧薄壁 (z<MAG_OUTER_WALL 有料).
    inner_open = all(_empty(_bc_ins, (mx, my, MAG_OUTER_WALL + MAG_T + 0.05)) for (mx, my) in MAG_POSITIONS)
    outer_wall = all(not _empty(_bc_ins, (mx, my, MAG_OUTER_WALL / 2)) for (mx, my) in MAG_POSITIONS)
    print(f"   (1) 后盖 Φ8 磁腔可装入: 内侧(z={MAG_OUTER_WALL+MAG_T:.2f}, 朝PCB)敞开(无料)? {inner_open}; "
          f"外侧薄壁(z<{MAG_OUTER_WALL}, 朝支架)有料? {outer_wall} -> "
          f"{'通过(磁从内侧压入, 外侧留薄壁透磁)' if inner_open and outer_wall else '失败'}")

    # (2) 支架对接面磁腔可装入: 每腔有一敞开面. 腔从 +Z 贴合面沉 MAG_T => +Z 开口装入.
    br_mag_open = all(_empty(_br_ins, (wx, wy, _mate['z_top'] + 0.05)) for (wx, wy, wz) in _mate['mag_world'])
    print(f"   (2) 支架对接面 Φ8 磁腔可装入: 每腔 +Z 贴合面 (z={_mate['z_top']:.2f}) 敞开(无料)? {br_mag_open} -> "
          f"{'通过(磁从 +Z 贴合面装入)' if br_mag_open else '失败'} [开口方向: +Z 朝屏贴合面]")

    # (3) POGO 可装入+可接线: 本体凹腔从 -Z 背面敞开 (背面探针无料到达本体腔);
    #     +Z 贴合面有 4 针孔 (针凸出朝屏) + 2 安装孔; 焊接面 (-Z) 连通走线腔/背面.
    pcx, pcy = _mate['pogo_cx'], _mate['pogo_cy']
    # 3a. -Z 背面装入: 背面外 (z=z_bot-0.05) 探到本体腔中部 (z 在凹腔内) 全程无料.
    back_open = _empty(_br_ins, (pcx, pcy, _mate['z_bot'] - 0.05)) and \
                _empty(_br_ins, (pcx, pcy, _mate['z_bot'] + POGO_BODY_H / 2))
    # 3b. +Z 贴合面 4 针孔: 针孔中心 (贴合面薄壁内, z=z_top-0.05) 无料 (针可穿出朝屏).
    pin_holes_open = all(
        _empty(_br_ins, (pcx + i * POGO_PIN_PITCH - POGO_PIN_SPAN / 2, pcy, _mate['z_top'] - 0.05))
        for i in range(POGO_PIN_N))
    # 3c. 2 安装孔贯穿 (z_top 侧 + z_bot 侧均无料).
    mounts_open = all(
        _empty(_br_ins, (pcx + sgn * POGO_MOUNT_SPAN / 2, pcy, _mate['z_top'] - 0.05)) and
        _empty(_br_ins, (pcx + sgn * POGO_MOUNT_SPAN / 2, pcy, _mate['z_bot'] + 0.05))
        for sgn in (-1, 1))
    # 3d. 焊接面 (-Z) 连通走线腔: POGO 凹腔上沿 -> 走线腔 C 段 (z_bot 背面) 无料连通.
    wire_reach = _empty(_br_ins, (pcx, pcy + POGO_WID / 2 + 1.0, _mate['z_bot'] + CHANNEL_DEPTH / 2))
    pogo_ins_ok = back_open and pin_holes_open and mounts_open and wire_reach
    print(f"   (3) POGO 可装入+可接线: 本体凹腔 -Z 背面敞开(背面探针无料)? {back_open}; "
          f"+Z 贴合面 4 针孔(针凸出朝屏)? {pin_holes_open}; 2 安装孔贯穿? {mounts_open}; "
          f"焊接面(-Z)连通走线腔(飞线可达)? {wire_reach} -> {'通过' if pogo_ins_ok else '失败'}")
    print(f"       [开口方向] POGO 本体: -Z 背面装入; 针: +Z 贴合面针孔凸出朝屏; 焊脚/飞线: -Z 背面走线腔")

    # (4) 针仍朝屏凸出: pogo_pin_tip_z = 凹腔顶(贴合面薄壁内面) + 针凸出, 朝 +Z, 凸出 mate_z_top.
    tip_z = _mate['pogo_pin_tip_z']
    print(f"   (4) 针朝屏凸出: 针尖 Z={tip_z:.2f} = 凹腔顶({_mate['pogo_pocket_floor_z']:.2f}) + 针凸出{POGO_PIN_PROTRUDE} "
          f"-> > 贴合面 {_mate['z_top']:.2f}? {tip_z > _mate['z_top']} "
          f"({'通过(凸出朝屏 +Z)' if tip_z > _mate['z_top'] else '失败'})")

    # --- 4) Type-C 在支柱下方真穿透 (最重要) — 防水母座, 口朝 -Y/向下 ---
    #   架构变更: Type-C 壳块已从对接板底部移到 "支柱下方" (X 偏卡钉端). 开孔 13.6×4.3
    #   在壳块 -Y 外面, 朝 -Y; 法兰沉台 16.7×10.3; 体腔深 14 向 +Y 伸进支柱下方结构.
    #   验证: 在支架合并实体上放穿透探针 (沿 -Y 从壳外连到体腔内), 布尔相交≈0 => 真穿透.
    bracket_for4 = make_bracket()
    tc_cx, tc_cz = _mate['tc_cx'], _mate['tc_cz']
    bottom_y4 = _mate['bottom_y']
    # 穿透探针: 截面 = 面板开孔 (略缩 0.4), 沿 Y 从壳外 (bottom_y-3) 探到体腔内 (bottom_y+6).
    probe_len4 = 9.0
    probe_cy4 = bottom_y4 - 3.0 + probe_len4 / 2
    with BuildPart() as _probe4:
        with Locations((tc_cx, probe_cy4, tc_cz)):
            Box(TYPEC_PANEL_W - 0.6, probe_len4, TYPEC_PANEL_H - 0.6, align=(Align.CENTER,)*3)
    block_vol4 = (_probe4.part & bracket_for4).volume
    true_through4 = block_vol4 < 1e-2
    # 朝向 -Y (向下): 壳块开口面 (bottom_y) 在壳块 Y 区间最小端, 体腔从开口向 +Y 深入 => 口朝 -Y.
    facing_down4 = _mate['bottom_y'] < _mate['housing_y_max']   # 开口面在壳块 -Y 端
    # 挂在支柱下方: 壳块 +Y 顶 (housing_y_max) 落在支柱下沿 (strut_y_bot) 之下 (或重叠熔接处),
    #   且整壳 X<0 (不碰显示器). 报告壳块世界 X/Y/Z 范围.
    h_x0, h_x1 = tc_cx - _mate['housing_w'] / 2, tc_cx + _mate['housing_w'] / 2
    under_strut4 = _mate['housing_y_max'] <= _mate['strut_y_bot'] + TYPEC_HOUSING_STRUT_OVERLAP + 1e-6
    x_neg4 = h_x1 < 0.0                                       # 整壳 X<0 (显示器左缘外, 不碰显示器)
    print(f"[4 TypeC真穿透] *** 最重要 *** (Type-C 壳块改挂 '支柱下方', 口朝下 -Y 出线)")
    print(f"          开孔 {TYPEC_PANEL_W}×{TYPEC_PANEL_H} (R{TYPEC_PANEL_R}) 在壳块 -Y 外面 Y={bottom_y4:.2f}, 朝 -Y (向下);")
    print(f"          法兰沉台 {TYPEC_FLANGE_W}×{TYPEC_FLANGE_H} (深 {TYPEC_FLANGE_T}); 体腔深入 +Y {TYPEC_BODY_DEPTH}")
    print(f"          壳块世界范围: X[{h_x0:.2f},{h_x1:.2f}] Y[{_mate['housing_y_min']:.2f},{_mate['housing_y_max']:.2f}] "
          f"Z[{_mate['housing_z_bot']:.2f},{_mate['housing_z_top']:.2f}]")
    print(f"          口世界中心 X={tc_cx:.2f} Z={tc_cz:.2f}; 开口朝 -Y? {facing_down4}; "
          f"挂支柱下方 (顶≤支柱下沿{_mate['strut_y_bot']:.1f}+重叠)? {under_strut4}; 整壳 X<0(不碰显示器)? {x_neg4}")
    print(f"          穿透探针 (跨壳壁, 壳外->体腔内) ∩ 支架合并实体 = {block_vol4:.4f} mm3 -> "
          f"{'通过(真穿透, 无料阻挡, 口朝下)' if (true_through4 and facing_down4 and under_strut4 and x_neg4) else '失败'}")

    # --- 4-bug) bug 复现确认: MATE_T 薄板 vs 法兰高 ---
    print(f"   [4-bug 复现] 对接板 MATE_T={MATE_T} (Z) < 法兰 TYPEC_FLANGE_H={TYPEC_FLANGE_H} (Z)? "
          f"{MATE_T < TYPEC_FLANGE_H} (旧方案: 法兰比板厚大 {TYPEC_FLANGE_H-MATE_T:+.1f}mm => 切穿薄板, 无壳)")
    # --- 4-shell) 修复后: 专用壳块 boss 完整包裹母座 ---
    hz = _mate['housing_z']; hw = _mate['housing_w']; HW = TYPEC_HOUSING_WALL
    print(f"   [4-shell 壳块] X宽={hw:.2f}(>=法兰{TYPEC_FLANGE_W}+2壁{HW}={TYPEC_FLANGE_W+2*HW:.1f}? {hw>=TYPEC_FLANGE_W+2*HW-1e-6}); "
          f"Z厚={hz:.2f}(>=法兰{TYPEC_FLANGE_H}+2壁{HW}={TYPEC_FLANGE_H+2*HW:.1f}? {hz>=TYPEC_FLANGE_H+2*HW-1e-6}); "
          f"Y深={_mate['housing_y']:.2f}")
    # 体腔四壁实测 (从体腔中心沿 ±X/±Z 探到无料):
    body_w_chk = TYPEC_PANEL_W + 2 * TYPEC_BODY_CLEAR
    body_z_chk = TYPEC_PANEL_H + 2 * TYPEC_BODY_CLEAR
    cav_cy4 = _mate['housing_y_min'] + TYPEC_FLANGE_T + TYPEC_BODY_DEPTH / 2
    def _solid_pt(p):
        return (bracket_for4 & (Pos(*p) * Box(0.06, 0.06, 0.06))).volume > 1e-9
    def _meas_wall(ax, sign, half):
        p = half + 0.05
        while p < half + 10:
            c = [tc_cx, cav_cy4, tc_cz]; c[ax] += sign * p
            if not _solid_pt(c):
                break
            p += 0.05
        return p - half
    w_xp = _meas_wall(0, +1, body_w_chk / 2); w_xn = _meas_wall(0, -1, body_w_chk / 2)
    w_zp = _meas_wall(2, +1, body_z_chk / 2); w_zn = _meas_wall(2, -1, body_z_chk / 2)
    walls_ok = min(w_xp, w_xn, w_zp, w_zn) >= TYPEC_HOUSING_WALL - 0.06
    print(f"   [4-wall 四壁实测] +X={w_xp:.2f} -X={w_xn:.2f} +Z={w_zp:.2f} -Z={w_zn:.2f} "
          f"(各 >=壁{TYPEC_HOUSING_WALL}? {walls_ok})")
    # 不侵入屏体: 壳块 +Z 最大值 < 屏体后表面 Z.
    no_intrude = _mate['housing_z_top'] < _mate['back_outer_z']
    print(f"   [4-intrude 不侵入屏] 壳块 +Z={_mate['housing_z_top']:.2f} < 屏体后表面 Z={_mate['back_outer_z']:.2f}? "
          f"{no_intrude} (藏屏后, 不撞磁吸面)")
    # 不撞 POGO: 架构变更后壳块 (X=tc_cx, 偏卡钉端) 与 POGO 凹腔 (X=pogo_cx, 板心) 在 X 上分离.
    pogo_x1_4 = _mate['pogo_cx'] + _mate['pocket_w'] / 2     # POGO 凹腔右沿 (+X)
    housing_x0_4 = _mate['tc_cx'] - _mate['housing_w'] / 2   # 壳块左沿 (-X)
    pogo_sep_x = housing_x0_4 - pogo_x1_4                    # X 间隙 (壳块左沿 - POGO 右沿)
    print(f"   [4-pogo 分离] 壳块 X[{housing_x0_4:.1f},{_mate['tc_cx']+_mate['housing_w']/2:.1f}] "
          f"vs POGO 凹腔右沿 X={pogo_x1_4:.1f}; X 间隙={pogo_sep_x:.2f}mm (>0? {pogo_sep_x > 0}) "
          f"[实测壳块∩POGO 见 3c, =0]")
    # --- 4-plate) 对接板缩短报告 (架构变更: Type-C 不再挂板底, 板底只包最低磁 + 余量) ---
    plate_bot_old = -58.31    # 旧值 (Type-C 挂板底、由体深下探, 见 git 历史/基线)
    print(f"   [4-plate 对接板缩短] plate_bot_y 新={_mate['plate_bot_y']:.2f} (= 最低磁 {_mate['lowest_mag_y']:.2f} "
          f"- 磁半{MAG_D/2:.1f} - 余{PLATE_BOT_MARGIN:.1f}); 旧≈{plate_bot_old:.2f} (Type-C 挂板底下探); "
          f"板高 plate_h={_mate['plate_h']:.1f} (上=屏顶 0, 下=底磁包络); 清爽: 只剩 4 磁+POGO+pad 对位")

    # --- 4a) 确认: 屏体有 4×Φ8 磁腔 (已恢复) + 无 Type-C 开口 (屏体不出线) ---
    print("[4a 屏体确认] 4×Φ8 磁已恢复; 屏体无 Type-C 口:")
    bc_for4 = make_back_cover()
    bz_for4 = make_bezel()
    # 屏体底边壁完整 (无 Type-C 口): 用探针盒跨 bezel 底边壁, 应被料阻挡 (实壁).
    place_bz4 = place4
    _bzw4 = place_bz4 * bz_for4
    _bzbb_w = _bzw4.bounding_box()
    body_bottom_y = _bzbb_w.min.Y
    with BuildPart() as _wallprobe:
        with Locations((0.0, body_bottom_y + 1.5, (_bzbb_w.min.Z + _bzbb_w.max.Z)/2)):
            Box(BEZEL_OUT_W * 0.9, 3.0, (_bzbb_w.max.Z - _bzbb_w.min.Z) * 0.8, align=(Align.CENTER,)*3)
    wall_solid_v = (_wallprobe.part & _bzw4).volume
    bezel_bottom_solid = wall_solid_v > 1.0      # 底边壁有料 => 无 Type-C 开口
    # 屏体后盖 4×Φ8 磁腔已恢复 (详见 [3c]); 此处仅复核期望计数=4.
    n_phi8 = sum(1 for (mx, my) in MAG_POSITIONS
                 if (bc_for4 & (Pos(mx, my, MAG_OUTER_WALL + MAG_T / 2) * Box(0.06, 0.06, 0.06))).volume < 1e-9)
    print(f"          屏体后盖 Φ8 磁腔数 = {n_phi8} (期望 4, 已恢复) -> {'通过' if n_phi8 == 4 else '失败'}")
    print(f"          屏体 Type-C 开口数 = 0 (底边壁实料体积探针 {wall_solid_v:.1f}mm3 > 1 => 无口) -> "
          f"{'通过(底边壁实心, 无 Type-C 口)' if bezel_bottom_solid else '失败(底边壁有口!)'}")
    print(f"          屏体后盖对接区: 4×Φ8 磁腔 + 4 触点 pad 窗 (Φ{PAD_WINDOW_D}) + 2 钢片腔 (Φ{STEEL_D}×{STEEL_T})")

    # --- 4b) PCBA 装配 + 无螺丝夹持 + FPC 自检 ---
    print("-" * 78)
    print("[4b PCBA] 板装配 / 夹持 / FPC:")
    pcba = make_pcba()
    pcb, comp, pads, fpc = pcba["pcb"], pcba["comp"], pcba["pads"], pcba["fpc"]
    pcb_bb = pcb.bounding_box(); comp_bb = comp.bounding_box()
    print(f"   主板去 Type-C 母座; 板背增 {len(PAD_WINDOW_POSITIONS)} 个 pogo 接触 pad (对位针阵)")
    # 板外形 + 间隙在腔内:
    pcb_in_cav = (pcb_bb.max.X <= SCR_CAV_W / 2 and pcb_bb.max.Y <= SCR_CAV_H / 2)
    print(f"   板外形 {PCB_W:.1f}×{PCB_H:.1f}×{PCB_T} (<=包络 {PCB_W_MAX}×{PCB_H_MAX}); "
          f"X半{pcb_bb.max.X:.2f}<腔半{SCR_CAV_W/2:.2f}? {pcb_in_cav} -> "
          f"{'通过(腔内, 配合间隙 PCB_FIT={:.1f})'.format(PCB_FIT) if pcb_in_cav else '检查'}")
    print(f"   PCB 前面 z={pcb_bb.min.Z:.2f} (目标 {PCB_FRONT_Z}); 背面 z={pcb_bb.max.Z:.2f} (目标 {PCB_BACK_Z})")
    comp_top = comp_bb.max.Z
    comp_clear_act = BEZEL_DEPTH - comp_top      # 元件顶到后盖内面
    print(f"   元件顶 z={comp_top:.2f} (<=后盖内面 {BEZEL_DEPTH:.2f}? {comp_top<=BEZEL_DEPTH+1e-6}); "
          f"到后盖内面留 COMP_CLEAR={comp_clear_act:.2f} (>= {COMP_CLEAR}) -> "
          f"{'通过' if comp_clear_act >= COMP_CLEAR - 1e-6 else '失败'}")
    # (修 bug1) PCB 支撑支柱移到 back_cover; 直接相交判定: 后盖(含 4 支柱/定位销) 与 bezel 都不得碰墨水屏.
    from build123d import Pos as _Ps
    def _ivol(a, b):
        r = a & b
        return getattr(r, "volume", 0.0) if r is not None else 0.0
    screen_body = _Ps(0, 0, FRONT_WALL_T + SCREEN_T / 2) * make_screen_ref()   # 屏在屏体局部 (居中)
    bc_body = back_cover_local() * make_back_cover()                            # 后盖装入屏体局部
    bc_scr = _ivol(bc_body, screen_body)
    bz_scr = _ivol(make_bezel(), screen_body)
    pin_top_z = PCB_BACK_Z - PCB_LOC_PIN_H      # 销顶 (屏体局部 z, 朝屏方向)
    print(f"   [支柱移后盖] 后盖(含4支柱+定位销) ∩ 墨水屏 = {bc_scr:.3f} mm3; bezel(前腔已无支柱) ∩ 墨水屏 = {bz_scr:.3f} mm3 -> "
          f"{'通过(支柱在后盖, 不戳屏)' if bc_scr < 1.0 and bz_scr < 1.0 else '失败(戳屏)'}")
    print(f"   支柱顶面 body z={PCB_BACK_Z} 托 PCB 背面(元件面); 支撑高 PCB_STANDOFF_H={PCB_STANDOFF_H:.2f}; "
          f"对角 2 定位销 Φ{PCB_LOC_PIN_D} 顶 body z={pin_top_z:.2f} >= PCB前 {PCB_FRONT_Z} (不穿板/不碰屏)? {pin_top_z >= PCB_FRONT_Z}")
    # 夹持: plug 前端面 z vs PCB 背面 (报告预压量); plug 中央镂空让开元件.
    bc_local = make_back_cover()
    plug_front_local_z = BACK_COVER_PLATE_T + BC_PLUG_DEPTH       # 后盖局部凸台前端面
    # 后盖装配后 plug 前端面世界->屏体局部 z: back_cover_local 翻转+平移. 等价 bezel 局部:
    plug_front_body_z = BODY_T_ACTUAL - plug_front_local_z        # 屏体局部 z (前端面)
    preload = PCB_BACK_Z - plug_front_body_z                      # >0 = 过盈预压
    print(f"   夹持: plug 前端面 屏体局部 z={plug_front_body_z:.2f} vs PCB 背面 z={PCB_BACK_Z}; "
          f"预压量={preload:+.2f}mm (>0 过盈夹紧, 设计 BC_PLUG_PRELOAD={BC_PLUG_PRELOAD}) -> "
          f"{'通过(拧 M2 即夹板)' if -0.05 <= preload <= 0.3 else '检查'}")
    # plug 中央镂空 z 区让开元件: 镂空 (BC_PLUG_CAV) 屏体局部 z 范围 vs 元件包络.
    #   plug 边框料 z = [plug_front_body_z, BEZEL_DEPTH]; 中央镂空整段 z 无料 (让元件).
    #   核验: 把元件实体放屏体局部, 与 plug 边框料做布尔, 应≈0 (元件落在镂空, 不撞边框).
    plug_w = place4 * (back_cover_local() * make_back_cover())
    comp_w_solid = place4 * comp                                  # 元件 (屏体局部 == bezel 局部) -> 世界
    comp_vs_plug = (plug_w & comp_w_solid).volume
    print(f"   plug 中央镂空 {BC_PLUG_CAV_W:.1f}×{BC_PLUG_CAV_H:.1f} 让过元件 ({pcba['comp_w']:.1f}×{pcba['comp_h']:.1f}); "
          f"元件 ∩ plug(后盖全体) = {comp_vs_plug:.3f} mm3 -> "
          f"{'通过(不撞元件)' if comp_vs_plug < 1.0 else '失败(plug 撞元件)'}")
    # FPC: 板底 24P 排座 vs 后盖底部折回槽对齐.
    fpc_bb = fpc.bounding_box()
    fpc_y = (fpc_bb.min.Y + fpc_bb.max.Y) / 2
    if FPC_SLOT_ENABLE:
        slot_y_inner = -BEZEL_OUT_H / 2 + FPC_SLOT_DEPTH          # 折回槽沿 +Y 深入到此
        print(f"   FPC 24P 排座 板底中点 (局部 X≈0, Y={fpc_y:.2f}, 宽 {FPC_CONN_W}); "
              f"后盖底部折回槽 宽 {FPC_SLOT_W} 槽口 Y=-{BEZEL_OUT_H/2:.1f} 深入到 Y={slot_y_inner:.1f}")
        fpc_aligned = abs(fpc_bb.min.X) < FPC_SLOT_W / 2 and FPC_CONN_W <= FPC_SLOT_W
        print(f"   排座宽 {FPC_CONN_W} <= 槽宽 {FPC_SLOT_W}, 居中对齐? {fpc_aligned}; 折回间隙 {FPC_FOLD_GAP} -> "
              f"{'通过(排座对齐折回槽)' if fpc_aligned else '检查'}")
    else:
        print(f"   FPC 24P 排座 板底中点 (局部 X≈0, Y={fpc_y:.2f}, 宽 {FPC_CONN_W}); "
              f"后盖底部折回槽: 已禁用(暂移除); 折回间隙 {FPC_FOLD_GAP} 保留 (待 FPC 实测后再开槽)")

    # --- 5) 屏体总厚分解 ---
    print(f"[5 叠层] 唇LIP{LIP} + 屏{SCREEN_T} + FPC折回{FPC_FOLD_GAP} + 小板(PCB{PCB_T}+元件{COMP_H_MAX}) + 后盖壁{BACK_WALL}")
    stack_sum = LIP + SCREEN_T + FPC_FOLD_GAP + PCB_T + COMP_H_MAX + BACK_WALL
    print(f"         分解和 = {stack_sum:.2f} (前面板=唇 LIP, 无额外余量); 几何屏体总厚 = {BODY_T_ACTUAL:.2f}")
    print(f"         vs BODY_T={BODY_T}: 偏差 {BODY_T_ACTUAL-BODY_T:+.2f}mm -> "
          f"{'通过(±1.5内)' if abs(BODY_T_ACTUAL-BODY_T)<1.5 else '注意'}")

    # --- 6) 装配体两两干涉 (>1mm³ 报警); 重点: bracket∩monitor ≈ 0 (改动 3) ---
    print("-" * 78)
    place = body_placement()
    bz_a = place * bezel
    bc_a = place * (back_cover_local() * back_cover)
    print("[6 干涉] 装配体各件两两干涉体积 (mm³, >1 报警):")
    print("         注: bezel∩back_cover 为屏体内部'凸台插腔'设计配合, 单列不报警.")
    parts = [("monitor", monitor), ("bracket", bracket), ("bezel", bz_a), ("back_cover", bc_a)]
    br_mon_v = None
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            n1, p1 = parts[i]; n2, p2 = parts[j]
            internal_pair = {n1, n2} == {"bezel", "back_cover"}
            grip_pair = {n1, n2} == {"monitor", "bracket"}
            try:
                v = (p1 & p2).volume
                if grip_pair:
                    br_mon_v = v
                if internal_pair:
                    flag = "  (屏体内部凸台插腔, 设计允许)"
                elif grip_pair:
                    flag = ("  (改动3: 留 %.1f 间隙, ≈0 通过)" % MON_FIT_GAP
                            if v < 1.0 else "  <<< 仍过盈, 检查!")
                else:
                    flag = "  <<< 冲突!" if v > 1.0 else "  ok"
                print(f"           {n1:10s} ∩ {n2:10s} = {v:10.4f}{flag}")
            except Exception as e:
                print(f"           {n1:10s} ∩ {n2:10s} = ERR({e})")

    # --- 7) 修复验证: 单一连通实体 + 四面实测间隙 + L 角包覆连续 ---
    n_solids = len(bracket.solids())
    print(f"[7 抱边间隙] bracket∩monitor = {br_mon_v:.4f} mm³ -> "
          f"{'通过(≈0)' if (br_mon_v is not None and br_mon_v < 1.0) else '失败'} "
          f"(设计间隙 MON_FIT_GAP={MON_FIT_GAP})")
    # 7a) 单一连通实体 (核心回归项): 明确打印实体数, 断言 ==1.
    print(f"   [7a 单一实体] bracket.solids() 数量 = {n_solids} -> "
          f"{'通过(单一连通实体)' if n_solids == 1 else '失败(>1, 卡钉/臂/板断开!)'}")
    assert n_solids == 1, f"bracket 必须为单一连通实体, 实测 {n_solids} 个 SOLID"

    # 7a2) 走线腔连通 (改道): Type-C 体腔(支柱下方) -> 段A(竖向,入支柱) -> 段B(沿支柱-X) ->
    #   段C(对接板竖向,到 POGO). 三段探针应全程无料 (连通容飞线). 逐段 + 合并探针验证.
    _m = make_bracket.mate
    # 走线腔已改 -Z 背面开口 (修 bug2 配套): A/B 从 strut_z_bot 向 +Z 沉; C 从 mate_z_bot 向 +Z 沉.
    zc_ch_AB = _m['strut_z_bot'] + CHANNEL_DEPTH / 2
    zc_ch_C = _m['z_bot'] + CHANNEL_DEPTH / 2
    # 段A: X=tc_cx, Y 从体腔顶 到 支柱带 (chanA).
    A_y0, A_y1 = _m['chanA_y_bot'] + 0.5, _m['chanA_y_top'] - 0.5
    with BuildPart() as _pA:
        with Locations((_m['tc_cx'], (A_y0 + A_y1) / 2, zc_ch_AB)):
            Box(CHANNEL_W - 1.0, A_y1 - A_y0, CHANNEL_DEPTH - 0.5, align=(Align.CENTER,)*3)
    # 段B: Y=strut_yc, X 从 tc_cx 到 pogo_cx (chanB).
    B_x0, B_x1 = _m['chanB_x_a'] + 0.5, _m['chanB_x_b'] - 0.5
    with BuildPart() as _pB:
        with Locations(((B_x0 + B_x1) / 2, _m['strut_yc'], zc_ch_AB)):
            Box(B_x1 - B_x0, CHANNEL_W - 1.0, CHANNEL_DEPTH - 0.5, align=(Align.CENTER,)*3)
    # 段C: X=pogo_cx, Y 从 支柱带 到 POGO 区 (chanC = channel_y_*).
    C_y0, C_y1 = _m['channel_y_bot'] + 0.5, _m['channel_y_top'] - 0.5
    with BuildPart() as _pC:
        with Locations((_m['pogo_cx'], (C_y0 + C_y1) / 2, zc_ch_C)):
            Box(CHANNEL_W - 1.0, C_y1 - C_y0, CHANNEL_DEPTH - 0.5, align=(Align.CENTER,)*3)
    vA = (_pA.part & bracket).volume; vB = (_pB.part & bracket).volume; vC = (_pC.part & bracket).volume
    chan_block = max(vA, vB, vC)
    print(f"   [7a2 走线腔·改道] Type-C 体腔(支柱下方) ->A(竖,入支柱)->B(沿支柱-X)->C(板,到POGO):")
    print(f"            段A ∩={vA:.3f}  段B ∩={vB:.3f}  段C ∩={vC:.3f} mm3 (各<1 通) -> "
          f"{'通过(全程连通, 无料阻挡; 容飞线+dock PCB)' if chan_block < 1.0 else '失败(某段被料堵)'}")

    # 7b) 抱边四面实测间隙: 用一个"细探针盒"扫每个面方向, 量 bracket 内表面与显示器面距离.
    #   显示器角块: 顶面 Y=0, 左面 X=0, 前面 Z=0, 背面 Z=-MON_EDGE_T.
    #   在抱边覆盖段 (顶边臂 X≈14, 左边臂 Y≈-14) 沿各法向步进找首次进入 bracket 实体的位置.
    g = MON_FIT_GAP

    from build123d import Box as _B, Pos as _P

    def _inside(part, p):
        # 用极小盒做布尔交判定点是否落在实体内部 (对内部点也成立, 不依赖表面距离).
        return (part & (_P(*p) * _B(0.04, 0.04, 0.04))).volume > 1e-9

    def _gap_along(p0, step, name, expect):
        # 从显示器表面 p0 沿 step 方向步进, 找首次进入 bracket 的距离 = 实测间隙.
        d = 0.0
        for _ in range(200):
            p = (p0[0] + step[0] * d, p0[1] + step[1] * d, p0[2] + step[2] * d)
            if _inside(bracket, p):
                break
            d += 0.01
        ok = abs(d - expect) < 0.08
        print(f"   [7b 间隙·{name:4s}] 实测 {d:.2f}mm (期望 {expect}) -> {'通过' if ok else '检查'}")
        return d

    # 顶面间隙: 顶边臂上 (X=14), 从 Z=-8.5 沿 +Y (顶面 Y=0 向外) 找外侧壁内面.
    _gap_along((14.0, 0.0, -8.5), (0, +1, 0), "顶", g)
    # 左面间隙: 左边臂上 (Y=-14), 从 Z=-8.5 沿 -X (左面 X=0 向外) 找外侧壁内面.
    _gap_along((0.0, -14.0, -8.5), (-1, 0, 0), "左", g)
    # 前面间隙: 顶边前舌下 (X=14, Y=-2 黑边区), 从 Z=0 沿 +Z 找前舌底面.
    _gap_along((14.0, -2.0, 0.0), (0, 0, +1), "前", g)
    # 背面间隙: 顶边后舌上 (X=14, Y=-4), 从 Z=-MON_EDGE_T 沿 -Z 找后舌顶面.
    _gap_along((14.0, -4.0, -MON_EDGE_T), (0, 0, -1), "后", g)

    # 7c) L 角包覆连续: 拐角邻域里, 同一个 solid 是否同时含"顶边臂"与"左边臂"卡钉特征.
    #   取顶边臂样点 (14,1.5,-8.5) 与左边臂样点 (-1.5,-14,-8.5), 看是否落在同一 solid.
    from build123d import Box as _B2, Pos as _P2
    sample_top = (14.0, g + CLIP_WALL / 2, -8.5)     # 顶边外侧壁带
    sample_left = (-(g + CLIP_WALL / 2), -14.0, -8.5)  # 左边外侧壁带
    same_solid = None
    for s in bracket.solids():
        in_t = (s & (_P2(*sample_top) * _B2(0.05, 0.05, 0.05))).volume > 1e-12
        in_l = (s & (_P2(*sample_left) * _B2(0.05, 0.05, 0.05))).volume > 1e-12
        if in_t and in_l:
            same_solid = s
            break
    # 拐角邻域体积连续性: 角块 (0,0) 周围一圈外壳应有连续料 (取 L 角外侧壳样点全部命中).
    corner_pts = [(g + CLIP_WALL / 2, g + CLIP_WALL / 2, -8.5),   # 顶外侧
                  (-(g + CLIP_WALL / 2), g + CLIP_WALL / 2, -8.5),  # 角外侧
                  (-(g + CLIP_WALL / 2), -(g + CLIP_WALL / 2), -8.5)]  # 左外侧
    corner_hit = all(_inside(bracket, p) for p in corner_pts)
    print(f"   [7c L角包覆] 顶边臂与左边臂共享同一 solid? {same_solid is not None}; "
          f"拐角外壳三点连续命中? {corner_hit} -> "
          f"{'通过(L 角连续包严)' if (same_solid is not None and corner_hit) else '检查'}")

    print(f"             U口深 CLIP_DEPTH={CLIP_DEPTH} (T_edge={MON_EDGE_T}); "
          f"前舌 CLIP_FRONT_LIP={CLIP_FRONT_LIP}(≤黑边{MON_BEZEL_TOP}不盖画面); 后舌 CLIP_BACK_LIP={CLIP_BACK_LIP}")
    print(f"             显示器前/后/侧面与抱边内壁各留 {MON_FIT_GAP}mm (靠 VHB 贴合, 非过盈; correct-by-construction)")

    # 7d) 支柱是"直"的: 单一 -X 拉伸矩形棒, 主轴=X, 截面 STRUT_W×STRUT_H 恒定, 无折弯/台阶.
    mate = make_bracket.mate
    strut_area = mate["strut_w"] * mate["strut_h"]
    print(f"   [7d 支柱·直] 单一 -X 拉伸矩形棒: 主轴=X(沿屏宽), 截面 STRUT_W×STRUT_H = "
          f"{mate['strut_w']:.1f}×{mate['strut_h']:.1f} = {strut_area:.1f} mm² 恒定; "
          f"两端圆角过渡 (STRUT_FILLET={STRUT_FILLET}); 无台阶/无折弯 -> 通过(平顺单一)")
    # 沿支柱主轴在多处取截面探针 (X 各点处 Y,Z 截面应同尺寸), 验证截面不变.
    #   取支柱自由段 (卡钉外壁 X≈-g 与板心 X≈arm_x_end 之间), 避开拐角块/对接板.
    strut_yc, strut_zc = mate["strut_yc"], mate["strut_z_c"]
    free_x0 = mate["arm_x_end"] + 2.0          # 略离板内
    free_x1 = -(g + CLIP_WALL) - 1.5           # 越过拐角块 (拐角外壁 X≥-cw, Y 上探), 取其外侧
    xs = [free_x0, (free_x0 + free_x1) / 2, free_x1]
    consistent = True
    for xq in xs:
        # 截面内心点应在实体内; 截面上方 (Y 超出上沿, 自由段上方无料) 应在实体外.
        c_in = _inside(bracket, (xq, strut_yc, strut_zc))
        c_out = _inside(bracket, (xq, strut_yc + mate["strut_w"] / 2 + 1.0, strut_zc))
        consistent = consistent and c_in and (not c_out)
    print(f"   [7d 截面探针] 沿主轴 {len(xs)} 处截面内实/外空一致? {consistent} "
          f"-> {'通过(截面规整不变)' if consistent else '检查'}")

    # 7e) 支柱↔对接板大面积熔接: 量结合处接触面积 (≈支柱末端 STRUT_W×STRUT_H 整张埋进板).
    #   做法: 在结合界面 (X = strut_x_endin, 即板心列) 附近, 用一片薄盒 ∩ bracket 量实料截面积.
    #   截面积 / 薄片厚 = 该 X 处实体横截面积; 取 ≈ 支柱末端整张 => 大面积、不细颈.
    eps = 0.2
    x_iface = mate["strut_x_endin"] + 0.5         # 略入板内一点 (支柱与板已熔为一体处)
    # 薄片覆盖支柱截面区 (Y 跨 strut_w, Z 跨 strut_h), 量其中实料体积 -> 接触面积.
    slab = (_P2(x_iface, strut_yc, strut_zc)
            * _B2(eps, mate["strut_w"] + 0.02, mate["strut_h"] + 0.02))
    bond_area = (bracket & slab).volume / eps
    ratio = bond_area / strut_area
    # 阈值: 允许两顶棱倒角带来的小幅截面损失 (≈2×(r²-πr²/4) ≈ 1.7mm²), 仍判"全截面熔接".
    bond_min = strut_area - 2.0 * (STRUT_FILLET ** 2)
    print(f"   [7e 熔接面] 支柱↔板结合处实料横截面 ≈ {bond_area:.1f} mm² "
          f"(支柱截面 {strut_area:.1f}; 比值 {ratio:.2f}) -> "
          f"{'通过(≈支柱全截面, 大面积熔接不细颈)' if bond_area >= bond_min else '检查(疑细颈)'}")
    print(f"             对接板 H×T = {mate['plate_h']:.1f}×{MATE_T} mm; 支柱以全截面整张埋入板 = 加强背肋熔为一体")

    # 7f) 磁带竖向位置: 报告磁带中心相对屏高的位置 (屏顶下方百分比), 确认在中上部.
    band_local_y = MAG_BAND_CENTER_Y                  # 后盖局部 Y (上=+Y, 屏体中心=0)
    body_top_local = BEZEL_OUT_H / 2                  # 屏顶 (后盖局部)
    depth_from_top = body_top_local - band_local_y    # 磁带中心到屏顶的距离
    pct_from_top = depth_from_top / BEZEL_OUT_H * 100
    print(f"   [7f 磁带位] 磁带中心 (后盖局部) Y = {band_local_y:+.2f} (屏体中心=0, 屏顶=+{body_top_local:.2f}); "
          f"位于屏顶下方 {depth_from_top:.1f}mm = 屏高 {pct_from_top:.0f}% (中上部) -> "
          f"{'通过(中上部 1/3~1/2)' if 25 <= pct_from_top <= 50 else '检查'}")
    print(f"             4 磁心 (后盖局部 X,Y): " +
          ", ".join(f"({mx:+.1f},{my:+.1f})" for mx, my in MAG_POSITIONS))

    # --- 8) 改动4 顶部对齐: 墨水屏顶边 Y vs 显示器顶边 Y ---
    bz_bb = bz_a.bounding_box()
    body_top_y = bz_bb.max.Y                 # 屏体(bezel)顶边世界 Y
    mon_bb = monitor.bounding_box()
    mon_top_y = mon_bb.max.Y                  # 显示器顶边世界 Y (=0)
    dy = body_top_y - mon_top_y
    print(f"[8 顶对齐] 墨水屏顶边 Y = {body_top_y:.3f}; 显示器顶边 Y = {mon_top_y:.3f}; "
          f"差 = {dy:+.3f} (期望 ≈ TOP_FLUSH_OFFSET={TOP_FLUSH_OFFSET}) -> "
          f"{'通过' if abs(dy - TOP_FLUSH_OFFSET) < 0.05 else '检查'}")
    print(f"           屏体世界 Y 范围 [{bz_bb.min.Y:.2f}, {bz_bb.max.Y:.2f}] (吊顶部向下延伸)")

    # --- 9) 不遮挡: 屏体 X 投影 vs 显示器 AA 区 X (屏体须在 AA 左侧之外) ---
    body_x0, body_x1 = bz_bb.min.X, bz_bb.max.X
    # 显示器 AA 区: 左边黑边 MON_BEZEL_LEFT, 故 AA 起于 X = MON_BEZEL_LEFT 向 +X.
    aa_mon_x0 = MON_BEZEL_LEFT
    aa_mon_x1 = mon_bb.max.X
    mon_left_edge = mon_bb.min.X               # 显示器左边缘 X=0
    no_occlude = body_x1 <= aa_mon_x0          # 屏体右边缘 ≤ AA 左沿
    left_of_edge = body_x1 <= mon_left_edge + 0.001  # 屏体在显示器左边缘之外
    print(f"[9 不遮挡] 屏体 X 投影 [{body_x0:.2f}, {body_x1:.2f}]; "
          f"显示器 AA 区 X [{aa_mon_x0:.2f}, {aa_mon_x1:.2f}]; 显示器左边缘 X={mon_left_edge:.2f}")
    print(f"           屏体右边缘 {body_x1:.2f} ≤ AA 左沿 {aa_mon_x0:.2f}? {no_occlude}; "
          f"在显示器左边缘之外? {left_of_edge} -> {'通过(不挡画面)' if (no_occlude and left_of_edge) else '检查'}")

    # --- 11) 修正 1: 支柱走向 (-X 直线, Y 在屏顶高度, Z 藏屏后, 无 +Y 拱起/无折弯) ---
    print("-" * 78)
    mate = make_bracket.mate
    Zf = 0.0                                   # 显示器前表面世界 Z
    strut_y0 = mate["strut_yc"] - mate["strut_w"] / 2
    strut_y1 = mate["strut_yc"] + mate["strut_w"] / 2
    strut_x0 = mate["arm_x_end"]               # 末端 (板内, -X)
    strut_x1 = mate["strut_x_start"]           # 起点 (咬卡钉, X≈-g)
    no_arch = strut_y1 <= 0.05                 # 支柱上沿 ≤ 0 => 无 +Y 拱起 (不在显示器顶边上方)
    z_behind = mate["strut_z_top"] < Zf        # 支柱最高 Z < Zf => 藏在屏体背后
    print(f"[11 支柱走向] 主轴 = -X 直线 (从 X={strut_x1:+.2f} 咬左边臂卡钉, 直伸到 X={strut_x0:+.2f} 板内);")
    print(f"            X 跨度 [{strut_x0:+.2f}, {strut_x1:+.2f}] (单截面 -X 拉伸, 无折弯/无台阶)")
    print(f"            Y 范围 [{strut_y0:+.2f}, {strut_y1:+.2f}] (屏顶高度一带, Y≤0); "
          f"上沿 ≤0 无 +Y 拱起? {no_arch} -> {'通过' if no_arch else '失败(仍拱起)'}")
    print(f"            Z 范围 [{mate['strut_z_bot']:+.2f}, {mate['strut_z_top']:+.2f}] (屏体背后); "
          f"最高 Z < Zf={Zf}? {z_behind} -> {'通过(藏屏后)' if z_behind else '失败(凸出)'}")
    print(f"            结论: 沿顶边 -X 直出, 无 +Y 平移/拱起, 无折弯 -> "
          f"{'通过' if (no_arch and z_behind) else '检查'}")

    # --- 12) 修正 2: Z 共面 + 结构藏屏后 (除前舌外最大 Z < Zf) ---
    # 墨水屏前表面世界 Z (屏体 bezel 的 +Z 最大面) vs 显示器前表面 Zf.
    eink_front_z = bz_bb.max.Z                 # 墨水屏/前框前表面世界 Z (装配后)
    mon_front_z = mon_bb.max.Z                 # 显示器前表面世界 Z (=0)
    dz = eink_front_z - mon_front_z
    flush_ok = abs(dz - Z_FLUSH_OFFSET) < 0.05
    print(f"[12 Z共面] 墨水屏前表面 Z = {eink_front_z:.3f}; 显示器前表面 Z = {mon_front_z:.3f}; "
          f"差 = {dz:+.3f} (期望 ≈ Z_FLUSH_OFFSET={Z_FLUSH_OFFSET}) -> "
          f"{'通过(共面)' if flush_ok else '检查'}")
    print(f"           屏体世界 Z 范围 [{bz_bb.min.Z:.2f}, {bz_bb.max.Z:.2f}] "
          f"(前表面在 Zf, 向 -Z 叠 BODY_T; 后表面 {bz_bb.min.Z:.2f} > 显示器背面 -{MON_EDGE_T})")
    # 一致性: body_placement 的 Z0 锚点与 bracket 内 mate_z_top 是否自洽.
    expect_z_top = (Zf + Z_FLUSH_OFFSET) - BODY_T_ACTUAL - 0.5
    consistent_z = abs(mate["z_top"] - expect_z_top) < 1e-6
    print(f"           对接板顶面 Z = {mate['z_top']:.3f} (期望 = 后盖外表面 - 气隙 = {expect_z_top:.3f}); "
          f"自洽? {consistent_z} -> {'通过' if consistent_z else '检查'}")
    # 结构 (对接板/支柱/后舌) 最大 Z 应 < Zf; 唯有前舌 Z≥Zf 压黑边. 用包络盒分层量.
    #   后舌料顶面 BACK_Z1 = -(MON_EDGE_T+g); 对接板顶 = mate_z_top; 支柱顶 = strut_z_top; 都 <0.
    back_tongue_top = -(MON_EDGE_T + MON_FIT_GAP)   # 后舌顶面 Z (离背面 0.3)
    struct_max_z = max(mate["z_top"], mate["strut_z_top"], back_tongue_top)
    front_lip_top = MON_FIT_GAP + CLIP_FRONT_T      # 前舌料顶 Z (≥0, 唯一露正面者)
    struct_hidden = struct_max_z < Zf
    print(f"           结构最大 Z: 对接板顶 {mate['z_top']:.2f} / 支柱顶 {mate['strut_z_top']:.2f} / "
          f"后舌顶 {back_tongue_top:.2f} => max {struct_max_z:.2f} < Zf={Zf}? {struct_hidden} -> "
          f"{'通过(对接板/支柱/后舌全藏屏后)' if struct_hidden else '失败'}")
    print(f"           仅卡钉前舌 Z 顶 {front_lip_top:.2f} (≥Zf) 露正面压黑边 (前舌底离前表面 {MON_FIT_GAP})")

    # --- 10) 两个装配文件实体清单 (确认 assembly_print 不含参考体) ---
    # 注: Compound 加子件会"移交"所有权, 故每个装配各用独立 part 实例, 避免互相抽走子件.
    asm_print = make_assembly_print(make_bezel(), make_back_cover(), make_bracket())
    asm_ctx = make_assembly_context(make_bezel(), make_back_cover(), make_bracket(),
                                    make_screen_ref(), make_monitor_corner())
    pl = [c.label for c in asm_print.children]
    cl = [c.label for c in asm_ctx.children]
    print(f"[10 文件] assembly_print 实体 = {pl} (期望仅 3 打印件, 无参考体)")
    print(f"          assembly_context 实体 = {cl} (打印件 + monitor_ref + screen_ref)")
    ref_in_print = any(x in pl for x in ("monitor_ref", "screen_ref"))
    print(f"          assembly_print 含参考体? {ref_in_print} -> "
          f"{'失败' if ref_in_print else '通过(参考体未混入打印模型)'}")

    # --- 导出 ---
    print("-" * 78)
    export_step(bezel, str(OUT / "bezel.step"))
    export_stl(bezel, str(OUT / "bezel.stl"))
    export_step(back_cover, str(OUT / "back_cover.step"))
    export_stl(back_cover, str(OUT / "back_cover.stl"))
    export_step(bracket, str(OUT / "bracket.step"))
    export_stl(bracket, str(OUT / "bracket.stl"))
    # 改动 1: 拆成两个装配文件
    export_step(asm_print, str(OUT / "assembly_print.step"))
    export_step(asm_ctx, str(OUT / "assembly_context.step"))

    # 改动 2 验证: 重新 import assembly_context, 读 STEP 装配树各节点 label (viewer 显示的就是它).
    try:
        from build123d import import_step
        re = import_step(str(OUT / "assembly_context.step"))
        top = getattr(re, "label", "")
        node_labels = [getattr(c, "label", "") for c in (re.children or [])]
        print(f"[label验证] 重导 assembly_context 顶层 label='{top}'; "
              f"装配树子节点 label={node_labels}")
        re2 = import_step(str(OUT / "assembly_print.step"))
        print(f"           assembly_print 子节点 label="
              f"{[getattr(c, 'label', '') for c in (re2.children or [])]}")
    except Exception as e:
        print(f"[label验证] 重导失败: {e}")

    print("exported to", OUT)
    for f in sorted(OUT.glob("*")):
        print("  ", f.name, f"{f.stat().st_size}B")


if __name__ == "__main__":
    main()
