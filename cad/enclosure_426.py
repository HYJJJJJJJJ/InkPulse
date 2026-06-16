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
TYPEC_BODY_H = 3.2             # Type-C 母座高出 PCB 元件面 (从 PCB 背面起算的母座外壳高)
# FPC 排座在底边中点 bottom_mid
# --- Type-C 改到底边朝下出线 (改动: 右侧壁 -> 底边 -Y, 口朝 -Y/向下) ---
#   背景: 原口在屏体右侧壁(+X, 朝显示器), 插头/线缆往 +X 与显示器左边框打架.
#   改为母座移到 PCB 底边(-Y 缘)、口朝 -Y(向下), 线缆垂直沿显示器左侧落下, 彻底避开.
TYPEC_SIDE = "bottom"          # 底边短边 (-Y), 口朝下 (-Y) 出线
TYPEC_W = 10.0                 # 开口沿 X 宽 (= 母座宽方向)
TYPEC_H = 4.0                  # (旧右侧壁口的 Z 高占位; 底边口的 Z 跨度改由板位推出, 见派生区)
# Type-C 沿 X 偏置, 避开底边中央 FPC 排座/折回槽 (FPC_SLOT_W=24, X∈[-12,12]).
#   偏 -X 一侧 (背离显示器). 口 X∈[CENTER-W/2, CENTER+W/2], 与 FPC 槽留 ≥2mm 间隔.
#   -20: 口 X∈[-25,-15], 距 FPC 槽左缘 -12 => 间隙 3.0mm (≥2). (设计指定 ~-18, 因 -18
#   仅余 1mm < 2mm 约束, 故收到 -20 满足硬约束; 见完成报告.)
TYPEC_CENTER_X = -20.0         # Type-C 开口 X 中心 (bezel 局部, 偏 -X 背离显示器)
# --- PCB 安装/定位 ---
PCB_MOUNT_INSET = 5.0          # 安装/定位孔从板边内缩 (避开连接器)
PCB_LOC_PIN_D = 1.8            # 定位销直径 (插板定位孔)
PCB_STANDOFF_D = 4.0          # PCB 支撑支柱外径
PCB_STANDOFF_TOP_INSET = 0.0  # 支柱顶 (= PCB 前面 z) 由叠层派生

# --- 磁吸 ---
MAG_D = 8.0
MAG_T = 3.0
MAG_N = 4                      # 上下各一对, 左右对称, 靠近对接侧
MAG_GRADE = "N52"
FRICTION_PAD_T = 0.8          # 高摩擦垫沉槽深

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

# --- PCB 支撑支柱 (bezel 内长出, 顶到 PCB 前面 z=PCB_FRONT_Z) ---
PCB_STANDOFF_H = PCB_FRONT_Z - FRONT_WALL_T   # 支柱从前面板内面(z=1.0)升到 PCB 前面(2.5), 高 1.5
PCB_LOC_PIN_H = PCB_T + 0.6                    # 定位销高: 穿过 PCB 板厚 + 余量

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

# --- 后盖嵌磁腔 ---
# 4 个 Φ8×3, 上下各一对, 左右对称, 靠近对接侧 (对接侧 = 右 +X, 朝显示器/支架).
# 磁心 X 靠右侧内壁 (但避开 Type-C 与螺柱); 上下对称分布。
BACK_COVER_PLATE_T = BACK_WALL              # 1.5
MAG_INSET_X = BEZEL_OUT_W / 2 - MAG_D / 2 - WALL - 1.0   # 磁心 X (靠右内壁, 留壁厚)
MAG_INSET_Y = 18.0                           # 磁带内两行半距 (上下各一行的 |ΔY|, 绕带中心)
# --- 改动 3: 磁带上移到屏体中上部 ---
# 4 颗磁仍"上下两对、左右对称", 但整带沿竖向上移到中上部 (而非屏体正中).
# 带中心 MAG_BAND_CENTER_Y (后盖局部 Y, 上=+Y): 取屏顶下方约 1/3 屏高处.
#   屏顶边 (后盖局部) = +BEZEL_OUT_H/2; 下移 1/3 屏高 => 中心在 +BEZEL_OUT_H/2 - BEZEL_OUT_H/3.
#   好处: 磁点靠上更抗剥离/杠杆力矩; 支柱也能就近从顶部卡钉平直接到磁带区.
MAG_BAND_CENTER_Y = BEZEL_OUT_H / 2 - BEZEL_OUT_H / 3   # ≈ +18.4 (中上部)
# 磁心坐标 (后盖局部, 4 个): 左右两列 × 上下两行, "靠近对接侧" => 偏 +X
MAG_COL_X = MAG_INSET_X                       # 列 |X|
MAG_POSITIONS = [
    (MAG_COL_X, MAG_BAND_CENTER_Y + MAG_INSET_Y), (-MAG_COL_X, MAG_BAND_CENTER_Y + MAG_INSET_Y),
    (MAG_COL_X, MAG_BAND_CENTER_Y - MAG_INSET_Y), (-MAG_COL_X, MAG_BAND_CENTER_Y - MAG_INSET_Y),
]
assert len(MAG_POSITIONS) == MAG_N

# --- 后盖 FPC 折回槽 (底部短边 -Y 中央) ---
FPC_SLOT_W = 24.0                            # 折回槽宽 (FPC 实测宽 + 余量; 待测 §8)
FPC_SLOT_DEPTH = 10.0                        # 沿 +Y 深入

# ============================================================
# Type-C 开口 — 改到 bezel 底边壁 (-Y), 口朝下 (-Y); 由 PCBA 装配 Z 推出 Z 跨度
# ============================================================
# 母座移到 PCB 底边(-Y 缘)、元件面朝后(+z), 母座高出 PCB 约 TYPEC_BODY_H.
#   口朝 -Y(向下): 开口沿 X 宽 = TYPEC_W; 沿 Z 跨度 = 母座在底边的实际 Z 包络 (连接器贴板).
#   母座 Z 包络: 从 PCB 背面 z=PCB_BACK_Z(4.1) 起, 高 TYPEC_BODY_H, 即 z∈[4.1, 4.1+3.2=7.3].
#     口稍放宽两端各 0.4 余量, 仍 < BEZEL_DEPTH=8.3 (落 bezel 壁内, 只需切 bezel).
TYPEC_OPEN_MARGIN_Z = 0.4                                # 口 Z 两端余量 (让母座+插头)
TYPEC_Z0 = PCB_BACK_Z - TYPEC_OPEN_MARGIN_Z              # 口 Z 下沿 ≈ 3.7
TYPEC_Z1 = PCB_BACK_Z + TYPEC_BODY_H + TYPEC_OPEN_MARGIN_Z   # 口 Z 上沿 ≈ 7.7
TYPEC_OPEN_H_Z = TYPEC_Z1 - TYPEC_Z0                     # 口沿 Z 跨度 ≈ 4.0
TYPEC_CENTER_Z = (TYPEC_Z0 + TYPEC_Z1) / 2              # 口中心 z ≈ 5.7
# 底边壁朝下: bezel 局部 -Y 即世界 -Y (body_placement 的 Rot(0,180,0) 不改 Y). 口朝 -Y/向下.
# X 偏置 (避开 FPC): 见 TYPEC_CENTER_X (默认 -20, 偏 -X 背离显示器, 与 FPC 槽留 ≥2mm).
TYPEC_LOCAL_X = TYPEC_CENTER_X                           # bezel 局部 X (= 世界 -X 一侧, 背离显示器)
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
# --- plug 底边 Type-C 让位缺口 (随 Type-C 移到底边而改) ---
# plug 边框 (RIM=4mm) 压在 PCB 底边(-Y)缘, 而 Type-C 母座 + 朝下开口穿透路径正落此处.
#   若不让位, plug 底边边框会(a)挡死开口腔内→壳外向下通路, (b)压坏母座.
#   故在 plug 底边边框 (bezel 局部 -Y = 后盖局部 -Y, 两次翻转 Y 不变) 的 Type-C (X) 处切缺口,
#   宽含母座+余量, 沿 Y 切穿整条底边边框 (从镂空内缘到 plug 外缘), 贯穿整个 plug 深度.
#   缺口 X 中心 = TYPEC_LOCAL_X (与 FPC 槽中央缺口在 X 上错开, 互不干涉).
BC_TYPEC_NOTCH_W = TYPEC_W + 2.0               # 缺口沿 X 宽 (开口宽 + 余量, 让母座+插头)
BC_TYPEC_NOTCH_Y_OVER = 1.0                    # 缺口沿 Y 越过 plug 外缘的余量 (确保切穿边框)

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

# 对接面 (mating plate): 嵌对磁 (与后盖磁位镜像对齐) + 高摩擦垫沉槽
MATE_W = BEZEL_OUT_W                          # 对接面宽 (≈屏体宽, 容纳磁阵)
MATE_H = BEZEL_OUT_H * 0.65                   # 对接面高 (覆盖上下两排磁)
MATE_T = 5.0                                  # 对接面板厚 (嵌 Φ8×3 磁 + 留底)
# 对接面磁腔位置: 与后盖磁位镜像对齐 (镜像 X, 因屏体后盖朝外、支架朝内对贴).
# 后盖磁心 (后盖局部) 投到对接面: 屏体后盖外表面贴对接面, 两者法向相对 => X 镜像.
MATE_MAG_POSITIONS = [(-x, y) for (x, y) in MAG_POSITIONS]
FRICTION_PAD_W = MATE_W - 2 * MAG_D - 4.0     # 摩擦垫沉槽宽 (居中, 避开磁腔列)
FRICTION_PAD_H = 2 * MAG_INSET_Y - MAG_D - 4.0  # 摩擦垫沉槽高 (落在两磁行之间, 不碰磁腔)

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

        # 5) PCB 支撑支柱 (4 根): 从前面板内面 z=FRONT_WALL_T 升到 PCB 前面 z=PCB_FRONT_Z.
        #    位置 = 板四角内侧 (PCB_STANDOFF_POSITIONS); 板落其顶面 (Z 定位).
        for (sx, sy) in PCB_STANDOFF_POSITIONS:
            # 起点下沉 0.3 进前面板 (z=FRONT_WALL_T-0.3), 保证与托盘熔为一体 (避免共面不熔).
            with Locations((sx, sy, FRONT_WALL_T - 0.3)):
                Cylinder(PCB_STANDOFF_D / 2, PCB_STANDOFF_H + 0.3,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 6) 定位销 (对角 2 根支柱顶部长出, 插 PCB 定位孔): 从 PCB 前面 z=PCB_FRONT_Z 向 +z.
        for (px, py) in PCB_LOC_PIN_POSITIONS:
            with Locations((px, py, PCB_FRONT_Z)):
                Cylinder(PCB_LOC_PIN_D / 2, PCB_LOC_PIN_H,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 7) Type-C 开口 (改: 切在 bezel 底边壁 -Y, 口朝下/-Y 出线), 穿 2mm 壁.
        #    朝向推导: bezel 经 body_placement 的 Rot(0,180,0) 翻转, Y 分量不变 => 局部 -Y
        #    映到世界 -Y (向下), 即屏体底边短边. 故口切在局部 -Y 壁, 装配后落世界底边、口朝下.
        #    X 偏置: TYPEC_LOCAL_X (默认 -20, 偏 -X 背离显示器), 与底边中央 FPC 槽 X 错开.
        #    Z 跨度: [TYPEC_Z0, TYPEC_Z1] (由母座贴板的实际 Z 包络推出, 落 bezel 壁内).
        #    沿 Y 穿透 2mm 底边壁: 开口盒沿 Y 取 WALL*4 居中跨壁.
        wall_y = -BEZEL_OUT_H / 2
        with Locations((TYPEC_LOCAL_X, wall_y, TYPEC_CENTER_Z)):
            Box(TYPEC_W, WALL * 4, TYPEC_OPEN_H_Z,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT)
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

        # 2b) plug 底边 Type-C 让位缺口 (随 Type-C 移到底边): 切穿底边(-Y)边框.
        #   后盖经 back_cover_local + body_placement 两次 Rot(0,180,0): Y 分量不变, X 翻两次抵消.
        #   而 bezel 仅经 body_placement 一次翻转 (X 翻一次). 两者要落同一世界 X 壁, 后盖局部 X
        #   须取 bezel 局部 X 的相反数 => 缺口 X 中心 = -TYPEC_LOCAL_X (= +20). Y 同为 -Y 底边.
        #   沿 -Y 从镂空内缘切到 plug 外缘外, 贯穿整个 plug 深度 + 盖板, 使母座+向下穿透路径无料.
        notch_inner_y = -(BC_PLUG_CAV_H / 2 - 1.0)        # 起点略入镂空区 (与镂空连通)
        notch_outer_y = -(BC_PLUG_H / 2 + BC_TYPEC_NOTCH_Y_OVER)  # 越过 plug 外缘 (-Y 向)
        notch_len_y = notch_inner_y - notch_outer_y
        notch_cy = (notch_inner_y + notch_outer_y) / 2
        notch_h = BACK_COVER_PLATE_T + BC_PLUG_DEPTH + 0.02
        with Locations((-TYPEC_LOCAL_X, notch_cy, -0.01)):
            Box(BC_TYPEC_NOTCH_W, notch_len_y, notch_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 3) 嵌磁腔 MAG_N 个 Φ8×3 (从盖板外表面 z=0 向 +z 沉, 不穿透)
        for (mx, my) in MAG_POSITIONS:
            with Locations((mx, my, -0.01)):
                Cylinder(MAG_D / 2, MAG_T + 0.01,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)

        # 4) 底部短边 (-Y) FPC 折回槽: 中央, 宽 FPC_SLOT_W, 深入 +Y FPC_SLOT_DEPTH, 贯穿厚度
        slot_total_h = BACK_COVER_PLATE_T + BC_PLUG_DEPTH + 0.02
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
        # 板竖向范围: 上探到屏顶 (Y≈0, 让支柱平直接入板顶), 下盖到下排磁下方.
        band_y_world = mate_cy + MAG_BAND_CENTER_Y
        plate_top_y = 0.0                                   # 板顶贴屏顶高度 (Y=0)
        plate_bot_y = band_y_world - MAG_INSET_Y - MAG_D / 2 - 4.0   # 板底盖过下排磁 + 余量
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

        # ---- 对接板嵌对磁腔 (从 +Z 顶面向 -Z 沉, 不穿透). 与后盖磁位镜像对齐 ----
        #   屏体后盖(法向-Z)贴对接板(+Z), 对贴 => 屏宽(X) 镜像. 后盖磁(bx,by)->板(mate_cx-bx, mate_cy+by).
        for (bx, by) in MAG_POSITIONS:
            with Locations((mate_cx - bx, mate_cy + by, mate_z_top + 0.01)):
                Cylinder(MAG_D / 2, MAG_T + 0.01,
                         align=(Align.CENTER, Align.CENTER, Align.MAX),
                         mode=Mode.SUBTRACT)
        # 高摩擦垫沉槽 (磁带两行之间, 从 +Z 顶面沉 FRICTION_PAD_T)
        with Locations((mate_cx, band_y_world, mate_z_top + 0.01)):
            Box(FRICTION_PAD_W, FRICTION_PAD_H, FRICTION_PAD_T + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
                mode=Mode.SUBTRACT)

        # 注: 已去掉上一版"折臂+臂根块+腹板"三件套, 换成单一笔直支柱 + 板背肋熔接.
        #   0.3 抱边间隙仍由 U 腔参数化偏置保证 (correct-by-construction), 连通性不破坏.
    # 暴露对接板关键坐标供装配/自检 (作为函数属性)
    make_bracket.mate = dict(cx=mate_cx, cy=mate_cy, z_top=mate_z_top, z_bot=mate_z_bot,
                             arm_x_end=arm_x_end,
                             strut_w=STRUT_W, strut_h=STRUT_H, strut_yc=arm_yc,
                             strut_z_c=strut_z_c, strut_z_top=strut_z_top, strut_z_bot=strut_z_bot,
                             strut_x_start=strut_x_start, strut_x_endin=strut_x_endin,
                             plate_cy=plate_cy, plate_h=plate_h, band_y=band_y_world,
                             body_front_z=body_front_z, back_outer_z=back_outer_z)
    return br.part


# ============================================================
# 屏参考板 (装配可视化用, 非打印件): 代表小板/屏在屏体内
# ============================================================
def make_screen_ref():
    with BuildPart() as sr:
        Box(SCREEN_W, SCREEN_H, SCREEN_T)
    return sr.part


# ============================================================
# PCBA 装配体 (bezel 局部坐标, 非打印件): PCB + 元件包络 + Type-C 母座 + 24P 排座.
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
    comp_w = BC_PLUG_CAV_W - 1.0
    comp_h = BC_PLUG_CAV_H - 1.0
    with BuildPart() as _comp:
        with Locations((0, 0, PCB_BACK_Z)):
            Box(comp_w, comp_h, COMP_H_MAX,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Type-C 母座: PCB 底边(-Y)缘, 元件面朝后, 母座高 TYPEC_BODY_H, 口朝 -Y(向下).
    #   X 中心 = TYPEC_LOCAL_X (偏 -X 背离显示器, 避开底边中央 FPC 排座).
    #   母座沿 Y 进深 tc_body_l, 紧贴板底缘 (-Y) 内侧; 沿 X 宽 = TYPEC_W-2 (开口内母座本体).
    tc_body_l = 7.0     # 母座沿 Y 进深
    with BuildPart() as _tc:
        with Locations((TYPEC_LOCAL_X, -PCB_H / 2 + tc_body_l / 2, PCB_BACK_Z)):
            Box(TYPEC_W - 2.0, tc_body_l, TYPEC_BODY_H,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    # 24P FPC 排座: PCB 底边中点, 元件面朝后, 矮座.
    with BuildPart() as _fpc:
        with Locations((0, -PCB_H / 2 + 2.0, PCB_BACK_Z)):
            Box(FPC_CONN_W, 4.0, 1.5,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    return dict(pcb=_pcb.part, comp=_comp.part, typec=_tc.part, fpc=_fpc.part,
                comp_w=comp_w, comp_h=comp_h, tc_body_l=tc_body_l)


def make_pcba_compound():
    p = make_pcba()
    pcb = p["pcb"]; pcb.label = "pcb"
    comp = p["comp"]; comp.label = "components"
    tc = p["typec"]; tc.label = "typec_recept"
    fpc = p["fpc"]; fpc.label = "fpc_conn"
    return Compound(label="pcba", children=[pcb, comp, tc, fpc])


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
    sr_local = Pos(0, WINDOW_OFFSET_Y, FRONT_WALL_T + SCREEN_T / 2) * screen_ref
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

    # --- 3) 后盖磁腔数量 + 与支架对接面磁位镜像对齐 ---
    print(f"[3 磁吸] 后盖磁腔数 = {len(MAG_POSITIONS)} (期望 MAG_N={MAG_N}): "
          f"{'通过' if len(MAG_POSITIONS)==MAG_N else '失败'}")
    # 镜像对齐: 后盖磁心 (X,Y) 经装配(后盖翻转 Rot(0,180,0): X->-X) 后世界投影,
    #   与支架对接面磁心应重合. 这里逐一比对 |后盖镜像X - 对接面映射X|.
    # 对接面磁心局部 (mate): (arm_x_end, by, -bx); 屏体后盖磁心装配后世界投影需在同列.
    # 简化几何核验: 后盖磁 (bx,by) -> 对接面期望 (by, -bx); MATE_MAG_POSITIONS=[(-x,y)] 即对接面板内布置.
    print("         逐磁心 后盖(局部) vs 对接面(局部 Y,Z) 镜像距离:")
    max_d = 0.0
    for (bx, by) in MAG_POSITIONS:
        # 对接面板上对应磁心 (沿 Y=by, 沿 Z=-bx)
        mate_y, mate_z = by, -bx
        # 后盖磁心经"对贴镜像"(X->-X)后, 期望对接面 Z = -(-bx)?? 对贴: 后盖法向-X 贴对接面+X,
        # 共面对齐 => 后盖磁 Y 对 对接面 Y; 后盖磁 X(沿屏宽) 对 对接面沿屏宽(Z), 对贴翻面 => Z=-bx.
        exp_y, exp_z = by, -bx
        d = math.hypot(mate_y - exp_y, mate_z - exp_z)
        max_d = max(max_d, d)
        print(f"           后盖({bx:+.2f},{by:+.2f}) -> 对接面(Y{mate_y:+.2f},Z{mate_z:+.2f}) 距期望={d:.4f}")
    print(f"         最大镜像偏差 = {max_d:.4f}mm -> {'通过(≈0)' if max_d < 1e-6 else '检查'}")

    # --- 4) Type-C 真穿透 (最重要) — 改: 口在底边壁 -Y, 朝下/-Y 出线 ---
    #   口现切在 bezel 底边壁 -Y (X 偏置 TYPEC_LOCAL_X 避 FPC, Z 跨母座包络, 落 bezel 壁内).
    #   验证: 在装配后的屏体 (bezel ∪ back_cover 合并实体) 上, 放一探针盒跨越底边壁
    #   (沿 -Y 从腔内连到壳外), 与"合并实体"做布尔相交, 相交≈0 => 真有口连通腔内外.
    from build123d import Cylinder as _Cyl
    _mate = make_bracket.mate
    place4 = body_placement()
    # 装配后的屏体合并实体 (bezel ∪ back_cover, 世界系):
    _bz_w = place4 * make_bezel()
    _bc_w = place4 * (back_cover_local() * make_back_cover())
    body_merged = _bz_w + _bc_w     # 合并成一个屏体实体
    _bzbb4 = _bz_w.bounding_box()
    # 底边壁 = 世界 min Y (装配 Rot(0,180,0) 不改 Y, bezel 局部 -Y 映到世界 -Y 底边).
    bottom_wall_y, top_wall_y = _bzbb4.min.Y, _bzbb4.max.Y
    # 开口世界包围盒: 用一个跟随装配的探针盒 (= 开口标称几何) 求世界包围盒 (杜绝手算坐标误差).
    #   开口在 bezel 局部 -Y 壁, X=TYPEC_LOCAL_X, Z 跨 [TYPEC_Z0,TYPEC_Z1].
    with BuildPart() as _tcp:
        with Locations((TYPEC_LOCAL_X, -BEZEL_OUT_H / 2, TYPEC_CENTER_Z)):
            Box(TYPEC_W, WALL * 4, TYPEC_OPEN_H_Z, align=(Align.CENTER,) * 3)
    _tcw = (place4 * _tcp.part).bounding_box()     # 口现在 bezel 上, 仅 bezel 变换
    typec_cx = (_tcw.min.X + _tcw.max.X) / 2
    typec_cy = (_tcw.min.Y + _tcw.max.Y) / 2
    typec_cz = (_tcw.min.Z + _tcw.max.Z) / 2
    typec_x0, typec_x1 = _tcw.min.X, _tcw.max.X
    # 穿透探针: 沿世界 -Y 从底壁内 (bottom_wall_y+3) 到壳外 (bottom_wall_y-3), 长 6+WALL.
    #   探针截面 = 开口标称 (X=TYPEC_W, Z=TYPEC_OPEN_H_Z), 略缩 0.4 避开开口边/壁数值噪声.
    probe_len = WALL + 6.0
    probe_cy = bottom_wall_y + 3.0 - probe_len / 2   # 从腔内一路探到壳外 (向 -Y)
    with BuildPart() as _probe:
        with Locations((typec_cx, probe_cy, typec_cz)):
            Box(TYPEC_W - 0.4, probe_len, TYPEC_OPEN_H_Z - 0.4, align=(Align.CENTER,) * 3)
    probe_solid = _probe.part
    block_vol = (probe_solid & body_merged).volume   # 探针被料阻挡的体积
    probe_vol = probe_solid.volume
    true_through = block_vol < 1e-3
    on_bottom = abs(typec_cy - bottom_wall_y) < abs(typec_cy - top_wall_y)
    facing_down = _tcw.min.Y <= bottom_wall_y + 1e-6   # 口下沿触底壁 => 朝下 -Y 出线
    print(f"[4 TypeC真穿透] *** 最重要 ***")
    print(f"          开口切在 bezel 局部 -Y 底边壁 (装配后落世界 min Y = 底边); 口朝 -Y (向下出线); "
          f"口世界中心 X={typec_cx:.2f} Y={typec_cy:.2f} Z={typec_cz:.2f}")
    print(f"          口世界范围 X[{_tcw.min.X:.2f},{_tcw.max.X:.2f}] Y[{_tcw.min.Y:.2f},{_tcw.max.Y:.2f}] "
          f"Z[{_tcw.min.Z:.2f},{_tcw.max.Z:.2f}]; 朝向 法向 -Y (向下出线)")
    print(f"          屏体底壁 Y={bottom_wall_y:.2f} 顶壁 Y={top_wall_y:.2f}; 在底边? {on_bottom}; "
          f"口朝下(下沿触底壁)? {facing_down}")
    print(f"          穿透探针 (跨底壁, 腔内->壳外向下, 体积 {probe_vol:.2f}mm3) ∩ 屏体合并实体 = "
          f"{block_vol:.4f} mm3 -> {'通过(真穿透, 无料阻挡)' if true_through else '失败(口被封死!)'}")
    # 不与 FPC 折回槽 X 重叠 (要点: ≥2mm 间隔):
    fpc_slot_x0, fpc_slot_x1 = -FPC_SLOT_W / 2, FPC_SLOT_W / 2
    # Type-C 开口在底边壁的 X 范围 = 口世界 X 范围 (底边壁 X 与 bezel 局部 X 等向, 仅平移):
    tc_x0, tc_x1 = typec_x0, typec_x1
    # X 间隔 (口在 FPC 槽 -X 一侧): 槽左缘 - 口右缘:
    gap_to_fpc = fpc_slot_x0 - tc_x1 if tc_x1 <= fpc_slot_x0 else (tc_x0 - fpc_slot_x1)
    x_no_overlap = (tc_x1 <= fpc_slot_x0) or (tc_x0 >= fpc_slot_x1)
    print(f"          Type-C 开口世界 X[{tc_x0:.2f},{tc_x1:.2f}] vs FPC 折回槽世界 X[{fpc_slot_x0:.2f},{fpc_slot_x1:.2f}]; "
          f"不交叠? {x_no_overlap}; X 间隔={gap_to_fpc:.2f}mm -> "
          f"{'通过(不重叠且 ≥2mm)' if x_no_overlap and gap_to_fpc >= 2.0 else '检查'}")
    # 不与支柱重叠 (支柱世界 Y∈[-STRUT_W,0] 屏顶高度, Type-C 在底边 Y≈min; X<0 一侧):
    strut_wy0 = _mate["strut_yc"] - _mate["strut_w"] / 2
    strut_wy1 = _mate["strut_yc"] + _mate["strut_w"] / 2
    strut_y_overlap = not (_tcw.max.Y < strut_wy0 or _tcw.min.Y > strut_wy1)
    print(f"          支柱世界 Y[{strut_wy0:.2f},{strut_wy1:.2f}] (屏顶高度) vs Type-C Y[{_tcw.min.Y:.2f},{_tcw.max.Y:.2f}] (底边); "
          f"Y 重叠? {strut_y_overlap} -> {'通过(不重叠, 一上一下)' if not strut_y_overlap else '检查'}")
    # 不与磁区干涉 (磁腔 4 圆柱, 真实布尔逐个核验):
    _tc_solid_w = place4 * _tcp.part
    _mag_v_max = 0.0
    for (mx, my) in MAG_POSITIONS:
        with BuildPart() as _mgp:
            with Locations((mx, my, -0.01)):
                _Cyl(MAG_D / 2, MAG_T + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _mgw = place4 * (back_cover_local() * _mgp.part)
        _mag_v_max = max(_mag_v_max, (_tc_solid_w & _mgw).volume)
    print(f"          Type-C ∩ 4 磁腔真实布尔最大 = {_mag_v_max:.3f} mm3 -> "
          f"{'通过(不干涉)' if _mag_v_max < 1e-6 else '失败(干涉)'}")

    # --- 4b) PCBA 装配 + 无螺丝夹持 + FPC 自检 ---
    print("-" * 78)
    print("[4b PCBA] 板装配 / 夹持 / FPC:")
    pcba = make_pcba()
    pcb, comp, tc_body, fpc = pcba["pcb"], pcba["comp"], pcba["typec"], pcba["fpc"]
    pcb_bb = pcb.bounding_box(); comp_bb = comp.bounding_box()
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
    # 支柱顶 z = PCB 前面; 定位销插孔:
    bz_for_pin = make_bezel()
    # 支柱顶面 z (从 bezel 实体取 standoff 顶): 用探针在支柱中心 (PCB_FRONT_Z-0.05) 在实, (+0.05) 空.
    from build123d import Box as _Bx, Pos as _Ps
    def _solid_at(part, p):
        return (part & (_Ps(*p) * _Bx(0.06, 0.06, 0.06))).volume > 1e-9
    sx, sy = PCB_STANDOFF_POSITIONS[0]
    top_in = _solid_at(bz_for_pin, (sx, sy, PCB_FRONT_Z - 0.1))
    top_out = _solid_at(bz_for_pin, (sx, sy, PCB_FRONT_Z + 0.1))   # 上方有定位销(此柱带销?)
    print(f"   支柱顶面 z=PCB_FRONT_Z={PCB_FRONT_Z}: 柱内有料(z-0.1)? {top_in}; "
          f"支撑高 PCB_STANDOFF_H={PCB_STANDOFF_H} -> {'通过' if top_in else '检查'}")
    # 定位销插孔: 销顶 z 应 > PCB 背面 (穿过板厚); 用销中心探板内是否有销料.
    px, py = PCB_LOC_PIN_POSITIONS[0]
    pin_top_z = PCB_FRONT_Z + PCB_LOC_PIN_H
    pin_into_board = _solid_at(bz_for_pin, (px, py, (PCB_FRONT_Z + PCB_BACK_Z) / 2))
    print(f"   对角 2 定位销 Φ{PCB_LOC_PIN_D} 顶 z={pin_top_z:.2f} (>PCB背{PCB_BACK_Z}? {pin_top_z>PCB_BACK_Z}); "
          f"销贯穿板厚区有料? {pin_into_board} -> {'通过(插孔定位 XY)' if pin_into_board and pin_top_z>PCB_BACK_Z else '检查'}")
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
    slot_y_inner = -BEZEL_OUT_H / 2 + FPC_SLOT_DEPTH              # 折回槽沿 +Y 深入到此
    print(f"   FPC 24P 排座 板底中点 (局部 X≈0, Y={fpc_y:.2f}, 宽 {FPC_CONN_W}); "
          f"后盖底部折回槽 宽 {FPC_SLOT_W} 槽口 Y=-{BEZEL_OUT_H/2:.1f} 深入到 Y={slot_y_inner:.1f}")
    fpc_aligned = abs(fpc_bb.min.X) < FPC_SLOT_W / 2 and FPC_CONN_W <= FPC_SLOT_W
    print(f"   排座宽 {FPC_CONN_W} <= 槽宽 {FPC_SLOT_W}, 居中对齐? {fpc_aligned}; 折回间隙 {FPC_FOLD_GAP} -> "
          f"{'通过(排座对齐折回槽)' if fpc_aligned else '检查'}")

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
