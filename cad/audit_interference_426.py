"""InkPulse 4.26" 外壳 — 独立实体干涉审计 (只审计, 不改模型).

实现交接文档 §4 的"内存单实体相交"配方 + §3 要求补建的实体:
  - 8×Φ8×3 磁铁 (后盖 4 + 支架 4): 在各自宿主局部系按真实腔位建圆柱, 再施加同一装配变换.
  - POGO 4 弹针 / N/S 磁: 从 make_pogo_connector() 的 Compound 子件拆出单列.
穷举所有实体两两干涉矩阵; 对每个 >阈值 的对给 体积 + 相交区 bbox; 关键点探.

运行: 仓库根 + conda env cad: python cad/audit_interference_426.py
"""
import importlib.util as ilu
from build123d import Pos, Rot, BuildPart, Cylinder, Box, Locations, Align

# ---- 载入建模源 ----
spec = ilu.spec_from_file_location("E", "cad/enclosure_426.py")
E = ilu.module_from_spec(spec)
spec.loader.exec_module(E)

# ---- §4 复现 world 放置 ----
bracket = E.make_bracket()                       # 必先调用以填 make_bracket.mate
mate = E.make_bracket.mate
place = E.body_placement()
bc_local = E.back_cover_local()
p = E.make_pcba()

# POGO 连接器拆子件 (本体/磁/针 分列)
pogo_cmp = E.make_pogo_connector()
pogo_children = {c.label: c for c in pogo_cmp.children}
typec_cmp = E.make_typec_receptacle()
typec_children = {c.label: c for c in typec_cmp.children}


def _mag_cyl(cx, cy, z0, z1):
    """在指定局部系建一个 Φ8 磁柱实体 (z0..z1)."""
    with BuildPart() as m:
        with Locations((cx, cy, z0)):
            Cylinder(E.MAG_D / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return m.part


# ---- §3: 补建 8 磁实体 ----
# 后盖 4 磁 (改动#2): back_cover 局部腔从外表面 z=0 开口, 磁体 = [0, MAG_T]; 经 place*bc_local 入世界.
bc_mag_solids = {}
for i, (mx, my) in enumerate(E.MAG_POSITIONS):
    mloc = _mag_cyl(mx, my, 0.0, E.MAG_T)
    bc_mag_solids[f"bc_mag{i}"] = place * (bc_local * mloc)
# 支架 4 磁: 世界腔 = [z_top - MAG_T, z_top] (从对接面顶向 -Z 沉, 留 -Z 外侧薄壁).
br_mag_solids = {}
for i, (wx, wy, wz) in enumerate(mate["mag_world"]):
    mloc = _mag_cyl(wx, wy, wz - E.MAG_T, wz)
    br_mag_solids[f"br_mag{i}"] = mloc

# ---- 组装实体字典 ----
B = {
    "bezel":      place * E.make_bezel(),
    "back_cover": place * (bc_local * E.make_back_cover()),
    "bracket":    bracket,
    "screen":     place * (Pos(0, 0, E.FRONT_WALL_T + E.SCREEN_T / 2) * E.make_screen_ref()),
    "pcb":   place * p["pcb"],
    "comp":  place * p["comp"],
    "pads":  place * p["pads"],
    "fpc":   place * p["fpc"],
    "pogo_body": pogo_children["pogo_body"],
    "pogo_mag":  pogo_children["pogo_magnets"],
    "pogo_pins": pogo_children["pogo_pins"],
    "typec":     typec_children["typec_shell"],
    "typec_cable": typec_children["typec_cable"],
    "monitor":   E.make_monitor_corner(),
}
B.update(bc_mag_solids)
B.update(br_mag_solids)


def iv(a, b):
    """稳健: 分解到单实体两两求交, 返回 (总体积, 相交区 bbox)."""
    v = 0.0
    bbmin = [1e9, 1e9, 1e9]
    bbmax = [-1e9, -1e9, -1e9]
    for sa in (a.solids() or [a]):
        for sb in (b.solids() or [b]):
            r = sa & sb
            vol = getattr(r, "volume", None)
            if vol and vol > 1e-9:
                v += vol
                bb = r.bounding_box()
                bbmin = [min(bbmin[0], bb.min.X), min(bbmin[1], bb.min.Y), min(bbmin[2], bb.min.Z)]
                bbmax = [max(bbmax[0], bb.max.X), max(bbmax[1], bb.max.Y), max(bbmax[2], bb.max.Z)]
    if v <= 1e-9:
        return 0.0, None
    return v, (bbmin, bbmax)


# 不报警的"设计配合"对 (内部凸台插腔 / 同一连接器内部子件 / 磁在自身腔内)
SKIP_PAIRS = {
    frozenset({"bezel", "back_cover"}),         # 屏体凸台插腔
    frozenset({"pogo_body", "pogo_pins"}),      # 同一连接器内部
    frozenset({"pogo_body", "pogo_mag"}),
    frozenset({"pogo_mag", "pogo_pins"}),
    frozenset({"typec", "typec_cable"}),
}

names = list(B.keys())
THRESH = 0.5
rows = []
print("=" * 100)
print(f"全实体两两干涉矩阵 (内存单实体相交, >{THRESH} mm³). 实体数={len(names)}")
print("=" * 100)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        n1, n2 = names[i], names[j]
        try:
            v, bb = iv(B[n1], B[n2])
        except Exception as e:
            print(f"  ERR {n1} ∩ {n2}: {e}")
            continue
        if v > THRESH:
            skip = frozenset({n1, n2}) in SKIP_PAIRS
            rows.append((v, n1, n2, bb, skip))

rows.sort(reverse=True)
for v, n1, n2, bb, skip in rows:
    tag = " [设计配合-忽略]" if skip else ""
    if bb:
        (x0, y0, z0), (x1, y1, z1) = bb
        bbs = f" bbox X[{x0:.2f},{x1:.2f}] Y[{y0:.2f},{y1:.2f}] Z[{z0:.2f},{z1:.2f}]"
    else:
        bbs = ""
    print(f"  {v:9.3f}  {n1:12s} ∩ {n2:12s}{tag}{bbs}")

print("\n" + "=" * 100)
print("关键点探 (§3 ⚠️ + §7.6 回归)")
print("=" * 100)


def probe(part, pt, name):
    """点探: 在 pt 处放一个 0.06 立方测试体, 与 part 求交>0 => 该点有料."""
    with BuildPart() as t:
        with Locations(pt):
            Box(0.06, 0.06, 0.06)
    r = part & t.part
    has = getattr(r, "volume", 0.0) or 0.0
    print(f"   [{name}] @{tuple(round(c,2) for c in pt)} 有料={has>1e-12}")
    return has > 1e-12


# 屏 AA 体 (世界): 用于"任何实体侵入 AA"检查
aa_local = Pos(0, E.WINDOW_OFFSET_Y, E.FRONT_WALL_T + E.SCREEN_T / 2)
with BuildPart() as _aa:
    with Locations((0, E.WINDOW_OFFSET_Y, E.FRONT_WALL_T)):
        Box(E.AA_W, E.AA_H, E.SCREEN_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
aa_world = place * _aa.part

# 唇是否遮挡 AA: bezel ∩ AA 体
v_lip_aa, bb = iv(B["bezel"], aa_world)
print(f"   bezel(唇) ∩ AA 体 = {v_lip_aa:.3f} mm³ (>0 => 唇侵入 AA 视窗, 遮挡画面)")

# 磁能否装入 / 磁 vs 各体 已在矩阵; 这里补磁柱 boss 是否封死(装入面应敞开)
print("   (磁实体 vs PCB/元件/屏/对方磁/走线腔 见上矩阵; pogo针 vs pad 见上矩阵)")
