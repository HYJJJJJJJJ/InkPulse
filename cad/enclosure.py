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
    Compound, export_step, export_stl, Vector, SlotOverall,
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
CORNER_R = 10.0          # 各件外形四角圆角半径 (美观; <=R12 不碰屏框角立柱)
# 底座/PCB  —— 实测自 hardware/PCB1.step (板中心为原点)
PCB_W = 70.10             # 板 X 向 (沿屏宽/连接器边)
PCB_D = 50.04             # 板 Y 向 (Type-C <-> FPC 方向)
PCB_T = 1.6               # 物理板厚 (STEP简化为0.41, 取实际1.6)
STANDOFF_H = 4.0
HOLE_D = 3.2              # 实测 Φ3.2 (R1.59)
# 安装孔实测 (±30, ±20); Type-C 在 -Y 边中点, FPC 排座在 +Y 边中点
M3_POS_X = 30.0
M3_POS_Y = 20.0
TYPEC_W = 9.6             # 开口宽 (USB-C插头8.34 + 余量; obround圆端长圆形)
TYPEC_H = 3.4             # 开口高 (插头2.56/受口3.16 + 余量; 圆端半径=H/2=1.7; 开口z6.0..9.4)
TYPEC_PORT_Z = STANDOFF_H + 1.7    # 口中心离内底: 螺柱4 + 1.7 = 5.7
# === 核心盒整体前移 (让 ~20mm 短 FPC 够到屏出线点) ===
# 核心盒(PCB仓/螺柱/Type-C壁/FPC缺口)中心沿 -Y 前移到 CORE_CY; 底脚板仍居中(0,0).
CORE_CY = -11.0           # 核心盒中心 Y (前移 11mm, 朝屏/铰接侧)
FPC_CONN_Y = -33.0        # 显示排座 (= CORE_CY - 22, 装配后映射到外壳前侧 -Y, 靠屏)
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
BASE_FOOT_D = 90.0                        # 底脚板深 (抗后倾). 注意: 屏铰接/斜墙 front_y=-45 由此派生, 勿改!
BASE_FOOT_T = 4.0                         # 底脚板厚
# 免螺丝固定: 脚板前缘向 -Y 额外延伸, 托住前挡唇 (不改 BASE_FOOT_D, 保持铰接/斜墙在 -45).
FOOT_FRONT_EXT = 13.5                     # 前缘额外延伸量 -> 前缘 Y=-(90/2+13.5)=-58.5

# PCB M3 螺柱
M3_STANDOFF_D = 6.0
M3_PILOT_D = 2.5                          # M3 自攻底孔
# 螺柱位置实测 (±30, ±20)

# Type-C 口
# 口中心离内底 7.3 => 离底座底面 = BASE_FLOOR_T + 7.3
TYPEC_CENTER_Z = BASE_FLOOR_T + TYPEC_PORT_Z

# 60 度斜墙 (做后撑斜面; 免螺丝设计已取消接缝螺丝)
GUSSET_T = 4.0                            # 斜墙厚
GUSSET_HEIGHT = 40.0                      # 斜墙竖直高 (沿 z)

# === 免螺丝前挡唇 (retaining lip) ===
# 屏框前倾 60°, 前表面底角(0,-52.97,8.6), 前表面外法线(0,-0.866,0.5).
# 在前表面前方留 LIP_FRONT_GAP(垂直间隙)立一道斜唇(内面平行屏前表面), 挡住屏框前倒.
# 中央 X=0 留 ≥20mm 缺口供 FPC 出线; 分左右两段.
LIP_FRONT_GAP = 0.4                       # 唇内面到屏前表面的垂直间隙
LIP_WALL_T = 2.0                          # 唇厚 (沿水平 -Y)
LIP_TOP_Z = 11.5                          # 唇顶高 (高过屏框前底角 8.6 约 2.9mm, 挡得住前倾)
LIP_BOT_Z_R = BASE_FOOT_T                 # 唇底=脚板顶 z=4
LIP_FPC_GAP_HALF = 11.0                   # 中央 FPC 缺口半宽 (=22mm 缺口 >=20)
# 轻卡点 (detent ridge): 唇内面对应屏框处一个小凸棱, 屏框插到底轻轻一扣 (擦过, 静止≈0干涉)
LIP_CLEAT_PROUD = 0.35                    # 卡点凸出量 (擦过级, 不造成大静态干涉)
LIP_CLEAT_Z = 9.5                         # 卡点中心 z (略高于屏前底角 8.6, 屏前表面在此处)
LIP_CLEAT_W = 8.0                         # 卡点沿 X 宽
LIP_CLEAT_D = 2.0                         # 卡点沿 Y 厚 (小凸棱)

# ============================================================
# 零件 4: 抽拉式卡扣盖板 (drawer + snap) 及底座配套导轨/卡扣
# ============================================================
# 设计(v3): 盖板沿 +Y(向后)抽出. 导轨唇在左右侧壁(±X 内壁), 沿 Y 方向贯通;
#       盖板左右边缘滑入唇下被压住. 抽出口在 +Y(后, 开放脚板区), 挡位在 -Y(前)端,
#       卡扣凸点 detent + 手指凸耳在 +Y(后)端. 后壁(含Type-C开口)降低让盖板越过滑出.
# 坐标: 核心盒中心已前移到 CORE_CY; 仓 Y 范围 = [CORE_CY-iy, CORE_CY+iy].
LID_T = 1.5                               # 盖板平板厚 (减薄 2.0->1.5)
LID_FIT_GAP = 0.35                        # 盖板与槽/壁滑动间隙(单边)
INNER_HALF_W = BASE_INNER_W / 2           # 35.55 (左右内壁面 X=±35.55)
INNER_HALF_D = BASE_INNER_D / 2           # 25.52 (前后内壁面 Y=CORE_CY±25.52)
# 仓 Y 内壁面 (随核心盒前移)
POCKET_Y_FRONT = CORE_CY - INNER_HALF_D   # 前内壁面 = -36.52
POCKET_Y_BACK = CORE_CY + INNER_HALF_D    # 后内壁面 = +14.52
# 盖板覆盖 Y 范围: 前缘到前内壁面附近(伸入前唇/挡位区), 后缘到后内壁面(抽出口处).
LID_Y_FRONT = POCKET_Y_FRONT + 2.0 + LID_FIT_GAP    # 前缘抵在前挡条(STOP_T=2.0)的+Y面外, 不再压进挡条
LID_Y_BACK = POCKET_Y_BACK                    # 后缘到后内壁面 (+Y 抽出口处)
# 导轨唇/槽 (在左右 ±X 内壁顶部, 沿 Y 贯通)
LIP_REACH = 1.5                           # 唇向内(沿 X)伸出量
LIP_T = 0.6                               # 唇厚 (z 方向): 盖板顶上方薄薄一层压住盖板顶边
GROOVE_H = 2.5                            # 唇下竖直滑槽高 (槽底到唇底; 盖板坐于其中)
# === 自下而上推导盖板/唇/槽的 Z ===
# 硬约束: 盖板必须在板上元件(顶 z≈9.7)之上滑动. 取盖板底面 LID_BOT_Z=10.25 (净空 9.7 + 0.55 余量).
LID_BOT_Z = 10.6                          # 盖板底面 (> 元件顶 9.7, 留 ~0.9 余量, 放宽紧配合)
LID_TOP_Z = LID_BOT_Z + LID_T             # 11.75 盖板顶面
LID_TOP_GAP = 0.15                        # 盖板顶面与唇底的间隙 (不顶死, 便于滑动)
LIP_BOT_Z = LID_TOP_Z + LID_TOP_GAP       # 11.90 唇底 (压在盖板顶边上方)
# 槽底在盖板底面之下少量 (盖板坐于槽内, 槽底留间隙)
GROOVE_BOT_Z = LID_BOT_Z - 0.25           # 10.00 槽底
# 核心盒外壁顶 = 唇顶 = 唇底 + 唇厚 => 由盖板机构决定
BASE_WALL_H = LIP_BOT_Z + LIP_T           # 12.50 核心盒外壁总高 (轻薄目标 ≈12.5)
BASE_INNER_H = BASE_WALL_H - BASE_FLOOR_T # 10.50 内腔净高 (派生)
CAVITY_CLEAR = BASE_INNER_H               # 兼容旧名 (= 内腔净高)
# 后壁(+Y, 含Type-C开口)降低: 顶部须低于盖板底(10.25), 让盖板从 +Y 越过滑出.
BACK_WALL_H = 10.3                        # +Y 后壁顶 z=10.3 (<盖板底10.6, 盖板可越过; >=Type-C开口顶10.2)
# 盖板主体 Y 长(沿抽拉方向): 前缘到后缘
LID_BODY_D = LID_Y_BACK - LID_Y_FRONT
# 卡扣 detent (在 +Y 抽出端): 侧唇下槽底做小凸点, 盖板边缘下表面做凹坑被咬住
DETENT_D = 2.0                            # 卡扣凸点直径
DETENT_H = 0.8                            # 凸点高
DETENT_Y = LID_Y_BACK - 3.0               # detent Y 靠后(抽出)端, 在盖板边缘下
DETENT_X = INNER_HALF_W - 0.3             # 凸点外移嵌进侧壁(原-1.5悬空0.5mm成独立实体), 仍凸入槽~0.7
# 抽出端(+Y)防滑横条 (取代凸耳: 凸耳与Type-C数据线打架)
# 顶面靠后端印几道沿 X 的凸棱, 大拇指压住向 +Y 推开上盖.
LID_RIDGE_W = 26.0                        # 横条宽(沿 X, 拇指宽)
LID_RIDGE_THK = 1.2                       # 每条沿 Y 厚
LID_RIDGE_PROUD = 0.7                     # 凸出盖板顶面高度
LID_RIDGE_COUNT = 5                       # 条数
LID_RIDGE_PITCH = 2.6                     # 条间距(沿 Y)
# 盖板前缘(-Y) FPC 缺口 (对应新排座 -33, 在盖板前缘中央)
LID_FPC_NOTCH_W = 20.0                    # FPC 缺口宽
LID_FPC_NOTCH_D = 8.0                     # 缺口沿 +Y 深入
# -Y 里端挡位: 滑入到底处 (前内壁顶); +Y 端开放供抽出
STOP_T = 2.0                              # 前挡位厚(沿 Y)

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)


# ============================================================
# 零件 1: bezel 前框
#   局部坐标: 前表面在 z=0 (朝 -z 即朝下打印), 背腔开口朝 +z
#   X = SCREEN_W 方向, Y = SCREEN_H 方向 (向上为 +Y, FPC 在 -Y 底边)
# ============================================================
def make_bezel():
    with BuildPart() as bz:
        # 1) 整体实心托盘块(四角 R 圆角): 从 z=0 到 z=BEZEL_DEPTH
        with BuildSketch(Plane.XY) as _osk:
            Rectangle(BEZEL_OUT_W, BEZEL_OUT_H)
            fillet(_osk.vertices(), radius=CORNER_R)
        extrude(amount=BEZEL_DEPTH)

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
        # 盖板 (与屏框外形齐平, 四角 R 圆角)
        with BuildSketch(Plane.XY) as _bcsk:
            Rectangle(BEZEL_OUT_W, BEZEL_OUT_H)
            fillet(_bcsk.vertices(), radius=CORNER_R)
        extrude(amount=BACK_COVER_PLATE_T)
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

        # boss 让位: 凸台(plate以上)给 bezel 角立柱(Φ5)让 Φ6 空腔, 避免边框顶到立柱;
        # 盖板(z<plate)仍是 Φ2.7 螺丝孔, 盖板坐于立柱顶、螺丝穿入.
        with Locations(
            (BOSS_X, BOSS_Y, BACK_COVER_PLATE_T), (-BOSS_X, BOSS_Y, BACK_COVER_PLATE_T),
            (BOSS_X, -BOSS_Y, BACK_COVER_PLATE_T), (-BOSS_X, -BOSS_Y, BACK_COVER_PLATE_T),
        ):
            Cylinder((BOSS_D + 1.0) / 2, plug_depth + 0.01,
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
        #    后缘缩到与核心盒后壁齐平(+CORE_CY+BASE_OUT_D/2), 让开 Type-C 数据线;
        #    前缘向 -Y 延伸 FOOT_FRONT_EXT 托住前挡唇. (重心在Y≈-16偏前, 缩后缘不影响防倾.)
        foot_back = CORE_CY + BASE_OUT_D / 2            # +17.02, 与PCB盒后壁齐平
        foot_front = -(BASE_FOOT_D / 2 + FOOT_FRONT_EXT)  # -58.5, 托前挡唇
        foot_depth = foot_back - foot_front
        foot_cy = (foot_front + foot_back) / 2
        with BuildSketch(Plane.XY) as _ftsk:
            with Locations((0, foot_cy)):
                Rectangle(BASE_FOOT_W, foot_depth)
            fillet(_ftsk.vertices(), radius=CORNER_R)
        extrude(amount=BASE_FOOT_T)

        # 1) 中央 PCB 核心盒 (实心) 高 BASE_WALL_H, 坐在底脚板上(z=0 起, 与脚板并集)
        #    核心盒整体前移到中心 (0, CORE_CY).
        with Locations((0, CORE_CY, 0)):
            Box(BASE_OUT_W, BASE_OUT_D, BASE_WALL_H,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 1b) 后壁(+Y)降低: 把核心盒后壁顶部削到 BACK_WALL_H (<盖板底), 让盖板从 +Y 越过滑出.
        #     削去 z∈[BACK_WALL_H, BASE_WALL_H] 处, 后壁外侧一段(Y >= 后内壁面).
        back_wall_y_in = CORE_CY + BASE_INNER_D / 2   # 后内壁面 = POCKET_Y_BACK
        with Locations((0, CORE_CY + BASE_OUT_D / 2, BACK_WALL_H)):
            Box(BASE_OUT_W + 0.02, BASE_WALL * 2 + 0.02,
                (BASE_WALL_H - BACK_WALL_H) + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 2) 挖内腔 (从顶面向下挖, 留底板) — 随核心盒前移
        with Locations((0, CORE_CY, BASE_FLOOR_T)):
            Box(BASE_INNER_W, BASE_INNER_D, BASE_INNER_H + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 3) 四角 M3 PCB 螺柱 (±30, CORE_CY±20)=(±30,+9),(±30,-31), 柱高=STANDOFF_H
        for sx in (M3_POS_X, -M3_POS_X):
            for sy in (CORE_CY + M3_POS_Y, CORE_CY - M3_POS_Y):
                with Locations((sx, sy, BASE_FLOOR_T)):
                    Cylinder(M3_STANDOFF_D / 2, STANDOFF_H,
                             align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 螺柱自攻底孔
        for sx in (M3_POS_X, -M3_POS_X):
            for sy in (CORE_CY + M3_POS_Y, CORE_CY - M3_POS_Y):
                with Locations((sx, sy, BASE_FLOOR_T + STANDOFF_H)):
                    Cylinder(M3_PILOT_D / 2, STANDOFF_H - 0.5,
                             align=(Align.CENTER, Align.CENTER, Align.MAX),
                             mode=Mode.SUBTRACT)

        # 4) 后壁 Type-C 开口 (后壁在 +Y 侧): USB-C 圆端长圆形(obround), 非方孔.
        #    在后壁所在的 X-Z 平面画 SlotOverall(宽 TYPEC_W, 高 TYPEC_H, 圆端 r=TYPEC_H/2), 沿 Y 穿透.
        wall_y = CORE_CY + BASE_OUT_D / 2
        tc_plane = Plane(origin=(0, wall_y, TYPEC_CENTER_Z), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        with BuildSketch(tc_plane):
            SlotOverall(TYPEC_W, TYPEC_H)
        extrude(amount=BASE_WALL * 2, both=True, mode=Mode.SUBTRACT)
        # 内侧加宽让位(counterbore): 连接器壳体~11.3宽、前端伸入壁内~1.15mm,
        #   内侧挖宽腔避让, 外侧保持贴合 obround(可见端口).
        inner_y = wall_y - BASE_WALL
        relief_w, relief_h, relief_depth = 12.0, 4.4, 1.8
        with Locations((0, inner_y + relief_depth / 2, TYPEC_CENTER_Z)):
            Box(relief_w, relief_depth + 0.02, relief_h,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT)

        # 5) 前壁(-Y) FPC 进线缺口: 对位排座 (0, FPC_CONN_Y=CORE_CY-22), 在前内壁顶沿开槽
        front_wall_y = CORE_CY - BASE_OUT_D / 2
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

        # 7) 免螺丝前挡唇 (retaining lip): 已取消接缝 M3 螺丝.
        #    屏框前倾时前表面抵住此唇内斜面(60°), 防倒出; 配合斜墙后撑 + 重力自稳.
        #    分左右两段, 中央 X=0 留 2*LIP_FPC_GAP_HALF 缺口给 FPC.
        #    在 Plane.YZ 上画唇横截面多边形(内面平行屏前表面, 60°), 沿 X 拉伸.
        #    屏前表面线: 过(Y,Z)=(-52.9674, 8.6), 方向(0.5,0.866)归一; 斜率 dY/dZ=0.57735.
        def _front_y_at(z):    # 屏框前表面在 world z 处的 Y
            return -52.9674 + 0.57735 * (z - 8.6)
        # 唇内面 = 屏前表面沿外法线(0,-0.866,0.5)偏移 LIP_FRONT_GAP
        ny, nz = -0.866025, 0.5
        def _lip_inner_y(z):   # 唇内面在 world z 处的 Y
            return _front_y_at(z - LIP_FRONT_GAP * nz) + LIP_FRONT_GAP * ny
        lip_z0 = LIP_BOT_Z_R
        lip_z1 = LIP_TOP_Z
        # 改为竖直唇内面: 取屏前最靠前点(底角 Y=-52.9674)前方 LIP_FRONT_GAP.
        # 屏前表面随 z 上升向后退, 故竖直唇恒在其前方, 绝不重叠(原60°斜唇上部会插进屏框).
        lip_in_y = -52.9674 - LIP_FRONT_GAP
        in_bot = (lip_in_y, lip_z0)                            # 内面底(竖直)
        in_top = (lip_in_y, lip_z1)                            # 内面顶(竖直)
        out_top = (lip_in_y - LIP_WALL_T, lip_z1)             # 外面顶
        out_bot = (lip_in_y - LIP_WALL_T, lip_z0)             # 外面底
        # 唇沿 X 分两段, 各段中心与半宽
        seg_x_in = LIP_FPC_GAP_HALF                            # 缺口内沿
        seg_x_out = BASE_FOOT_W / 2 - 4.0                      # 唇外端 (略收进脚板边)
        seg_w = seg_x_out - seg_x_in
        seg_cx = (seg_x_in + seg_x_out) / 2
        from build123d import Polygon
        for sgn in (1, -1):
            with BuildSketch(Plane.YZ.offset(sgn * seg_x_in)) as lsk:
                Polygon(in_bot, in_top, out_top, out_bot, align=None)
            # Plane.YZ 法线为 +X; 从缺口内沿(±seg_x_in)向外侧拉伸 seg_w (sgn 决定方向)
            extrude(amount=sgn * seg_w, mode=Mode.ADD)

        # 8) 轻卡点 (cleat): 唇内斜面对应屏框处加小凸棱, 凸向屏前表面(+Y 内法线方向).
        #    屏框插到底擦过/轻扣; 静止时仅 just-touching, 不造成大静态干涉.
        #    放在左右唇段内侧, 凸出 LIP_CLEAT_PROUD 朝屏前表面.
        # 卡点从竖直唇内面水平凸向屏(+Y), 前面刚好擦到屏前表面(在 LIP_CLEAT_Z 处), 留 0.05 间隙.
        frame_front_at_cleat = -52.9674 + 0.57735 * (LIP_CLEAT_Z - 8.6)
        cl_cy = frame_front_at_cleat - LIP_CLEAT_D / 2 - 0.05
        cl_cz = LIP_CLEAT_Z
        for sgn in (1, -1):
            cl_x = sgn * (seg_x_in + 6.0)   # 卡点靠近缺口内侧, 在唇段上
            with Locations((cl_x, cl_cy, cl_cz)):
                Box(LIP_CLEAT_W, LIP_CLEAT_D, LIP_CLEAT_D,
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.ADD)

        # ====================================================
        # 8) 抽拉盖板配套(v3, 沿+Y抽出): 左右侧壁(±X)导轨唇沿Y贯通 + +Y抽出口
        #    + -Y 挡位 + +Y 卡扣凸点. 盖板左右边缘滑入侧唇下.
        # ====================================================
        ix = BASE_INNER_W / 2     # 左右内壁 X 面 = ±35.55
        # 仓 Y 内壁面 (随核心盒前移)
        y_front = POCKET_Y_FRONT  # 前内壁面 -36.52
        y_back = POCKET_Y_BACK    # 后内壁面 +14.52
        lip_z = LIP_BOT_Z
        lip_h = BASE_WALL_H - LIP_BOT_Z       # 0.6

        # 8a) +Y 抽出口本由 (1b) 削低后壁实现: 后壁顶=BACK_WALL_H(10.0)<盖板底(10.25),
        #     盖板可直接从后方越过后壁滑出. 此外把后内壁面以后(Y>y_back)的滑槽段也清空,
        #     确保盖板边缘(在侧唇下)抽出路径无阻 — 但侧唇本身止于 y_back 之前(见 8b).

        # 8b) 左右(±X)侧壁顶部导轨唇 (lip): 内面 X=±ix, 向内伸 LIP_REACH, z=LIP_BOT_Z..顶,
        #     沿 Y 从 y_front 贯通到 y_back(后内壁), 压住盖板左右边缘上方.
        for sgn in (1, -1):
            cx = sgn * (ix - LIP_REACH / 2)
            cy = (y_front + y_back) / 2
            dy = y_back - y_front
            with Locations((cx, cy, lip_z)):
                Box(LIP_REACH, dy, lip_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.ADD)

        # 8c) -Y 里端挡位 (stop): 盖板滑入到底处, 沿 X 立一道竖挡条(占滑槽高度, 只挡盖板).
        #     避开中央 FPC 进线缺口区(中央留空让 FPC 过).
        fpc_keep = LID_FPC_NOTCH_W / 2 + 2.0  # 中央 FPC 让位半宽 = 12
        stop_seg_w = ix - fpc_keep
        for sgn in (1, -1):
            seg_cx = sgn * (fpc_keep + stop_seg_w / 2)
            with Locations((seg_cx, y_front + STOP_T / 2, GROOVE_BOT_Z)):
                Box(stop_seg_w, STOP_T, (LID_TOP_Z - GROOVE_BOT_Z),
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.ADD)

        # 8d) +Y 卡扣凸点 (detent): 左右侧唇下槽底, 靠抽出(+Y)端各立小凸点.
        #     盖板边缘滑过压过, 到位后卡进盖板边缘下凹坑(见 make_lid).
        for sx in (DETENT_X, -DETENT_X):
            with Locations((sx, DETENT_Y, GROOVE_BOT_Z)):
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
    # 盖板主体 X 范围: 左右边缘伸入侧唇(X ±34.05..±35.55)下方被压, 留滑动间隙.
    body_x_half = ix - LID_FIT_GAP            # 35.20, 边缘在侧唇覆盖区下(<35.55)
    # 盖板主体 Y 范围(沿抽拉方向): 前缘抵 -Y 挡位(留间隙), 后缘到后内壁面(+Y 抽出口处).
    body_y_front = LID_Y_FRONT                # 前缘 -36.17 (抵前挡位)
    body_y_back = LID_Y_BACK                  # 后缘 +14.52 (后内壁面/抽出口)
    body_cy = (body_y_back + body_y_front) / 2
    body_dy = body_y_back - body_y_front

    with BuildPart() as ld:
        # 1) 平板主体 (z LID_BOT_Z..LID_TOP_Z)
        with Locations((0, body_cy, LID_BOT_Z)):
            Box(body_x_half * 2, body_dy, LID_T,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 2) 左右边缘即滑条: 主体两侧 X 已到 ±body_x_half(伸入侧唇下被压). 无需额外滑条.

        # 3) 防滑横条 (取代凸耳): 顶面靠 +Y(后)端印几道沿 X 凸棱, 拇指压住推开.
        #    凸棱凸出盖板顶面 LID_RIDGE_PROUD; 居中 X, 不伸出后缘(不碰 Type-C 数据线).
        ridge_y0 = body_y_back - 2.0    # 最后一条距后缘 2mm
        for i in range(LID_RIDGE_COUNT):
            ry = ridge_y0 - i * LID_RIDGE_PITCH
            with Locations((0, ry, LID_TOP_Z)):
                Box(LID_RIDGE_W, LID_RIDGE_THK, LID_RIDGE_PROUD,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 4) 前缘(-Y) FPC 缺口 (中央, 宽 LID_FPC_NOTCH_W, 沿 +Y 深入, 对应排座 -33)
        with Locations((0, body_y_front, LID_BOT_Z - 0.01)):
            Box(LID_FPC_NOTCH_W, LID_FPC_NOTCH_D * 2, LID_T + 0.02,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 5) 卡扣配合凹槽 (detent recess): 盖板左右边缘下表面, 对应 base +Y 凸点位置,
        #    挖圆柱凹坑, 滑到位后 base 凸点卡入.
        recess_d = DETENT_D + 0.6
        recess_h = DETENT_H + 0.2
        for sx in (DETENT_X, -DETENT_X):
            with Locations((sx, DETENT_Y, LID_BOT_Z)):
                Cylinder(recess_d / 2, recess_h,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)

    return ld.part


# ============================================================
# 装配体: 60 度仰角姿态
# ============================================================
def make_assembly(bezel, back_cover, base, lid=None, pcb=None):
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

    # 靠斜墙的是"后盖外表面"(在 bezel 局部 z = BEZEL_DEPTH+BACK_COVER_PLATE_T).
    # 把该外表面的屏底角点对到斜墙铰接点 A, 解出平移 T (整体比仅bezel外移一个后盖厚).
    p_rot = (R * Pos(0, -BEZEL_OUT_H / 2, BEZEL_DEPTH + BACK_COVER_PLATE_T)).position
    T = A - p_rot

    bezel_a = Pos(T.X, T.Y, T.Z) * R * bezel
    # 后盖须翻转(绕Y转180)使凸台朝 -z 插入背腔; 盖板(外侧)贴屏框背面外, 凸台伸到泡棉处.
    # 翻转后平移 +z 到 BEZEL_DEPTH+PLATE: 盖板占[7.2,9.2](背面外), 凸台占[3.95,7.2](腔内压泡棉).
    bc_local = Pos(0, 0, BEZEL_DEPTH + BACK_COVER_PLATE_T) * Rot(0, 180, 0) * back_cover
    back_a = Pos(T.X, T.Y, T.Z) * R * bc_local

    children = [base_a, bezel_a, back_a]
    # 盖板: 与 base 同坐标系, 闭合位(make_lid 已含正确 z), 直接放入(底座不旋转).
    if lid is not None:
        children.append(Pos(0, 0, 0) * lid)
    # 真实 PCB (已按装配姿态放好的 located shape): 直接并入预览.
    if pcb is not None:
        children.append(pcb)

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

    # 实体数 (各应=1, 无悬空件)
    print("-" * 70)
    for nm, pt in (("bezel", bezel), ("back_cover", back_cover), ("base", base), ("lid", lid)):
        print(f"[solids] {nm:12s} = {len(pt.solids())}")
    # 前挡唇有效性: 唇内面 Y vs 屏框前表面 Y(-53)
    def _front_y_at(z):
        return -52.9674 + 0.57735 * (z - 8.6)
    ny, nz = -0.866025, 0.5
    def _lip_inner_y(z):
        return _front_y_at(z - LIP_FRONT_GAP * nz) + LIP_FRONT_GAP * ny
    print("-" * 70)
    print(f"[前挡唇] 唇顶 z={LIP_TOP_Z} (>屏前底角 z8.6 约 {LIP_TOP_Z-8.6:.1f}mm)")
    for z in (4.0, 8.6, 11.0):
        print(f"   z={z:5.1f}: 唇内面 Y={_lip_inner_y(z):7.3f}  屏前表面 Y={_front_y_at(z):7.3f}  "
              f"间隙={_front_y_at(z)-_lip_inner_y(z):.3f}mm (唇在屏前方)")

    # 盖板自验: 覆盖范围 / 避让 / FPC 缺口
    print("-" * 70)
    lb = lid.bounding_box()
    print(f"[lid] 覆盖 X {lb.min.X:.2f}..{lb.max.X:.2f}  Y {lb.min.Y:.2f}..{lb.max.Y:.2f}  Z {lb.min.Z:.2f}..{lb.max.Z:.2f}")
    print(f"[lid] 抽出端(+Y, 顶面防滑横条) Y 到 {lb.max.Y:.2f}; 主体不超核心盒 X(±{BASE_OUT_W/2:.2f})")
    print(f"[抽拉] 沿 +Y(向后)抽出; 仓 Y [{POCKET_Y_FRONT:.2f}..{POCKET_Y_BACK:.2f}] (核心盒中心 CORE_CY={CORE_CY})")
    print(f"[后抽可行] 后壁顶 z={BACK_WALL_H} < 盖板底 z={LID_BOT_Z} ? {BACK_WALL_H < LID_BOT_Z}")
    print(f"[避让-Type-C] 开口 z {TYPEC_CENTER_Z-TYPEC_H/2:.2f}..{TYPEC_CENTER_Z+TYPEC_H/2:.2f}; 顶 < 盖板底 {LID_BOT_Z} ? {TYPEC_CENTER_Z+TYPEC_H/2 < LID_BOT_Z}")
    print(f"[FPC] 前缘(-Y)中央缺口宽 {LID_FPC_NOTCH_W}, 深 {LID_FPC_NOTCH_D}; 排座 Y={FPC_CONN_Y}")

    # 导出零件
    export_step(bezel, str(OUT / "bezel.step"))
    export_stl(bezel, str(OUT / "bezel.stl"))
    export_step(back_cover, str(OUT / "back_cover.step"))
    export_stl(back_cover, str(OUT / "back_cover.stl"))
    export_step(base, str(OUT / "base.step"))
    export_stl(base, str(OUT / "base.stl"))
    export_step(lid, str(OUT / "lid.step"))
    export_stl(lid, str(OUT / "lid.stl"))

    # 把真实 PCB 组进装配预览: 重定心->绕Z翻180(Type-C朝+Y)->抬到螺柱顶->移到 CORE_CY
    pcb_placed = None
    pcb_path = Path(__file__).resolve().parent.parent / "hardware" / "PCB1.step"
    if pcb_path.exists():
        from build123d import import_step
        _pcb = import_step(str(pcb_path))
        _bd = max((s for s in _pcb.solids() if s.bounding_box().size.Z < 3),
                  key=lambda s: s.bounding_box().size.X * s.bounding_box().size.Y)
        _b = _bd.bounding_box()
        _ox, _oy, _oz = (_b.min.X + _b.max.X) / 2, (_b.min.Y + _b.max.Y) / 2, _b.min.Z
        pcb_placed = (Pos(0, CORE_CY, BASE_FLOOR_T + STANDOFF_H)
                      * Rot(0, 0, 180) * Pos(-_ox, -_oy, -_oz)) * _pcb
        print(f"[pcb] 已组入装配预览 (中心->CORE_CY={CORE_CY}, 翻转使Type-C朝+Y, 坐螺柱顶)")

    # 装配体 (含盖板 + 真实PCB, 闭合位)
    asm = make_assembly(bezel, back_cover, base, lid, pcb=pcb_placed)
    export_step(asm, str(OUT / "assembly.step"))
    print("-" * 70)
    print("assembly bbox:", asm.bounding_box().size)
    print("exported to", OUT)
    for f in sorted(OUT.glob("*")):
        print("  ", f.name, f"{f.stat().st_size}B")


if __name__ == "__main__":
    main()
