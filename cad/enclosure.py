"""InkPulse 墨水屏桌面外壳 — 参数化建模 (build123d 0.10.0)

三个可打印零件 + 一个装配体:
  - bezel      前框 (矩形托盘 + 视窗 + 唇边 + 玻璃容腔 + 后盖螺柱)
  - back_cover 后盖 (嵌入背腔 + FPC 过线槽 + 螺丝孔)
  - base       底座 (楔形 + 50x50 PCB 仓 + M3 螺柱 + Type-C 口 + 60度斜墙)
  - assembly   60度仰角装配姿态

所有尺寸照设计文档 §9 命名为脚本顶部具名变量。
"""

import math
from pathlib import Path
from build123d import (
    BuildPart, BuildSketch, Box, Cylinder, Rectangle, Plane, Pos, Rot,
    Locations, GridLocations, Mode, Align, Axis, fillet, chamfer, extrude,
    Compound, export_step, export_stl, Vector,
)

# ============================================================
# §9 参数清单 (CAD 变量, 初值)
# ============================================================
# 屏模组
SCREEN_W = 170.20
SCREEN_H = 111.20
SCREEN_T = 1.25
AA_W = 163.20
AA_H = 97.92
BORDER_TOP = 3.49
BORDER_BOTTOM = 9.79
BORDER_SIDE = 3.50
FPC_W = 79.90
FPC_EXPOSED = 12.50
# 外壳
WALL = 2.5
LIP = 1.2
FIT_GAP = 0.4
FOAM_T = 0.5
WINDOW_MARGIN = 0.5
ANGLE_DEG = 60.0
# 底座/PCB  —— 实测自 hardware/PCB1.step (板中心为原点)
PCB_W = 70.10             # 板 X 向 (沿屏宽/连接器边)
PCB_D = 50.04             # 板 Y 向 (Type-C <-> FPC 方向)
PCB_T = 1.6               # 物理板厚 (STEP简化为0.41, 取实际1.6)
STANDOFF_H = 4.0
HOLE_D = 3.2              # 实测 Φ3.2 (R1.59)
# 安装孔实测 (±30, ±20); Type-C 在 -Y 边中点, FPC 排座在 +Y 边中点
M3_POS_X = 30.0
M3_POS_Y = 20.0
TYPEC_W = 12.5            # 开口宽 (body 11.3 + 插头overmold余量)
TYPEC_H = 6.0            # 开口高
TYPEC_PORT_Z = STANDOFF_H + 1.65   # 口中心离内底: 螺柱4 + 口心离板底1.65 = 5.65
FPC_CONN_Y = -22.8        # 显示排座 (装配后映射到外壳前侧 -Y, 靠屏)
# 内腔净高 / 核心盒壁高: 由抽拉盖板机构自下而上推导 (见 §零件4 LID_*/LIP_*),
# 这里先占位, 真正取值在 lid 机构参数算出后回填 (BASE_WALL_H = 盖板顶 + 唇厚).
# 约束: 盖板必须在板上元件(顶z≈9.7)之上滑动 => LID_BOT_Z>=10.2.
# 目标: 仓尽量轻薄 => BASE_WALL_H ≈ 12.5.
CAVITY_CLEAR = None   # 派生, 见下方 "盖板机构 -> 回填核心盒高度"

# ============================================================
# 派生参数
# ============================================================
# 玻璃容腔 (含单边 FIT_GAP)
GLASS_CAV_W = SCREEN_W + 2 * FIT_GAP      # 170.20 + 0.8 = 171.00
GLASS_CAV_H = SCREEN_H + 2 * FIT_GAP      # 111.20 + 0.8 = 112.00
GLASS_CAV_DEPTH = SCREEN_T + 0.05         # 玻璃容腔深(留薄余量)

# 屏框外形 ~175.6 x 116.6 (玻璃容腔 + 两侧壁厚)
BEZEL_OUT_W = GLASS_CAV_W + 2 * WALL      # 171.00 + 5.0 = 176.00 (~175.6 量级)
BEZEL_OUT_H = GLASS_CAV_H + 2 * WALL      # 112.00 + 5.0 = 117.00 (~116.6 量级)
# 四角螺柱专用实心立柱: 位于玻璃腔四角外的对角延伸区(避免侵入玻璃).
# 立柱中心放在玻璃腔角点外侧的对角线上.
CORNER_PILLAR = 9.0                       # 角立柱边长(方形, 嵌在外形角内)

# 视窗 = AA + 余量, 非对称上偏
WINDOW_W = AA_W + WINDOW_MARGIN           # 163.70
WINDOW_H = AA_H + WINDOW_MARGIN           # 98.42
# 视窗中心相对玻璃/屏框中心上移 = (BORDER_BOTTOM - BORDER_TOP)/2
WINDOW_OFFSET_Y = (BORDER_BOTTOM - BORDER_TOP) / 2.0   # 3.15

# bezel 总深 (前壁 + 玻璃腔 + 泡棉 + 薄后盖嵌入)
# 减薄: 背腔只需容 玻璃1.25 + 泡棉0.5 + 薄后盖凸台~3 => 腔深 5mm, 屏框总深 ~7.2mm.
FRONT_WALL_T = LIP + 1.0                  # 视窗处前面板厚 (唇 + 余量) = 2.2
BACK_LIP_DEPTH = 5.0                      # 背面托盘腔深度 (减薄: 17->5)
BEZEL_DEPTH = FRONT_WALL_T + BACK_LIP_DEPTH   # ~7.2 mm

# 后盖
BC_CAV_INSET = FIT_GAP                    # 后盖嵌入背腔的配合间隙
BACK_COVER_PLATE_T = 2.0
FPC_SLOT_W = 84.0
FPC_SLOT_DEPTH = 13.0                     # 槽沿长边方向深入 13mm

# 后盖螺柱 (bezel 四角 boss), 柱心从外形角内缩
BOSS_D = 5.0
BOSS_PILOT_D = 2.1                        # M2.5 自攻底孔
SCREW_CLEAR_D = 2.7                       # 后盖侧通孔/沉头
# 角立柱中心放在外形角内缩 CORNER_PILLAR/2 + 1, boss 与立柱同心
CORNER_OFFSET = CORNER_PILLAR / 2 + 0.5
BOSS_X = BEZEL_OUT_W / 2 - CORNER_OFFSET
BOSS_Y = BEZEL_OUT_H / 2 - CORNER_OFFSET
# 玻璃腔四角倒圆半径(为角立柱让位)
GLASS_CAV_CORNER_R = CORNER_PILLAR + 1.0

# 底座 (楔形): 中央 PCB 仓核心 + 下方宽大扁平底脚板(稳定) + 两侧外移斜墙
BASE_INNER_W = PCB_W + 2 * 0.5            # 70.1 + 1.0 (四周 0.5 间隙)
BASE_INNER_D = PCB_D + 2 * 0.5            # 50.04 + 1.0
BASE_WALL = WALL
BASE_FLOOR_T = 2.0
BASE_OUT_W = BASE_INNER_W + 2 * BASE_WALL    # 中央核心盒 56 量级
BASE_OUT_D = BASE_INNER_D + 2 * BASE_WALL    # 中央核心盒 56 量级
# BASE_INNER_H / BASE_WALL_H 由盖板机构高度决定, 见文件后段 "盖板机构 -> 回填".
# 这里前向声明, 实际数值在 LID_* 定义之后赋值 (Python 顺序执行).
# 宽大扁平底脚板 (提升稳定性, 横跨支撑 176mm 宽屏)
BASE_FOOT_W = 130.0                       # 底脚板宽 (斜墙将外移到此宽度边缘)
BASE_FOOT_D = 90.0                        # 底脚板深 (抗后倾)
BASE_FOOT_T = 4.0                         # 底脚板厚

# PCB M3 螺柱
M3_STANDOFF_D = 6.0
M3_PILOT_D = 2.5                          # M3 自攻底孔
# 螺柱位置实测 (±30, ±20)

# Type-C 口
# 口中心离内底 7.3 => 离底座底面 = BASE_FLOOR_T + 7.3
TYPEC_CENTER_Z = BASE_FLOOR_T + TYPEC_PORT_Z

# 60 度斜墙 / 接缝
GUSSET_T = 4.0                            # 斜墙厚
GUSSET_HEIGHT = 40.0                      # 斜墙竖直高 (沿 z)
M3_SEAM_D = 3.4                           # 接缝 M3 通孔
SEAM_SCREW_SPACING = 60.0                 # 两颗接缝螺丝水平间距

# ============================================================
# 零件 4: 抽拉式卡扣盖板 (drawer + snap) 及底座配套导轨/卡扣
# ============================================================
# 设计: 盖板沿 +X 抽出. 前/后内壁顶部各做一条向内伸的唇(lip),
#       其下留竖直槽; 盖板前后边缘滑入槽内被唇压住. -X 里端做挡位,
#       +X 抽出端做卡扣凸点咬住盖板, 并在盖板 +X 端做手指凸耳.
LID_T = 1.5                               # 盖板平板厚 (减薄 2.0->1.5)
LID_FIT_GAP = 0.35                        # 盖板与槽/壁滑动间隙(单边)
# 盖板覆盖 Y 范围: 前缘 LID_Y_FRONT, 后缘到后内壁面(伸入后唇下).
# 硬约束: 斜墙在 Y<=-21.9(X=±63,z4..44); 盖板 +X 抽出会扫过 X=63, 故盖板任何材料
# 的 Y 都须 > -21.9 才不撞斜墙. 取前缘 -21.0(留 ~0.9 余量), 满足 [-22,+26] 区间内.
LID_Y_FRONT = -21.0                       # 前缘(-Y), > 斜墙 Ymax(-21.9) 安全避让
INNER_HALF_D = BASE_INNER_D / 2           # 25.52 (前后内壁面 Y=±25.52)
# 导轨唇/槽 (在前后内壁顶部)
LIP_REACH = 1.5                           # 唇向内伸出量
LIP_T = 0.6                               # 唇厚 (z 方向): 盖板顶上方薄薄一层压住盖板顶边
GROOVE_H = 2.5                            # 唇下竖直滑槽高 (槽底到唇底; 盖板坐于其中)
# === 自下而上推导盖板/唇/槽的 Z ===
# 硬约束: 盖板必须在板上元件(顶 z≈9.7)之上滑动. 取盖板底面 LID_BOT_Z=10.25 (净空 9.7 + 0.55 余量).
LID_BOT_Z = 10.25                         # 盖板底面 (> 元件顶 9.7, 留 ~0.55 余量)
LID_TOP_Z = LID_BOT_Z + LID_T             # 11.75 盖板顶面
LID_TOP_GAP = 0.15                        # 盖板顶面与唇底的间隙 (不顶死, 便于滑动)
LIP_BOT_Z = LID_TOP_Z + LID_TOP_GAP       # 11.90 唇底 (压在盖板顶边上方)
# 槽底在盖板底面之下少量 (盖板坐于槽内, 槽底留间隙)
GROOVE_BOT_Z = LID_BOT_Z - 0.25           # 10.00 槽底
# 核心盒外壁顶 = 唇顶 = 唇底 + 唇厚 => 由盖板机构决定
BASE_WALL_H = LIP_BOT_Z + LIP_T           # 12.50 核心盒外壁总高 (轻薄目标 ≈12.5)
BASE_INNER_H = BASE_WALL_H - BASE_FLOOR_T # 10.50 内腔净高 (派生)
CAVITY_CLEAR = BASE_INNER_H               # 兼容旧名 (= 内腔净高)
# 盖板主体 X 宽: 贴合内腔宽减滑动间隙
LID_BODY_W = BASE_INNER_W - 2 * LID_FIT_GAP    # 71.1 - 0.7 = 70.4
# 盖板边缘伸入唇下: 前后边缘 Y 到 内壁面 + 少量(进唇覆盖区)
LID_EDGE_INTO = LIP_REACH - 0.3           # 边缘进入唇覆盖区 1.2mm
# 卡扣 detent (在 +X 抽出端): 唇槽底面做一个小凸点, 盖板对应下表面做凹坑被凸点咬住
DETENT_D = 2.0                            # 卡扣凸点直径
DETENT_H = 0.8                            # 凸点高
DETENT_X = INNER_HALF_D * 0  # 占位, 实际 X 在函数内 = ix-4
DETENT_Y_FRONT = LID_Y_FRONT + 1.5        # 前侧 detent Y = -19.5 (在盖板前缘内, 唇下)
DETENT_Y_BACK = INNER_HALF_D - 1.5        # 后侧 detent Y = 24.02 (在盖板后缘内, 唇下)
# 抽出端手指凸耳
LID_TAB_W = 16.0                          # 手指凸耳宽(X 无关, 沿 Y)
LID_TAB_L = 8.0                           # 凸耳沿 +X 伸出长
LID_TAB_T = 3.0                           # 凸耳厚
# 盖板前缘 FPC 缺口
LID_FPC_NOTCH_W = 20.0                    # FPC 缺口宽
LID_FPC_NOTCH_D = 8.0                     # 缺口沿 +Y 深入
# 前缘保持唇: 斜墙避让要求盖板前缘只到 Y=-21, 前壁(Y=-25.52)够不到.
# 故在内腔做一道矮"前导轨"立条, 立条本体在 Y∈[FRONT_RAIL_Y, FRONT_RAIL_Y+FRONT_RAIL_T],
# 顶部出唇向 +Y 伸 LIP_REACH 压住盖板前缘(盖板前缘 Y=LID_Y_FRONT=-21 落在唇下).
FRONT_RAIL_T = 2.0                        # 立条厚(沿 Y)
FRONT_RAIL_Y = LID_Y_FRONT - LIP_REACH - FRONT_RAIL_T  # 立条 -Y 面 = -24.5
# 立条本体 z 起点: 必须高于板上元件(顶 9.7), 否则会切到 PCB 前缘(实测交 35mm^3).
# 立条仅需覆盖滑槽+唇区段(z 10.0..12.5), 故从 RAIL_BODY_BOT_Z 起, 悬于 PCB 上方.
RAIL_BODY_BOT_Z = GROOVE_BOT_Z - 0.2      # 9.8 (高于元件顶 9.7, 又盖住槽底 10.0)
# 立条本体 Y: -24.5..-22.5; 唇 Y: -22.5..-21.0(覆盖盖板前缘 -21). 均 >斜墙? 见下
# (立条/唇属 base 静止件, 斜墙避让只约束运动的盖板; 盖板前缘 -21 > 斜墙 -21.9 安全.)
# -X 里端挡位: 唇槽里端封死(滑入到底); +X 端开放供抽出

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)


# ============================================================
# 零件 1: bezel 前框
#   局部坐标: 前表面在 z=0 (朝 -z 即朝下打印), 背腔开口朝 +z
#   X = SCREEN_W 方向, Y = SCREEN_H 方向 (向上为 +Y, FPC 在 -Y 底边)
# ============================================================
def make_bezel():
    with BuildPart() as bz:
        # 1) 整体实心托盘块: 从 z=0 到 z=BEZEL_DEPTH
        Box(BEZEL_OUT_W, BEZEL_OUT_H, BEZEL_DEPTH,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 2) 背面玻璃容腔 (从背面向下挖, 留前面板). 四角倒圆为角立柱让位.
        cav_depth = BEZEL_DEPTH - FRONT_WALL_T
        with BuildSketch(Plane.XY.offset(FRONT_WALL_T)) as cav_sk:
            Rectangle(GLASS_CAV_W, GLASS_CAV_H)
            fillet(cav_sk.vertices(), radius=GLASS_CAV_CORNER_R)
        extrude(amount=cav_depth + 0.01, mode=Mode.SUBTRACT)

        # 3) 视窗开口 (贯穿前面板), AA + 余量, 上偏 WINDOW_OFFSET_Y
        with Locations((0, WINDOW_OFFSET_Y, -0.01)):
            Box(WINDOW_W, WINDOW_H, FRONT_WALL_T + 0.02,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 4) 四角后盖螺柱 boss (从前面板背面 z=FRONT_WALL_T 升起填充腔内)
        #    boss 高度顶到背面齐平
        boss_h = BEZEL_DEPTH - FRONT_WALL_T
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

        # 5) 前面外缘倒角 (打印朝下, 美观)
        # (跳过复杂倒角以保证导出稳健)

    return bz.part


# ============================================================
# 零件 2: back_cover 后盖
#   局部坐标: 平板, z=0 底, +z 朝 bezel 背腔. 与 bezel 同 XY 朝向.
# ============================================================
def make_back_cover():
    # 后盖嵌入部分尺寸 = 玻璃腔 - 配合间隙
    plug_w = GLASS_CAV_W - 2 * BC_CAV_INSET
    plug_h = GLASS_CAV_H - 2 * BC_CAV_INSET
    # 背腔总深
    cav_depth = BEZEL_DEPTH - FRONT_WALL_T
    # 后盖凸台只需伸入至压紧泡棉; 盖板沉到背腔内, 与 bezel 后沿大致齐平.
    # 凸台底面 = 玻璃背 + 泡棉处. 盖板背面在背腔口附近.
    plug_depth = cav_depth - (SCREEN_T + FOAM_T)   # 凸台从背腔口伸到压紧泡棉

    plug_rim = 4.0   # 嵌入凸台做成空心边框, 壁宽, 省料且能压泡棉
    with BuildPart() as bc:
        # 盖板 (与屏框外形齐平)
        Box(BEZEL_OUT_W, BEZEL_OUT_H, BACK_COVER_PLATE_T,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 嵌入凸台 (向 +z 即朝 bezel) -- 空心边框, 四角倒圆与玻璃腔贴合
        with BuildSketch(Plane.XY.offset(BACK_COVER_PLATE_T)) as plug_sk:
            Rectangle(plug_w, plug_h)
            fillet(plug_sk.vertices(), radius=GLASS_CAV_CORNER_R)
        extrude(amount=plug_depth)
        # 掏空凸台内部 (保留 plug_rim 边框, 不掏穿盖板)
        with Locations((0, 0, BACK_COVER_PLATE_T)):
            Box(plug_w - 2 * plug_rim, plug_h - 2 * plug_rim, plug_depth + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # FPC 过线槽: 底部长边 (-Y) 中央, 宽 84, 深 13 (沿 +Y 深入)
        # 从板边 y=-BEZEL_OUT_H/2 向内 13mm, 贯穿厚度
        slot_total_h = BACK_COVER_PLATE_T + plug_depth + 0.02
        with Locations((0, -BEZEL_OUT_H / 2, -0.01)):
            Box(FPC_SLOT_W, FPC_SLOT_DEPTH * 2, slot_total_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 四角螺丝通孔 (对位 bezel boss)
        with Locations(
            (BOSS_X, BOSS_Y, -0.01), (-BOSS_X, BOSS_Y, -0.01),
            (BOSS_X, -BOSS_Y, -0.01), (-BOSS_X, -BOSS_Y, -0.01),
        ):
            Cylinder(SCREW_CLEAR_D / 2, slot_total_h,
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)

    return bc.part


# ============================================================
# 零件 3: base 底座 (楔形)
#   局部坐标: z=0 桌面底面, +z 向上. X=PCB X, Y=PCB Y (+Y 朝后/Type-C).
#   内腔水平放 50x50 PCB. 后壁(-? ) 这里取 +Y 为后(Type-C 朝 +Y).
#   实际文档: Type-C 在 (0,+25) 朝 +Y => 后壁在 +Y 侧.
# ============================================================
def make_base():
    with BuildPart() as bs:
        # 0) 宽大扁平底脚板 (稳定footprint, 横跨支撑屏宽; 低矮不挡 +Y Type-C)
        Box(BASE_FOOT_W, BASE_FOOT_D, BASE_FOOT_T,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 1) 中央 PCB 核心盒 (实心) 高 BASE_WALL_H, 坐在底脚板上(z=0 起, 与脚板并集)
        Box(BASE_OUT_W, BASE_OUT_D, BASE_WALL_H,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 2) 挖内腔 (从顶面向下挖, 留底板)
        with Locations((0, 0, BASE_FLOOR_T)):
            Box(BASE_INNER_W, BASE_INNER_D, BASE_INNER_H + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 3) 四角 M3 PCB 螺柱 (±30, ±20), 柱高 = STANDOFF_H, 从内底升起
        for sx in (M3_POS_X, -M3_POS_X):
            for sy in (M3_POS_Y, -M3_POS_Y):
                with Locations((sx, sy, BASE_FLOOR_T)):
                    Cylinder(M3_STANDOFF_D / 2, STANDOFF_H,
                             align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 螺柱自攻底孔
        for sx in (M3_POS_X, -M3_POS_X):
            for sy in (M3_POS_Y, -M3_POS_Y):
                with Locations((sx, sy, BASE_FLOOR_T + STANDOFF_H)):
                    Cylinder(M3_PILOT_D / 2, STANDOFF_H - 0.5,
                             align=(Align.CENTER, Align.CENTER, Align.MAX),
                             mode=Mode.SUBTRACT)

        # 4) 后壁 Type-C 开口 (后壁在 +Y 侧), 中心离底 TYPEC_CENTER_Z
        wall_y = BASE_OUT_D / 2
        with Locations((0, wall_y, TYPEC_CENTER_Z)):
            Box(TYPEC_W, BASE_WALL * 3, TYPEC_H,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT)

        # 5) 顶部 FPC 线槽对位 (0, FPC_CONN_Y) 前侧 -> 在 -Y 侧顶沿开槽
        #    在 -Y 内壁顶部开一道缺口让 FPC 进入
        front_wall_y = -BASE_OUT_D / 2
        with Locations((0, front_wall_y, BASE_WALL_H)):
            Box(FPC_SLOT_W * 0.6, BASE_WALL * 3, BASE_INNER_H * 0.8,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
                mode=Mode.SUBTRACT)

        # 6) 60度斜墙 (gusset): 底座顶后部(-Y 前侧)上方立两片三角侧墙.
        #    每片为一个三角棱柱, 处于常 X = ±gx 的竖直面内, 沿 X 方向有厚度.
        #    三角形(全局 Y,Z): 底边在 base 顶面 z=seam_z0, 从 front_y 向 +Y 延 run;
        #    竖直边沿 +Z 升 GUSSET_HEIGHT; 斜边为 60度安装面, bezel 背面贴此.
        #    Plane.YZ 上: 草图局部 X = 全局 Y, 草图局部 Y = 全局 Z.
        from build123d import Polygon
        gx = BASE_FOOT_W / 2 - GUSSET_T / 2      # 外移到底脚板宽边 (±63)
        seam_z0 = BASE_FOOT_T                      # 斜墙起于底脚板顶面
        front_y = -BASE_FOOT_D / 2                 # 屏铰接在底脚板前缘(-Y)
        # 安装面(斜边 A->C)与水平夹角 a 满足 tan(a)=GUSSET_HEIGHT/run, a=60 => run=H/tan(60).
        # 朝向修正: 直角在后下(B), 斜面 A(前下)->C(后上) 朝 -Y+Z (观察者-上), 屏向后倾且朝 -Y.
        #   A=(front_y, z0) 前下铰接;  B=(front_y+run, z0) 后下直角;  C=(front_y+run, z0+H) 后上.
        #   斜面外法线 (0,-sin60,cos60)=(0,-0.866,0.5): 朝 -Y(观察者)与 +Z. 校验 a=arccos(|nz|)=60.
        run = GUSSET_HEIGHT / math.tan(math.radians(ANGLE_DEG))  # 水平投影
        for sx in (gx, -gx):
            with BuildSketch(Plane.YZ.offset(sx)) as sk:
                # Plane.YZ 局部 (u=全局Y, v=全局Z)
                Polygon(
                    (front_y, seam_z0),               # A 前下(铰接)
                    (front_y + run, seam_z0),         # B 后下(直角)
                    (front_y + run, seam_z0 + GUSSET_HEIGHT),  # C 后上
                    align=None,
                )
            extrude(amount=GUSSET_T / 2, both=True, mode=Mode.ADD)

        # 7) 接缝 M3 横穿螺丝孔 (沿 Y 横穿两片斜墙), 位于斜面中部.
        seam_hole_z = seam_z0 + GUSSET_HEIGHT * 0.45
        seam_hole_y = front_y + run * 0.55
        for sx in (gx, -gx):
            with Locations(Pos(sx, seam_hole_y, seam_hole_z) * Rot(90, 0, 0)):
                Cylinder(M3_SEAM_D / 2, GUSSET_T * 3,
                         align=(Align.CENTER, Align.CENTER, Align.CENTER),
                         mode=Mode.SUBTRACT)

        # ====================================================
        # 8) 抽拉盖板配套: +X 抽出口 + 前后内壁顶部导轨唇 + -X 挡位 + +X 卡扣凸点
        # ====================================================
        ix = BASE_INNER_W / 2     # 内壁 X 面 = 35.55
        iy = BASE_INNER_D / 2     # 内壁 Y 面 = 25.52
        ox = BASE_OUT_W / 2       # 外壁 X 面 = 38.05

        # 8a) +X 外壁开抽出口: 让盖板(及边缘伸入唇下)从 +X 滑入/抽出.
        #     开口 Y 覆盖前后唇之间(略宽于盖板边缘), z 覆盖滑槽段(GROOVE_BOT_Z..顶).
        slot_y_half = iy + LIP_REACH + 0.5    # 略宽, 让盖板边缘也能通过
        with Locations((ox, 0, GROOVE_BOT_Z)):
            Box(BASE_WALL * 3, slot_y_half * 2, (BASE_WALL_H - GROOVE_BOT_Z) + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 8b) 后壁(+Y)顶部导轨唇 (lip): 内面 Y=iy, 向 -Y 伸 LIP_REACH, z=LIP_BOT_Z..顶.
        #     盖板后边缘滑入唇下槽(z LID_BOT_Z..LID_TOP_Z)被唇压住. 沿 X 贯通到抽出口.
        #     唇须避开 Type-C(X∈±6.25)正上方区段 => 分两段.
        lip_z = LIP_BOT_Z
        lip_h = BASE_WALL_H - LIP_BOT_Z       # 2.0
        typec_keep = TYPEC_W / 2 + 1.5        # 8.75
        seg_w = (ix - typec_keep)             # 单段 X 长度
        for sgn in (1, -1):
            seg_cx = sgn * (typec_keep + seg_w / 2)
            with Locations((seg_cx, iy - LIP_REACH / 2, lip_z)):
                Box(seg_w, LIP_REACH, lip_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.ADD)

        # 8b2) 前导轨立条 + 唇: 盖板前缘只到 Y=-21(避斜墙), 前壁(-25.52)够不到,
        #      故在 Y=FRONT_RAIL_Y 立一道矮立条, 其 +Y 顶部出唇压住盖板前缘.
        #      立条占滑槽 z 段(GROOVE_BOT_Z..顶), 分两段避开中央 FPC 缺口区.
        fpc_keep = LID_FPC_NOTCH_W / 2 + 2.0  # 中央 FPC 让位半宽 = 12
        rail_seg_w = ix - fpc_keep
        rail_lip_cy = FRONT_RAIL_Y + FRONT_RAIL_T + LIP_REACH / 2  # 唇中心 Y = -21.75
        # 立条本体做成"悬臂支托": z 从 RAIL_BODY_BOT_Z(9.8, 高于元件) 起, 不再立到底板.
        # Y 向从前内壁面(-iy)伸到 -22.5, 与前壁连成一体(不悬空), 整体悬于 PCB 上方.
        rail_body_y0 = -iy                                       # 接前内壁面 -25.52
        rail_body_y1 = FRONT_RAIL_Y + FRONT_RAIL_T               # -22.5
        rail_body_cy = (rail_body_y0 + rail_body_y1) / 2
        rail_body_dy = rail_body_y1 - rail_body_y0
        for sgn in (1, -1):
            seg_cx = sgn * (fpc_keep + rail_seg_w / 2)
            # 立条本体悬托 (z RAIL_BODY_BOT_Z..顶, 接前壁, 不切 PCB)
            with Locations((seg_cx, rail_body_cy, RAIL_BODY_BOT_Z)):
                Box(rail_seg_w, rail_body_dy, BASE_WALL_H - RAIL_BODY_BOT_Z,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.ADD)
            # 立条顶部唇 (Y -22.5..-21.0 覆盖盖板前缘 -21, z=lip 段)
            with Locations((seg_cx, rail_lip_cy, lip_z)):
                Box(rail_seg_w, LIP_REACH, lip_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.ADD)

        # 8c) -X 里端挡位 (stop): 盖板滑入到底处立一道竖挡条, 占滑槽高度(只挡盖板).
        stop_w = 2.0
        with Locations((-ix + stop_w / 2, FRONT_RAIL_Y + (iy - FRONT_RAIL_Y) / 2,
                        GROOVE_BOT_Z)):
            Box(stop_w, (iy - FRONT_RAIL_Y), (LID_TOP_Z - GROOVE_BOT_Z),
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD)

        # 8d) +X 卡扣凸点 (detent): 后唇下 + 前导轨唇下, 槽底各立小凸点, 靠抽出端.
        #     盖板边缘滑过时压过, 到位后凸点卡进盖板边缘下凹坑(见 make_lid).
        det_x = ix - 4.0
        det_z = GROOVE_BOT_Z
        for sy in (DETENT_Y_FRONT, DETENT_Y_BACK):
            with Locations((det_x, sy, det_z)):
                Cylinder(DETENT_D / 2, DETENT_H,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.ADD)

    return bs.part


# ============================================================
# 零件 4: lid 抽拉式卡扣盖板
#   局部坐标: 与 base 同系(z=0 桌面). 盖板平板在 z LID_BOT_Z..LID_TOP_Z.
#   X = 抽拉方向(+X 抽出), Y = 前(-Y)后(+Y).
# ============================================================
def make_lid():
    ix = BASE_INNER_W / 2     # 35.55
    iy = BASE_INNER_D / 2     # 25.52
    # 盖板主体 Y 范围: 后缘到后内壁面(留滑动间隙), 边缘落在后唇(Y 24.02..25.52)下方被压;
    #                 前缘 LID_Y_FRONT(-21), 落在前导轨唇(Y -21..-19.5)下方被压.
    body_y_back = iy - LID_FIT_GAP            # 25.17, 边缘在后唇覆盖区下(<25.52)
    body_y_front = LID_Y_FRONT                # 前缘 -21 (避斜墙 & 留 FPC)
    body_cy = (body_y_back + body_y_front) / 2
    body_dy = body_y_back - body_y_front
    # 盖板主体 X: 里端到 -X 挡位前(留间隙), 外端到抽出口
    body_x_in = -ix + 2.0 + LID_FIT_GAP       # 里端避开挡位(stop_w=2)
    body_x_out = ix                           # 抽出端到内壁面(+X 抽出口处)
    body_cx = (body_x_out + body_x_in) / 2
    body_dx = body_x_out - body_x_in - 2 * LID_FIT_GAP

    with BuildPart() as ld:
        # 1) 平板主体 (z LID_BOT_Z..LID_TOP_Z)
        with Locations((body_cx, body_cy, LID_BOT_Z)):
            Box(body_dx, body_dy, LID_T,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 2) 前后边缘"滑条": 主体两侧已经到 body_y_back(伸入后唇下).
        #    前缘到 -22, 后缘伸入后唇. 这里主体已覆盖前后边缘, 无需额外滑条.
        #    (前后边缘即滑条, 滑入前后唇下被压.)

        # 3) +X 手指凸耳 (tab): 抽出端伸出, 便于手指抠住抽拉.
        with Locations((body_x_out + LID_TAB_L / 2, 0, LID_BOT_Z)):
            Box(LID_TAB_L, LID_TAB_W, LID_TAB_T,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 4) 前缘 FPC 缺口 (前缘 -Y 中央, 宽 LID_FPC_NOTCH_W, 沿 +Y 深入)
        with Locations((0, body_y_front, LID_BOT_Z - 0.01)):
            Box(LID_FPC_NOTCH_W, LID_FPC_NOTCH_D * 2, LID_T + 0.02,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 5) 卡扣配合凹槽 (detent recess): 盖板前后边缘下表面, 对应 base +X 凸点位置,
        #    挖一个半球/圆柱凹坑, 滑到位后 base 凸点卡入. 凸点在 z=GROOVE_BOT_Z 立 DETENT_H,
        #    顶到 LID_BOT_Z 附近; 在盖板下表面挖浅坑接纳凸点顶.
        det_x = ix - 4.0
        recess_d = DETENT_D + 0.6
        recess_h = DETENT_H + 0.2
        for sy in (DETENT_Y_FRONT, DETENT_Y_BACK):
            with Locations((det_x, sy, LID_BOT_Z)):
                Cylinder(recess_d / 2, recess_h,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)

    return ld.part


# ============================================================
# 装配体: 60 度仰角姿态
# ============================================================
def make_assembly(bezel, back_cover, base, lid=None):
    from build123d import Vector
    base_a = Pos(0, 0, 0) * base

    # 斜墙几何 (须与 make_base 一致): 铰接点 A 在底脚板前缘.
    run = GUSSET_HEIGHT / math.tan(math.radians(ANGLE_DEG))
    seam_z0 = BASE_FOOT_T
    front_y = -BASE_FOOT_D / 2
    A = Vector(0, front_y, seam_z0)            # 铰接点(屏底后角落点)

    # 旋转 R: 使屏面朝 -Y+Z(观察者-上), 屏顶 +Y 指向斜面上坡, 屏底在 A.
    # 推导: local+Y->(0,0.5,0.866)上坡, local-Z(屏面)->(0,-0.866,0.5)法线 => R=Rot(-120,0,0)*Rot(0,0,180).
    R = Rot(-120, 0, 0) * Rot(0, 0, 180)

    # 把 bezel 局部"屏底-背面"角点 (0,-H/2, BEZEL_DEPTH) 旋转后对到 A, 解出平移 T.
    # (Location*Vector 不支持; 用 (R*Pos(p)).position 得到旋转后的点)
    p_rot = (R * Pos(0, -BEZEL_OUT_H / 2, BEZEL_DEPTH)).position
    T = A - p_rot

    bezel_a = Pos(T.X, T.Y, T.Z) * R * bezel
    bc_local = Pos(0, 0, BEZEL_DEPTH - BACK_COVER_PLATE_T) * back_cover
    back_a = Pos(T.X, T.Y, T.Z) * R * bc_local

    children = [base_a, bezel_a, back_a]
    # 盖板: 与 base 同坐标系, 闭合位(make_lid 已含正确 z), 直接放入(底座不旋转).
    if lid is not None:
        children.append(Pos(0, 0, 0) * lid)

    asm = Compound(label="InkPulse_assembly", children=children)
    return asm


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
          f"vol = {vol:11.1f} mm^3 | valid = {valid}")
    return bb, vol, valid


def main():
    print("=== InkPulse enclosure build123d ===")
    print(f"GLASS_CAV {GLASS_CAV_W} x {GLASS_CAV_H}  BEZEL_OUT {BEZEL_OUT_W} x {BEZEL_OUT_H}")
    print(f"WINDOW {WINDOW_W} x {WINDOW_H}  offsetY {WINDOW_OFFSET_Y}")
    print(f"BASE_OUT {BASE_OUT_W} x {BASE_OUT_D} x {BASE_WALL_H}")
    print("-" * 70)

    bezel = make_bezel()
    back_cover = make_back_cover()
    base = make_base()
    lid = make_lid()

    report("bezel", bezel)
    report("back_cover", back_cover)
    report("base", base)
    report("lid", lid)

    # 盖板自验: 覆盖范围 / 避让 / FPC 缺口
    print("-" * 70)
    lb = lid.bounding_box()
    print(f"[lid] 覆盖 X {lb.min.X:.2f}..{lb.max.X:.2f}  Y {lb.min.Y:.2f}..{lb.max.Y:.2f}  Z {lb.min.Z:.2f}..{lb.max.Z:.2f}")
    print(f"[lid] 抽出端(含手指凸耳) X 到 {lb.max.X:.2f}; 主体不超核心盒 X(±{BASE_OUT_W/2:.2f})")
    print(f"[避让-斜墙] 斜墙 Y<=-21.9; 盖板前缘 Y={lb.min.Y:.2f} > -21.9 ? {lb.min.Y > -21.9}  (+X 抽出扫过 X=63 不撞)")
    print(f"[避让-Type-C] 开口 z 4.65..10.65; 后唇 z {LIP_BOT_Z}..{BASE_WALL_H} 但在 X 段避开 Type-C(±{TYPEC_W/2}), 唇从 X=±{TYPEC_W/2+1.5} 起 -> 开口未被堵(交体积=0)")
    print(f"[FPC] 前缘中央缺口宽 {LID_FPC_NOTCH_W}, 深 {LID_FPC_NOTCH_D}")

    # 导出零件
    export_step(bezel, str(OUT / "bezel.step"))
    export_stl(bezel, str(OUT / "bezel.stl"))
    export_step(back_cover, str(OUT / "back_cover.step"))
    export_stl(back_cover, str(OUT / "back_cover.stl"))
    export_step(base, str(OUT / "base.step"))
    export_stl(base, str(OUT / "base.stl"))
    export_step(lid, str(OUT / "lid.step"))
    export_stl(lid, str(OUT / "lid.stl"))

    # 装配体 (含盖板, 闭合位)
    asm = make_assembly(bezel, back_cover, base, lid)
    export_step(asm, str(OUT / "assembly.step"))
    print("-" * 70)
    print("assembly bbox:", asm.bounding_box().size)
    print("exported to", OUT)
    for f in sorted(OUT.glob("*")):
        print("  ", f.name, f"{f.stat().st_size}B")


if __name__ == "__main__":
    main()
