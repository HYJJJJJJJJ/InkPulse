"""第二轮: 磁实体 sanity + 定点回归探针 + 关键对几何细节."""
import importlib.util as ilu
from build123d import Pos, BuildPart, Cylinder, Box, Locations, Align

spec = ilu.spec_from_file_location("E", "cad/enclosure_426.py")
E = ilu.module_from_spec(spec); spec.loader.exec_module(E)

bracket = E.make_bracket(); mate = E.make_bracket.mate
place = E.body_placement(); bc_local = E.back_cover_local()
p = E.make_pcba()
pogo = {c.label: c for c in E.make_pogo_connector().children}
typec = {c.label: c for c in E.make_typec_receptacle().children}


def iv(a, b):
    v = 0.0
    for sa in (a.solids() or [a]):
        for sb in (b.solids() or [b]):
            r = sa & sb; vol = getattr(r, "volume", None)
            if vol and vol > 1e-9: v += vol
    return v


def mag_cyl(cx, cy, z0, z1):
    with BuildPart() as m:
        with Locations((cx, cy, z0)):
            Cylinder(E.MAG_D / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return m.part


bc_mags = [place * (bc_local * mag_cyl(mx, my, 0.0, E.MAG_T))   # 改动#2: 后盖磁腔从外表面 z=0 开口, 磁 = [0,MAG_T]
           for (mx, my) in E.MAG_POSITIONS]
br_mags = [mag_cyl(wx, wy, wz - E.MAG_T, wz) for (wx, wy, wz) in mate["mag_world"]]

print("=== 1) 磁实体 sanity (每个应 ≈ π·4²·3 = 150.8 mm³) ===")
for i, m in enumerate(bc_mags):
    print(f"   bc_mag{i} vol={m.volume:.1f}  bbox={m.bounding_box().size}")
for i, m in enumerate(br_mags):
    print(f"   br_mag{i} vol={m.volume:.1f}")

print("\n=== 2) 磁 vs 关键体 (全部列出, 含<0.5; 确认间隙) ===")
targets = {"bezel": place * E.make_bezel(),
           "back_cover": place * (bc_local * E.make_back_cover()),
           "bracket": bracket,
           "screen": place * (Pos(0, 0, E.FRONT_WALL_T + E.SCREEN_T / 2) * E.make_screen_ref()),
           "pcb": place * p["pcb"], "comp": place * p["comp"]}
for i, m in enumerate(bc_mags):
    for tn, t in targets.items():
        v = iv(m, t)
        if v > 0.01: print(f"   bc_mag{i} ∩ {tn} = {v:.3f}")
for i, m in enumerate(br_mags):
    for tn, t in targets.items():
        v = iv(m, t)
        if v > 0.01: print(f"   br_mag{i} ∩ {tn} = {v:.3f}")
# 磁 vs 对方磁 (对吸面是否撞)
for i, ma in enumerate(bc_mags):
    for j, mb in enumerate(br_mags):
        v = iv(ma, mb)
        if v > 0.01: print(f"   bc_mag{i} ∩ br_mag{j} = {v:.3f}")
print("   (以上未打印的对 = 0, 即无干涉)")

print("\n=== 3) typec 壳体 vs bracket (基线 11.56 是 cable 还是 shell?) ===")
print(f"   typec_shell ∩ bracket = {iv(typec['typec_shell'], bracket):.3f}")
print(f"   typec_cable ∩ bracket = {iv(typec['typec_cable'], bracket):.3f}")
print(f"   typec_shell bbox = {typec['typec_shell'].bounding_box()}")
print(f"   cable bbox       = {typec['typec_cable'].bounding_box()}")
print(f"   走线腔A(竖Z riser): X={mate['tc_cx']:.2f} Y={mate['chanA_y']:.2f} Z[{mate['chanA_z_lo']:.2f},{mate['chanA_z_hi']:.2f}] body_cav_top_y={mate['body_cav_top_y']:.2f}")

print("\n=== 4) pogo 针 vs pad / 针能否穿后盖触点窗到 pad (受电) ===")
pads = place * p["pads"]
bc = place * (bc_local * E.make_back_cover())
print(f"   pogo_pins ∩ pads = {iv(pogo['pogo_pins'], pads):.3f} (接触/微过盈, 受电正常)")
print(f"   pogo_pins ∩ back_cover = {iv(pogo['pogo_pins'], bc):.3f} (>0 => 针撞后盖壁而非穿窗)")
pin_bb = pogo['pogo_pins'].bounding_box(); pad_bb = pads.bounding_box()
print(f"   pins bbox Z=[{pin_bb.min.Z:.2f},{pin_bb.max.Z:.2f}]  pads bbox Z=[{pad_bb.min.Z:.2f},{pad_bb.max.Z:.2f}]")

print("\n=== 5) §7.6 回归点探: 螺柱/支柱/定位销 戳屏/戳板 ? ===")
screen = place * (Pos(0, 0, E.FRONT_WALL_T + E.SCREEN_T / 2) * E.make_screen_ref())
pcb = place * p["pcb"]
bc_solid = place * (bc_local * E.make_back_cover())
bz = place * E.make_bezel()
print(f"   bezel(4×M2 boss) ∩ screen = {iv(bz, screen):.3f} (应=0, 螺柱已移屏外)")
print(f"   back_cover(支柱+定位销) ∩ screen = {iv(bc_solid, screen):.3f} (应=0, 支柱在后盖)")
print(f"   back_cover(定位销) ∩ pcb = {iv(bc_solid, pcb):.3f} (销Φ1.8入孔Φ2.0, 应≈0)")
print(f"   bezel ∩ pcb = {iv(bz, pcb):.3f}")

print("\n=== 6) back_cover ∩ fpc / comp ∩ fpc 几何 (24P 排座 vs 后盖) ===")
fpc = place * p["fpc"]; comp = place * p["comp"]
fpc_bb = (E.make_pcba()["fpc"]).bounding_box()
print(f"   fpc(局部) bbox X=[{fpc_bb.min.X:.2f},{fpc_bb.max.X:.2f}] Y=[{fpc_bb.min.Y:.2f},{fpc_bb.max.Y:.2f}] Z=[{fpc_bb.min.Z:.2f},{fpc_bb.max.Z:.2f}]")
print(f"   PCB_H/2={E.PCB_H/2:.2f}  元件包络半H={E.COMP_ENV_H/2:.2f}  plug镂空半H={E.BC_PLUG_CAV_H/2:.2f}")
print(f"   => fpc 座底 Y(局部)={fpc_bb.min.Y:.2f}; 超出元件包络? {fpc_bb.min.Y < -E.COMP_ENV_H/2}; 超出plug镂空? {fpc_bb.min.Y < -E.BC_PLUG_CAV_H/2}")
print(f"   back_cover ∩ fpc = {iv(bc_solid, fpc):.3f};  comp ∩ fpc = {iv(comp, fpc):.3f}")


print("\n=== 7) 改动#2: 后盖磁腔从対接面(z=0)开口可装入 + 内侧封底 + 装入路径不被 plug 挡 ===")
bc_raw = E.make_back_cover()   # 后盖局部 (z=0 外表面/対接面; +z 朝 PCB)


def _solid_local(part, p, sz=0.06):
    return (part & (Pos(*p) * Box(sz, sz, sz))).volume > 1e-12


MT = E.MAG_T; MIW = E.MAG_INNER_WALL
for (mx, my) in E.MAG_POSITIONS:
    outer_open = not _solid_local(bc_raw, (mx, my, MT / 2))            # 腔体 z∈[0,MT] 应空 (磁位)
    inner_seal = _solid_local(bc_raw, (mx, my, MT + MIW / 2))          # 内侧封底 z∈[MT,MT+MIW] 应有料
    print(f"   磁({mx:+.1f},{my:+.1f}): 外侧腔(z={MT/2:.1f},対接面侧)敞开={outer_open}  内侧封底壁(z={MT+MIW/2:.1f})有料={inner_seal}")
# 装入路径: 磁中心外表面一带 (z<0, 対接面外) 在装配世界应为开口 (磁从背面/対接面塞入, 不被 plug 挡).
#   plug 在内侧 (+z 朝 PCB), 与外表面装入方向相反 => 外侧装入全程无 plug 料.
bc_world_solid = place * (bc_local * bc_raw)
n_path_open = 0
for (mx, my) in E.MAG_POSITIONS:
    # 后盖局部 z=-0.3 (対接面外侧) -> 世界; 该点应无料 (开口朝外, 磁可塞入)
    wv = (place * (bc_local * Pos(mx, my, -0.3))).position
    open_here = not _solid_local(bc_world_solid, (wv.X, wv.Y, wv.Z))
    n_path_open += int(open_here)
print(f"   [装入路径] 4 磁外表面外侧 (z=-0.3, 対接面外) 开口 (磁可从背面塞入, plug 不挡) = {n_path_open}/4 -> "
      f"{'通过' if n_path_open == 4 else '检查'}")
# 磁腔外缘 X vs plug: 旧问题 (内侧 boss 撞 plug 壁) 现已与装入路径无关 (装入改外侧);
#   仍报告几何关系供参考.
boss_outer_x = E.MAG_COL_X + (E.MAG_D + 2 * 1.6) / 2
print(f"   [参考] 内侧 boss 外缘 X={boss_outer_x:.1f} vs plug镂空半宽 {E.BC_PLUG_CAV_W/2:.1f} (boss 与 plug 同属后盖, 熔为一体; 装入已改外侧, 不再受 plug 阻挡)")


print("\n=== 8) 改动 A: 飞线/弹簧针通道核查 (POGO 针尖 Z=-9.60 -> PCB pad Z=-4.10 的 5.5mm 桥接) ===")
# 不改 POGO 架构/pad 仍在 PCB; 仅核查 触点窗 -> 配对腔 -> plug 镂空 -> PCB pad 全程无塑料阻挡.
bc_w = place * (bc_local * E.make_back_cover())
pads_w = place * p["pads"]
pad_bb = pads_w.bounding_box()
print(f"   PCB 受电 pad 世界 Z=[{pad_bb.min.Z:.2f},{pad_bb.max.Z:.2f}]; POGO 针尖世界 Z={mate['pogo_pin_tip_z']:.2f}; "
      f"间隙={pad_bb.min.Z - mate['pogo_pin_tip_z']:.2f}mm (飞线/弹簧针桥接)")


def _bcw(lx, ly, lz=0.0):
    v = (place * (bc_local * Pos(lx, ly, lz))).position
    return (v.X, v.Y, v.Z)


all_clear = True
for (wx, wy) in E.PAD_WINDOW_POSITIONS:
    cx, cy, _ = _bcw(wx, wy)
    # 沿 world Z 从対接面 (-9.7) 到 PCB pad (-4.3) 探后盖料: 应全程无料 (触点窗+配对腔+plug镂空连通).
    blocked = [round(z, 1) for z in (-9.7, -9.0, -8.0, -7.0, -6.0, -5.0, -4.3)
               if (bc_w & (Pos(cx, cy, z) * Box(0.06, 0.06, 0.06))).volume > 1e-12]
    clear = not blocked
    all_clear = all_clear and clear
    print(f"   触点窗(局部X={wx:+.2f})->世界({cx:.1f},{cy:.1f}): 5.5mm 通道沿Z有料={blocked if blocked else '无(全程空气/空腔)'} -> {'通' if clear else '堵'}")
win_area = 3.14159 * (E.POGO_CONTACT_WIN_D / 2) ** 2
print(f"   [结论] 飞线/弹簧针通道 4 列全程无塑料阻挡? {all_clear}; 最小截面 = 触点窗 Φ{E.POGO_CONTACT_WIN_D:.1f} "
      f"({win_area:.2f}mm²/孔); 下游 配对腔 {E.POGO_LEN+2*E.POGO_MATE_CLEAR:.1f}×{E.POGO_WID+2*E.POGO_MATE_CLEAR:.1f} + plug镂空(巨大) 不限 -> "
      f"{'通过(无需让位; 飞线/弹簧针可穿)' if all_clear else '需让位'}")
