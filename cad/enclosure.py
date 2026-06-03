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
# 底座/PCB
PCB = 50.0
PCB_T = 1.6
STANDOFF_H = 4.0
HOLE_D = 3.2
HOLE_INSET = 4.0           # (备用) PCB 安装孔从板边内缩
TYPEC_W = 10.0
TYPEC_H = 4.0
TYPEC_PORT_Z = 7.3
FPC_CONN_Y = -22.0
CAVITY_CLEAR = 15.0

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

# bezel 总深 (前壁 + 玻璃腔 + 泡棉 + 后盖嵌入)
# 设计目标整体深度 ~18-20mm: 前面板 + 较深托盘背腔(容玻璃/泡棉/后盖凸台并提供刚性)
FRONT_WALL_T = LIP + 1.0                  # 视窗处前面板厚 (唇 + 余量) = 2.2
BACK_LIP_DEPTH = 17.0                     # 背面托盘腔深度
BEZEL_DEPTH = FRONT_WALL_T + BACK_LIP_DEPTH   # ~19.2 mm

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

# 底座 (楔形)
BASE_INNER_W = PCB + 2 * 0.5              # 50 + 1.0 = 51.0 (四周 0.5 间隙)
BASE_INNER_D = PCB + 2 * 0.5             # 沿 Y 方向同
BASE_WALL = WALL
BASE_FLOOR_T = 2.0
BASE_OUT_W = BASE_INNER_W + 2 * BASE_WALL    # 56.0 量级
BASE_OUT_D = BASE_INNER_D + 2 * BASE_WALL    # 56.0 量级
BASE_INNER_H = CAVITY_CLEAR              # 内腔净高 15
BASE_WALL_H = BASE_FLOOR_T + BASE_INNER_H    # 外壁总高 17

# PCB M3 螺柱
M3_STANDOFF_D = 6.0
M3_PILOT_D = 2.5                          # M3 自攻底孔
M3_POS = 21.0                             # (±21, ±21)

# Type-C 口
# 口中心离内底 7.3 => 离底座底面 = BASE_FLOOR_T + 7.3
TYPEC_CENTER_Z = BASE_FLOOR_T + TYPEC_PORT_Z

# 60 度斜墙 / 接缝
GUSSET_T = 4.0                            # 斜墙厚
GUSSET_HEIGHT = 40.0                      # 斜墙竖直高 (沿 z)
M3_SEAM_D = 3.4                           # 接缝 M3 通孔
SEAM_SCREW_SPACING = 60.0                 # 两颗接缝螺丝水平间距

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
        # 1) 外盒 (实心) 高 BASE_WALL_H
        Box(BASE_OUT_W, BASE_OUT_D, BASE_WALL_H,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 2) 挖内腔 (从顶面向下挖, 留底板)
        with Locations((0, 0, BASE_FLOOR_T)):
            Box(BASE_INNER_W, BASE_INNER_D, BASE_INNER_H + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT)

        # 3) 四角 M3 PCB 螺柱 (±21, ±21), 柱高 = STANDOFF_H, 从内底升起
        for sx in (M3_POS, -M3_POS):
            for sy in (M3_POS, -M3_POS):
                with Locations((sx, sy, BASE_FLOOR_T)):
                    Cylinder(M3_STANDOFF_D / 2, STANDOFF_H,
                             align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 螺柱自攻底孔
        for sx in (M3_POS, -M3_POS):
            for sy in (M3_POS, -M3_POS):
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
        gx = BASE_OUT_W / 2 - GUSSET_T / 2
        seam_z0 = BASE_WALL_H
        front_y = -BASE_OUT_D / 2
        # 安装面(斜边 B->C)与水平夹角 a 满足 tan(a)=GUSSET_HEIGHT/run.
        # 要 a=ANGLE_DEG(60度) => run = 竖直高 / tan(60). 斜面法线 nz=cos(60)=0.5,
        # 校验用 a=arccos(|nz|). (前两版分别误用 1/tan 与 tan, 此为正解.)
        run = GUSSET_HEIGHT / math.tan(math.radians(ANGLE_DEG))  # 水平投影
        for sx in (gx, -gx):
            with BuildSketch(Plane.YZ.offset(sx)) as sk:
                # 注意: Plane.YZ 局部坐标 (u=全局Y, v=全局Z), 但 +X 法线方向.
                Polygon(
                    (front_y, seam_z0),
                    (front_y + run, seam_z0),
                    (front_y, seam_z0 + GUSSET_HEIGHT),
                    align=None,
                )
            extrude(amount=GUSSET_T / 2, both=True, mode=Mode.ADD)

        # 7) 接缝 M3 横穿螺丝孔 (沿 Y 方向横穿两片斜墙), 两颗位于斜墙中部.
        #    放在斜面中点附近, 沿 +Y 钻穿.
        seam_hole_z = seam_z0 + GUSSET_HEIGHT * 0.45
        seam_hole_y = front_y + run * 0.35
        for sx in (gx, -gx):
            with Locations(Pos(sx, seam_hole_y, seam_hole_z) * Rot(90, 0, 0)):
                Cylinder(M3_SEAM_D / 2, GUSSET_T * 3,
                         align=(Align.CENTER, Align.CENTER, Align.CENTER),
                         mode=Mode.SUBTRACT)

    return bs.part


# ============================================================
# 装配体: 60 度仰角姿态
# ============================================================
def make_assembly(bezel, back_cover, base):
    # base 平放, z=0 桌面 (局部坐标已是)
    base_a = Pos(0, 0, 0) * base

    # bezel: 屏面与水平成 60 度, 背面贴靠斜墙. 背腔朝下(向斜墙).
    # bezel 局部: 前面 z=0, 背面 z=BEZEL_DEPTH, +Y 向上(屏顶).
    # 目标: 绕 X 轴旋转, 使屏面法线(+z) 与水平成 60 度.
    # 斜墙安装面在 base 顶 -Y 侧后倾. bezel 背面贴上去.
    tilt = ANGLE_DEG  # 屏面仰角
    # 绕 X 旋转 -tilt: 使屏面(局部 -Z 外法线)与水平成 tilt=60 度仰角.
    # (修正: 此前用 -(90-tilt)=-30 度, 屏只立到 30 度)
    rot = Rot(-tilt, 0, 0)
    # 抬升到斜墙位置: 放在 base 顶 -Y 侧上方
    lift_z = BASE_WALL_H + 10
    shift_y = -BASE_OUT_D / 2 + 5
    bezel_a = Pos(0, shift_y, lift_z) * rot * bezel

    # back_cover 贴 bezel 背面 (沿 bezel 局部 +z 偏移 BEZEL_DEPTH)
    bc_local = Pos(0, 0, BEZEL_DEPTH - BACK_COVER_PLATE_T) * back_cover
    back_a = Pos(0, shift_y, lift_z) * rot * bc_local

    asm = Compound(label="InkPulse_assembly",
                   children=[base_a, bezel_a, back_a])
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

    report("bezel", bezel)
    report("back_cover", back_cover)
    report("base", base)

    # 导出零件
    export_step(bezel, str(OUT / "bezel.step"))
    export_stl(bezel, str(OUT / "bezel.stl"))
    export_step(back_cover, str(OUT / "back_cover.step"))
    export_stl(back_cover, str(OUT / "back_cover.stl"))
    export_step(base, str(OUT / "base.step"))
    export_stl(base, str(OUT / "base.stl"))

    # 装配体
    asm = make_assembly(bezel, back_cover, base)
    export_step(asm, str(OUT / "assembly.step"))
    print("-" * 70)
    print("assembly bbox:", asm.bounding_box().size)
    print("exported to", OUT)
    for f in sorted(OUT.glob("*")):
        print("  ", f.name, f"{f.stat().st_size}B")


if __name__ == "__main__":
    main()
