"""把 4.26" 三件 + 装配体渲染成一张 preview_426.png (matplotlib 正交多视图)。"""
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Hiragino Sans GB",
                                          "Songti SC", "STHeiti"]
matplotlib.rcParams["axes.unicode_minus"] = False
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

OUT = "cad/output/426"


def load_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        tris = np.empty((n, 3, 3), dtype=np.float32)
        for i in range(n):
            f.read(12)
            data = struct.unpack("<9f", f.read(36))
            tris[i] = np.array(data).reshape(3, 3)
            f.read(2)
    return tris


def render(tris, ax, title, color="#9bb8d3", edge="#33506e", elev=22, azim=-58):
    coll = Poly3DCollection(tris, alpha=0.9, facecolor=color,
                            edgecolor=edge, linewidths=0.05)
    ax.add_collection3d(coll)
    pts = tris.reshape(-1, 3)
    mn, mx = pts.min(0), pts.max(0)
    ctr = (mn + mx) / 2
    r = (mx - mn).max() / 2
    ax.set_xlim(ctr[0] - r, ctr[0] + r)
    ax.set_ylim(ctr[1] - r, ctr[1] + r)
    ax.set_zlim(ctr[2] - r, ctr[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    dims = mx - mn
    ax.set_title(f"{title}\n{dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm", fontsize=9)
    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")


def tris_from_step(path):
    from build123d import import_step
    shape = import_step(path)
    all_t = []
    solids = shape.solids() if hasattr(shape, "solids") else [shape]
    for s in solids:
        verts, faces = s.tessellate(0.4)
        v = np.array([(p.X, p.Y, p.Z) for p in verts])
        for f in faces:
            all_t.append(v[list(f)])
    return np.array(all_t)


fig = plt.figure(figsize=(20, 16))
NR, NC = 3, 4   # 3 行 4 列 (新增第 3 行: Type-C 剖切 + 壳外右壁视图)

# === 第 1 行: 三个打印件 (STL) + 装配体上下文 ===
parts = [("bezel.stl", "Bezel 前框", "#9bb8d3", "#33506e"),
         ("back_cover.stl", "Back cover 后盖", "#a8c8a0", "#3e6e38"),
         ("bracket.stl", "Bracket L 支架", "#d9b48a", "#8a5a2b")]
for i, (fn, t, c, e) in enumerate(parts):
    ax = fig.add_subplot(NR, NC, i + 1, projection="3d")
    render(load_stl(f"{OUT}/{fn}"), ax, t, color=c, edge=e)

# === 第 2 行 (左两幅): bracket 专属清晰视角 — 等轴 + 俯视, 看"单一实体 + L 角包严" ===
br_tris = load_stl(f"{OUT}/bracket.stl")
ax_iso = fig.add_subplot(NR, NC, 5, projection="3d")
render(br_tris, ax_iso, "Bracket 等轴视 (直支柱 + 宽结合, 单一实体)",
       color="#d9b48a", edge="#8a5a2b", elev=26, azim=-50)
ax_top = fig.add_subplot(NR, NC, 6, projection="3d")
# 俯视 (沿 -Z 看): elev=90 看 XY 平面, 笔直支柱(沿X)从卡钉直通对接板, 磁点中上部可见.
render(br_tris, ax_top, "Bracket 俯视 (笔直支柱直通板, 磁点中上)",
       color="#d9b48a", edge="#8a5a2b", elev=89, azim=-90)

# === 第 2 行 (右两幅): 装配体上下文 — 等轴 (格7) + 侧视 (格8) ===
from build123d import import_step
asm = import_step(f"{OUT}/assembly_context.step")
# label -> 颜色: 显示器灰, 支架棕, bezel 蓝, 后盖绿, 屏参考板亮灰
color_by_label = {
    "monitor_ref": "#bdbdbd", "bracket": "#d9b48a", "bezel": "#9bb8d3",
    "back_cover": "#a8c8a0", "screen_ref": "#5a7fa0",
}
# 预先把各节点三角面缓存 (供两个视角复用)
asm_tris = []  # (color, tri)
for node in (asm.children or []):
    col = color_by_label.get(getattr(node, "label", ""), "#cccccc")
    for s in node.solids():
        verts, faces = s.tessellate(0.5)
        v = np.array([(p.X, p.Y, p.Z) for p in verts])
        tri = np.array([v[list(f)] for f in faces])
        if len(tri):
            asm_tris.append((col, tri))
allpts = np.vstack([t for _, t in asm_tris]).reshape(-1, 3)
mn, mx = allpts.min(0), allpts.max(0)
ctr = (mn + mx) / 2; r = (mx - mn).max() / 2
d = mx - mn


def draw_asm(ax, elev, azim, title, xlabel, ylabel, zlabel, aspect=(1, 1, 1)):
    for col, tri in asm_tris:
        ax.add_collection3d(Poly3DCollection(tri, alpha=0.82, facecolor=col,
                                             edgecolor="#444", linewidths=0.04))
    ax.set_xlim(ctr[0]-r, ctr[0]+r); ax.set_ylim(ctr[1]-r, ctr[1]+r); ax.set_zlim(ctr[2]-r, ctr[2]+r)
    ax.set_box_aspect(aspect); ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=9)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.set_zlabel(zlabel)


# POGO / Type-C 世界位置 (从建模脚本取参数, 用于在装配视图上醒目标注)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("enclosure_426", "cad/enclosure_426.py")
_E = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_E)
_E.make_bracket()  # 填充 mate
_mate = _E.make_bracket.mate
from build123d import Box as _TCBox, Locations as _TCLoc, BuildPart as _TCBP, Align as _TCAl
# 架构变更: Type-C 移到支架底边 (口朝 -Y), POGO 在对接面 (针朝屏 +Z).
# --- Type-C 世界中心 (支架底边壁, 朝 -Y) ---
TC_X = _mate["tc_cx"]
TC_Y = _mate["bottom_y"]
TC_Z = _mate["tc_cz"]
# --- Type-C 专用壳块 (boss) 世界尺寸 (供局部视图标注壳厚/体腔) ---
H_W = _mate["housing_w"]; H_Y = _mate["housing_y"]; H_Z = _mate["housing_z"]
H_WALL = _mate["housing_wall"]
H_YMIN = _mate["housing_y_min"]; H_YMAX = _mate["housing_y_max"]
H_ZTOP = _mate["housing_z_top"]; H_ZBOT = _mate["housing_z_bot"]
H_CZ = _mate["housing_cz"]
# --- POGO 针阵世界坐标 (对接面, 针朝屏 +Z) ---
POGO_PINS = _mate["pogo_pins_world"]
POGO_CX = _mate["pogo_cx"]; POGO_CY = _mate["pogo_cy"]; POGO_PIN_Z = _mate["pogo_pin_tip_z"]
# --- 8×Φ8 磁 (已恢复): 支架对接面 4 磁心世界坐标 + 棋盘极性 (蓝=N, 橙=S) ---
MAG_WORLD = _mate["mag_world"]            # 支架侧 4 磁心 (世界 X,Y,Z=对接板顶面)
MAG_POL = _mate["mag_polarity"]            # 后盖侧棋盘极性 ['N','S','S','N']
MAG_TOP_Z = _mate["z_top"]
MAG_COL = {"N": "#1565c0", "S": "#ef6c00"}   # 蓝=N, 橙=S


def mark_typec(ax):
    """在装配视图上用红点 + 箭头标出 "支柱下方" Type-C 壳块 (口朝下 -Y 出线)."""
    ax.scatter([TC_X], [TC_Y], [TC_Z], c="#d11", s=70, marker="o",
               depthshade=False, edgecolors="k", zorder=10)
    ax.quiver(TC_X, TC_Y, TC_Z, 0, -14, 0, color="#d11", linewidth=2.2, zorder=11)
    ax.text(TC_X + 2, TC_Y - 12, TC_Z + 4,
            f"防水 Type-C 壳块 (支柱下方)\n(壳 {H_W:.0f}×{H_Z:.0f}, 口朝下 -Y)\n体深入 +Y {_E.TYPEC_BODY_DEPTH:.0f}mm",
            color="#a00", fontsize=8, zorder=12)


def mark_magnets(ax, label=True):
    """在视图上用蓝(N)/橙(S)点标出对接面 4×Φ8 磁 (棋盘极性, 吸合/承重)."""
    for (mx, my, mz), pol in zip(MAG_WORLD, MAG_POL):
        ax.scatter([mx], [my], [mz], c=MAG_COL[pol], s=90, marker="o",
                   depthshade=False, edgecolors="k", linewidths=0.8, zorder=10)
    if label:
        # 取上方一颗磁标注 (Y 最大)
        mtop = max(MAG_WORLD, key=lambda p: p[1])
        ax.text(mtop[0] + 1, mtop[1] + 2, mtop[2] + 3,
                "4×Φ8 磁 (吸合/承重)\n蓝=N 橙=S (棋盘极性)\n四角围 POGO, 镜像对吸",
                color="#0d47a1", fontsize=8, zorder=12)


def mark_pogo(ax):
    """在装配视图上用绿点 + 箭头标出对接面 POGO 针阵 (针朝屏 +Z)."""
    xs = [p[0] for p in POGO_PINS]; ys = [p[1] for p in POGO_PINS]; zs = [p[2] for p in POGO_PINS]
    ax.scatter(xs, ys, zs, c="#0a0", s=45, marker="^", depthshade=False,
               edgecolors="k", zorder=10)
    # 针朝屏方向箭头: +Z (朝屏体后盖)
    ax.quiver(POGO_CX, POGO_CY, POGO_PIN_Z, 0, 0, 6, color="#0a0", linewidth=2.2, zorder=11)
    ax.text(POGO_CX - 2, POGO_CY + 3, POGO_PIN_Z + 3,
            "POGO 4 针\n(对接面, 针朝屏 +Z)\n+磁吸 N/S",
            color="#070", fontsize=8, zorder=12)


# 格 7: 装配等轴 (看整体落位) + POGO + Type-C 标注
ax_aiso = fig.add_subplot(NR, NC, 7, projection="3d")
draw_asm(ax_aiso, 18, -65,
         "Assembly 等轴 (屏顶=显示器顶持平, 屏在左侧外)\n8×Φ8 磁吸合承重(蓝N/橙S) + POGO 供电对位(绿) · Type-C 支柱下方朝下(红)",
         "X (右=朝显示器)", "Y (上)", "Z (朝用户)")
mark_magnets(ax_aiso)
mark_pogo(ax_aiso)
mark_typec(ax_aiso)

# 格 8: 装配侧视 (沿 -X 看 Y-Z 平面) — 一眼可见 墨水屏与显示器共面、支柱藏背后
ax_side = fig.add_subplot(NR, NC, 8, projection="3d")
draw_asm(ax_side, 6, 0,
         "Assembly 侧视 (沿 -X 看 Y-Z): 墨水屏与显示器正面共面\n支柱/对接板藏屏后; POGO(绿)朝屏; Type-C(红)支柱下方朝下",
         "X (右=朝显示器)", "Y (上)", "Z (朝用户=+Z)", aspect=(0.35, 1, 1))
mark_magnets(ax_side, label=False)
mark_pogo(ax_side)
mark_typec(ax_side)

# ============================================================
# 第 3 行: POGO 专属视图 (对接面针朝屏) + Type-C 专属视图 (支架底边剖切露 14mm 体腔)
# ============================================================
# 收集装配世界三角面, 按 label 分色 (含 bracket + 屏体 + pcba), 供 POGO/Type-C 局部视角复用.
all_node_tris = []  # (color, tri)
pcba_col = {"pcb": "#2f7d4f", "components": "#888888",
            "pogo_pads": "#d11", "fpc_conn": "#e08a2b"}
for node in (asm.children or []):
    lbl = getattr(node, "label", "")
    col = color_by_label.get(lbl, "#e0a0a0" if lbl == "pcba" else "#cccccc")
    if lbl == "pcba":
        for sub in (node.children or []):
            scol = pcba_col.get(getattr(sub, "label", ""), "#e0a0a0")
            for s in sub.solids():
                verts, faces = s.tessellate(0.4)
                v = np.array([(p.X, p.Y, p.Z) for p in verts])
                tri = np.array([v[list(f)] for f in faces])
                if len(tri):
                    all_node_tris.append((scol, tri, lbl))
        continue
    for s in node.solids():
        verts, faces = s.tessellate(0.4)
        v = np.array([(p.X, p.Y, p.Z) for p in verts])
        tri = np.array([v[list(f)] for f in faces])
        if len(tri):
            all_node_tris.append((col, tri, lbl))


def _draw_subset(ax, items, elev, azim, ctr, r, aspect=(1, 1, 1), alpha=0.9):
    for col, tri in items:
        ax.add_collection3d(Poly3DCollection(tri, alpha=alpha, facecolor=col,
                                             edgecolor="#333", linewidths=0.06))
    ax.set_xlim(ctr[0]-r, ctr[0]+r); ax.set_ylim(ctr[1]-r, ctr[1]+r); ax.set_zlim(ctr[2]-r, ctr[2]+r)
    ax.set_box_aspect(aspect); ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("X (右=朝显示器)"); ax.set_ylabel("Y (上)"); ax.set_zlabel("Z")


# --- 格 9: POGO 区局部 (支架对接面 + 屏体后盖对接区), 看 POGO 针朝屏 + pad 窗/钢片 ---
# 聚焦 POGO 中心一带 (世界): 取该邻域三角面 (X,Y 邻域), 不含显示器, 画对接面与后盖.
P_CX, P_CY, P_CZ = POGO_CX, POGO_CY, (POGO_PIN_Z + _mate["z_top"]) / 2
RAD = 34.0   # 放宽到含四角 4 磁 (磁在 X=±26.6, Y=band±18 一带)
def _near_pogo(tri):
    c = tri.reshape(-1, 3).mean(0)
    return abs(c[0]-P_CX) < RAD and abs(c[1]-P_CY) < RAD and c[2] > _mate["z_bot"]-3
# 逐三角面邻域裁剪 (聚焦 POGO):
pogo_items = []
for (col, tri, lbl) in all_node_tris:
    if lbl not in ("bracket", "back_cover", "pcba"):
        continue
    keep = np.array([_near_pogo(t) for t in tri])
    if keep.any():
        pogo_items.append((col, tri[keep]))
ax_pogo = fig.add_subplot(NR, NC, 9, projection="3d")
_draw_subset(ax_pogo, pogo_items, 16, -60, (P_CX, P_CY, P_CZ), RAD, aspect=(1, 1, 0.8))
ax_pogo.set_title("对接区局部: 8×Φ8 磁(蓝N/橙S, 四角承重) + POGO 4 针朝屏(绿▲, 供电对位)\n"
                  "后盖 4 pad 窗(红)+2 钢片腔 对位 pogo 针/磁; 8 磁 ↔ 4 磁镜像对吸", fontsize=9)
mark_magnets(ax_pogo)
mark_pogo(ax_pogo)

# --- 格 10: 后盖 Φ8 磁腔剖切 (修 bug1) — 一眼看 "磁腔内侧敞开, 磁从内侧装入; 外侧留薄壁" ---
#   取独立 back_cover STL (局部坐标 z: 0=外侧朝支架, +z=内侧朝 PCB), 过一列磁心 X 竖切, 沿 +X 看 Y-Z 剖面.
#   修 bug1: 磁柱顶降到与腔顶齐平 => 内侧 (+z) 敞开; 外侧 (z<0.8) 留薄壁透磁.
br_items = [(col, tri) for (col, tri, lbl) in all_node_tris if lbl == "bracket"]   # 供格11/12 复用
bc_tris = load_stl(f"{OUT}/back_cover.stl")
MAG_OW = _E.MAG_OUTER_WALL; MAG_T = _E.MAG_T
BC_MAG_X = _E.MAG_COL_X            # 磁列局部 X (±MAG_COL_X)
# 过 X=BC_MAG_X-0.2 切, 保留 X>=该面半, 沿 +X 看 (azim=-90) => Y-Z 剖面露磁腔内外开口.
BC_CUT_X = BC_MAG_X - 0.2
# 该磁列 Y 中心 (取上排磁): DOCK_CENTER_Y + MAG_INSET_Y
BC_MAG_Y = _E.DOCK_CENTER_Y + _E.MAG_INSET_Y
bc_sect = []
for t in bc_tris:
    if t.reshape(-1, 3)[:, 0].mean() >= BC_CUT_X:
        bc_sect.append(t)
bc_sect = np.array(bc_sect)
ax_bcmag = fig.add_subplot(NR, NC, 10, projection="3d")
_draw_subset(ax_bcmag, [("#a8c8a0", bc_sect)], 6, -90,
             (BC_MAG_X, BC_MAG_Y, (MAG_OW + MAG_T) / 2), 16.0, aspect=(1, 1.4, 1))
ax_bcmag.set_title("后盖 Φ8 磁腔剖切 (修 bug1, 沿 +X 看 Y-Z):\n"
                   f"内侧(+z, 朝PCB)敞开 磁从内侧压入 · 外侧(z<{MAG_OW})留薄壁透磁(磁柱顶已去 0.5 盖)",
                   fontsize=9)
# 内侧装入箭头 (从内侧 +z 朝 -z 压入磁铁)
ax_bcmag.quiver(BC_MAG_X, BC_MAG_Y, MAG_OW + MAG_T + 4, 0, 0, -3.0, color="#b00", linewidth=2.4, zorder=12)
ax_bcmag.text(BC_MAG_X, BC_MAG_Y, MAG_OW + MAG_T + 4.5,
              "磁从内侧 (+z) 压入\n(腔内侧敞开)", color="#900", fontsize=8, zorder=12)
# 外侧薄壁标注
ax_bcmag.plot([BC_MAG_X]*2, [BC_MAG_Y]*2, [0, MAG_OW], color="#06c", linewidth=3.0, zorder=12)
ax_bcmag.text(BC_MAG_X, BC_MAG_Y, -2.5, f"外侧薄壁 {MAG_OW}\n(朝支架, 透磁)",
              color="#04a", fontsize=8, zorder=12)

# --- 格 11: Type-C 壳块 (b) 剖切 (过 X=TC_X 竖直面), 露壳厚 + 14mm 体腔 + 走线腔 ---
#   过 X=TC_X 切, 保留 X>=TC_X-0.3 半, 沿 -X 看体腔内部 (Y-Z 剖面).
CUT_X = TC_X - 0.3
sect = []
for col, tri in br_items:
    cx = tri.reshape(-1, 3)[:, 0].reshape(-1, 3).mean(1)
    keep = tri[cx >= CUT_X]
    if len(keep):
        sect.append((col, keep))
TC_FOCUS_Y = (H_YMIN + _mate["channel_y_bot"]) / 2
foc_ctr_b = (TC_X, TC_FOCUS_Y, H_CZ); foc_r_b = 16.0
ax_tcb = fig.add_subplot(NR, NC, 11, projection="3d")
_draw_subset(ax_tcb, sect, 8, -100, foc_ctr_b, foc_r_b, aspect=(1, 1.2, 0.9))
ax_tcb.set_title(f"(b) Type-C 壳块剖切 (支柱下方, 过 X={TC_X:.0f}, 沿 -X 看 Y-Z):\n"
                 f"壳厚 {H_Z:.1f} 包裹 · 体腔深入 +Y {_E.TYPEC_BODY_DEPTH:.0f}mm · 经熔接颈上接支柱/走线腔", fontsize=9)
# 标体腔深 (Y 向) + 壳厚 (Z 向) 双箭头.
cav_y0 = H_YMIN + _E.TYPEC_FLANGE_T
cav_y1 = cav_y0 + _E.TYPEC_BODY_DEPTH
ax_tcb.plot([TC_X]*2, [cav_y0, cav_y1], [H_CZ]*2, color="#06c", linewidth=2.2, zorder=12)
ax_tcb.text(TC_X, (cav_y0 + cav_y1) / 2, H_CZ + 1,
            f"体腔 +Y {_E.TYPEC_BODY_DEPTH:.0f}mm", color="#04a", fontsize=8, zorder=12)
ax_tcb.plot([TC_X]*2, [H_YMIN - 1]*2, [H_ZBOT, H_ZTOP], color="#a00", linewidth=2.0, zorder=12)
ax_tcb.text(TC_X, H_YMIN - 2, H_CZ, f"壳厚 {H_Z:.1f}", color="#a00", fontsize=8, zorder=12)
mark_typec(ax_tcb)

# --- 格 12: POGO 剖切 (过 Y=POGO_CY 水平面, 沿 +Y 看 X-Z 剖面) — 一眼看 "POGO 从 -Z 背面装入 + 针孔朝屏 +Z" ---
#   修 bug2 验证: 本体凹腔从 -Z 背面 (z_bot) 敞开; +Z 贴合面只留薄壁 + 4 针孔; 走线腔在 -Z 背面.
#   过 Y=POGO_CY-0.3 切, 保留 Y>=该面半, 沿 +Y 看 (elev≈0 azim=-90) => X-Z 剖面露 POGO 腔上下开口.
P_ZBOT = _mate["z_bot"]; P_ZTOP = _mate["z_top"]
P_FLOOR = _mate["pogo_pocket_floor_z"]
CUT_Y = POGO_CY - 0.2
pogo_sect = []
for col, tri in br_items:
    cy = tri.reshape(-1, 3)[:, 1].reshape(-1, 3).mean(1)
    keep = tri[cy >= CUT_Y]
    if len(keep):
        pogo_sect.append((col, keep))
pfoc_ctr = (POGO_CX, POGO_CY, (P_ZBOT + P_ZTOP) / 2); pfoc_r = 14.0
ax_pgsec = fig.add_subplot(NR, NC, 12, projection="3d")
_draw_subset(ax_pgsec, pogo_sect, 6, -90, pfoc_ctr, pfoc_r, aspect=(1.4, 1, 1))
ax_pgsec.set_title("POGO 剖切 (过 POGO 中心, 沿 +Y 看 X-Z): 修 bug2\n"
                   "本体凹腔 -Z 背面敞开装入(▼) · 贴合面薄壁 4 针孔朝屏 +Z(▲) · 走线腔在 -Z 背面",
                   fontsize=9)
# -Z 背面装入箭头 (从背面 z_bot 朝 +Z 推入)
ax_pgsec.quiver(POGO_CX, POGO_CY, P_ZBOT - 4, 0, 0, 3.2, color="#b00", linewidth=2.4, zorder=12)
ax_pgsec.text(POGO_CX, POGO_CY, P_ZBOT - 5,
              "POGO 从 -Z 背面装入\n(焊脚/飞线朝背面)", color="#900", fontsize=8, zorder=12)
# +Z 针孔凸出朝屏箭头
ax_pgsec.quiver(POGO_CX, POGO_CY, P_ZTOP, 0, 0, 4.0, color="#0a0", linewidth=2.4, zorder=12)
ax_pgsec.text(POGO_CX, POGO_CY, P_ZTOP + 4,
              f"4 针穿薄壁针孔\n凸出朝屏 +Z (针尖 {POGO_PIN_Z:.1f})", color="#070", fontsize=8, zorder=12)
mark_pogo(ax_pgsec)

plt.tight_layout()
plt.savefig(f"{OUT}/preview_426.png", dpi=115)
print(f"saved {OUT}/preview_426.png")
