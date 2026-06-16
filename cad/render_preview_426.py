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


# Type-C 开口世界位置 (从建模脚本取参数, 用于在装配视图上醒目标注)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("enclosure_426", "cad/enclosure_426.py")
_E = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_E)
_E.make_bracket()  # 填充 mate
# Type-C 开口世界中心: 开口切在 bezel 局部 -X 壁 (装配后落世界 max X = 朝显示器壁).
#   故标注盒放 -BEZEL_OUT_W/2, 且只经 bezel 装配变换 (body_placement), 不经 back_cover_local.
_tc_place = _E.body_placement()
from build123d import Box as _TCBox, Locations as _TCLoc, BuildPart as _TCBP, Align as _TCAl
with _TCBP() as _tcp:
    with _TCLoc((-_E.BEZEL_OUT_W/2, _E.TYPEC_LOCAL_Y, _E.TYPEC_CENTER_Z)):
        _TCBox(_E.WALL*4, _E.TYPEC_W, _E.TYPEC_H, align=(_TCAl.CENTER,)*3)
_tcbb = (_tc_place * _tcp.part).bounding_box()
TC_X = (_tcbb.min.X + _tcbb.max.X) / 2
TC_Y = (_tcbb.min.Y + _tcbb.max.Y) / 2
TC_Z = (_tcbb.min.Z + _tcbb.max.Z) / 2


def mark_typec(ax):
    """在装配视图上用红点 + 箭头标出 Type-C 开口 (朝显示器 +X 出线)."""
    ax.scatter([TC_X], [TC_Y], [TC_Z], c="#d11", s=70, marker="o",
               depthshade=False, edgecolors="k", zorder=10)
    # 出线方向箭头: 朝 +X (朝显示器)
    ax.quiver(TC_X, TC_Y, TC_Z, 12, 0, 0, color="#d11", linewidth=2.2, zorder=11)
    ax.text(TC_X + 2, TC_Y + 6, TC_Z + 4,
            f"Type-C 开口\n(右侧边朝显示器, 屏顶下方 {abs(TC_Y):.0f}mm)\n法向 +X 出线",
            color="#a00", fontsize=8, zorder=12)


# 格 7: 装配等轴 (看整体落位) + Type-C 标注
ax_aiso = fig.add_subplot(NR, NC, 7, projection="3d")
draw_asm(ax_aiso, 18, -65,
         f"Assembly 等轴 (屏顶=显示器顶持平, 屏在左侧外)\nType-C 在右侧边朝显示器·靠上 (红点/箭头)",
         "X (右=朝显示器)", "Y (上)", "Z (朝用户)")
mark_typec(ax_aiso)

# 格 8: 装配侧视 (沿 -X 看 Y-Z 平面) — 一眼可见 墨水屏与显示器共面、支柱藏背后、不向 +Z 凸
ax_side = fig.add_subplot(NR, NC, 8, projection="3d")
draw_asm(ax_side, 6, 0,
         "Assembly 侧视 (沿 -X 看 Y-Z): 墨水屏与显示器正面共面\n支柱/对接板藏屏后; Type-C 右侧边·靠上 (红点)",
         "X (右=朝显示器)", "Y (上)", "Z (朝用户=+Z)", aspect=(0.35, 1, 1))
mark_typec(ax_side)

# ============================================================
# 第 3 行: Type-C 专属视图 (剖切露内部 + 壳外右壁看开口)
# ============================================================
# 重建带 label 的"屏体+PCBA"世界三角面 (含 bezel/back_cover/pcba/screen_ref, 不含 monitor/bracket),
# 以便剖切时只剖屏体, 露出 PCB/支柱/Type-C 母座/前框侧壁开口.
body_tris = []  # (color, tri)
for node in (asm.children or []):
    lbl = getattr(node, "label", "")
    if lbl in ("monitor_ref", "bracket"):
        continue   # 剖切图聚焦屏体内部, 不画显示器/支架
    col = color_by_label.get(lbl, "#e0a0a0" if lbl == "pcba" else "#cccccc")
    # pcba 子件分色: PCB 深绿, 元件灰, Type-C 母座红, FPC 座橙
    pcba_col = {"pcb": "#2f7d4f", "components": "#888888",
                "typec_recept": "#d11", "fpc_conn": "#e08a2b"}
    if lbl == "pcba":
        for sub in (node.children or []):
            scol = pcba_col.get(getattr(sub, "label", ""), "#e0a0a0")
            for s in sub.solids():
                verts, faces = s.tessellate(0.4)
                v = np.array([(p.X, p.Y, p.Z) for p in verts])
                tri = np.array([v[list(f)] for f in faces])
                if len(tri):
                    body_tris.append((scol, tri))
        continue
    for s in node.solids():
        verts, faces = s.tessellate(0.4)
        v = np.array([(p.X, p.Y, p.Z) for p in verts])
        tri = np.array([v[list(f)] for f in faces])
        if len(tri):
            body_tris.append((col, tri))

# 剖切: 过 Type-C 的水平面 Y=TC_Y 切开, 只保留 Y<=TC_Y 半 (剖面朝 +Y 观察者),
#   露出右壁开口 / PCB 边 / Type-C 母座 / 支柱。按三角面中心 Y 过滤 (轻量裁剪).
CUT_Y = TC_Y + 0.5
def clip_below_y(tris_list, ymax):
    out = []
    for col, tri in tris_list:
        cy = tri.reshape(-1, 3)[:, 1].reshape(-1, 3).mean(1)  # 每三角面中心 Y
        keep = tri[cy <= ymax]
        if len(keep):
            out.append((col, keep))
    return out
sect = clip_below_y(body_tris, CUT_Y)
spts = np.vstack([t for _, t in sect]).reshape(-1, 3)
smn, smx = spts.min(0), spts.max(0); sctr = (smn + smx) / 2; sr = (smx - smn).max() / 2

# 格 9: 剖切等轴 (从 +Y 上方俯看剖面) — 看 Type-C 母座对准右壁开口、PCB/支柱叠层
ax_sec = fig.add_subplot(NR, NC, 9, projection="3d")
for col, tri in sect:
    ax_sec.add_collection3d(Poly3DCollection(tri, alpha=0.9, facecolor=col,
                                             edgecolor="#333", linewidths=0.06))
ax_sec.set_xlim(sctr[0]-sr, sctr[0]+sr); ax_sec.set_ylim(sctr[1]-sr, sctr[1]+sr)
ax_sec.set_zlim(sctr[2]-sr, sctr[2]+sr)
ax_sec.set_box_aspect((1, 1, 1)); ax_sec.view_init(elev=32, azim=-72)
ax_sec.set_title(f"屏体剖切 (过 Type-C 平面 Y={TC_Y:.0f}): 露 PCB(绿)/支柱/\n"
                 f"Type-C 母座(红)对准右壁开口 / 前框侧壁", fontsize=9)
ax_sec.set_xlabel("X (右=朝显示器)"); ax_sec.set_ylabel("Y"); ax_sec.set_zlabel("Z")
mark_typec(ax_sec)

# 格 10: 从壳外 +X 正对右侧壁看 (沿 -X 视线) — Type-C 开口一眼可见 (壁上的方口)
# 只画屏体 (bezel+back_cover) 外观, 视线从 +X 朝 -X, 即正对朝显示器的右侧壁.
shell_tris = [(c, t) for (c, t) in body_tris
              if c in ("#9bb8d3", "#a8c8a0")]  # 仅 bezel(蓝)/back_cover(绿)
ax_wall = fig.add_subplot(NR, NC, 10, projection="3d")
for col, tri in shell_tris:
    ax_wall.add_collection3d(Poly3DCollection(tri, alpha=0.95, facecolor=col,
                                              edgecolor="#456", linewidths=0.08))
wpts = np.vstack([t for _, t in shell_tris]).reshape(-1, 3)
wmn, wmx = wpts.min(0), wpts.max(0)
# 聚焦朝显示器壁 (世界 max X) 一带, 沿 X 收紧, Y/Z 围绕 Type-C, 压扁 X 轴正视壁面.
ax_wall.set_xlim(wmx[0] - 14, wmx[0] + 2)
ax_wall.set_ylim(TC_Y - 58, TC_Y + 58)
ax_wall.set_zlim(-12, 2)
ax_wall.set_box_aspect((0.6, 3.0, 1.0))
# elev=15, azim=-100: 自壳外 +X 略俯视正对朝显示器壁, 壁上 Type-C 方口缺口清晰可见.
ax_wall.view_init(elev=15, azim=-100)
ax_wall.set_title("从壳外 +X 看朝显示器右侧壁:\nType-C 方口清晰可见 (壁上缺口, 红点标注)", fontsize=9)
ax_wall.set_xlabel("X (右=朝显示器)"); ax_wall.set_ylabel("Y (上)"); ax_wall.set_zlabel("Z")
mark_typec(ax_wall)

plt.tight_layout()
plt.savefig(f"{OUT}/preview_426.png", dpi=115)
print(f"saved {OUT}/preview_426.png")
