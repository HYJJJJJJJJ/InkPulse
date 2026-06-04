"""把 STL 渲染成 PNG 预览（独立校验几何用）。binary STL -> matplotlib 3D。"""
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# 中文字体 (macOS 自带)
matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Hiragino Sans GB",
                                          "Songti SC", "STHeiti"]
matplotlib.rcParams["axes.unicode_minus"] = False
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def load_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        tris = np.empty((n, 3, 3), dtype=np.float32)
        for i in range(n):
            f.read(12)  # normal
            data = struct.unpack("<9f", f.read(36))
            tris[i] = np.array(data).reshape(3, 3)
            f.read(2)
    return tris


def render(path, ax, title):
    tris = load_stl(path)
    coll = Poly3DCollection(tris, alpha=0.9, facecolor="#9bb8d3",
                            edgecolor="#33506e", linewidths=0.05)
    ax.add_collection3d(coll)
    pts = tris.reshape(-1, 3)
    mn, mx = pts.min(0), pts.max(0)
    ctr = (mn + mx) / 2
    r = (mx - mn).max() / 2
    ax.set_xlim(ctr[0] - r, ctr[0] + r)
    ax.set_ylim(ctr[1] - r, ctr[1] + r)
    ax.set_zlim(ctr[2] - r, ctr[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=22, azim=-58)
    dims = mx - mn
    ax.set_title(f"{title}\n{dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm", fontsize=9)
    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")


parts = [("bezel.stl", "Bezel 前框"), ("back_cover.stl", "Back cover 后盖"),
         ("base.stl", "Base 底座"), ("lid.stl", "Lid 抽拉盖板")]
fig = plt.figure(figsize=(20, 5))
for i, (fn, t) in enumerate(parts):
    ax = fig.add_subplot(1, 4, i + 1, projection="3d")
    render(f"cad/output/{fn}", ax, t)
plt.tight_layout()
plt.savefig("cad/output/preview_parts.png", dpi=110)
print("saved cad/output/preview_parts.png")

# 装配体：用 build123d 导入 STEP，三角化后渲染，核验 60° 姿态
from build123d import import_step

def tris_from_step(path):
    shape = import_step(path)
    all_t = []
    solids = shape.solids() if hasattr(shape, "solids") else [shape]
    for s in solids:
        verts, faces = s.tessellate(0.4)
        v = np.array([(p.X, p.Y, p.Z) for p in verts])
        for f in faces:
            all_t.append(v[list(f)])
    return np.array(all_t)

fig2 = plt.figure(figsize=(8, 8))
ax2 = fig2.add_subplot(111, projection="3d")
tris = tris_from_step("cad/output/assembly.step")
coll = Poly3DCollection(tris, alpha=0.85, facecolor="#9bb8d3",
                        edgecolor="#33506e", linewidths=0.05)
ax2.add_collection3d(coll)
pts = tris.reshape(-1, 3)
mn, mx = pts.min(0), pts.max(0)
ctr = (mn + mx) / 2; r = (mx - mn).max() / 2
ax2.set_xlim(ctr[0]-r, ctr[0]+r); ax2.set_ylim(ctr[1]-r, ctr[1]+r); ax2.set_zlim(ctr[2]-r, ctr[2]+r)
ax2.set_box_aspect((1, 1, 1)); ax2.view_init(elev=12, azim=-72)
d = mx - mn
ax2.set_title(f"Assembly 装配体 {d[0]:.0f} x {d[1]:.0f} x {d[2]:.0f} mm", fontsize=10)
ax2.set_xlabel("X"); ax2.set_ylabel("Y"); ax2.set_zlabel("Z")
plt.tight_layout()
plt.savefig("cad/output/preview_assembly.png", dpi=120)
print("saved cad/output/preview_assembly.png")


# ============================================================
# 盖板专项视图: (左) 俯视 base+lid 闭合, 看仓口贴合/FPC缺口/抽拉方向
#               (右) YZ 剖面, 看盖板坐唇下 + 与 Type-C/斜墙关系
# ============================================================
base_tris = tris_from_step("cad/output/base.step")
lid_tris = tris_from_step("cad/output/lid.step")

figL = plt.figure(figsize=(15, 7))

# --- (1) 俯视图 (XY 投影, 看 +Z 向下) ---
axT = figL.add_subplot(1, 2, 1)
# 俯视: 画三角形在 XY 的投影; base 浅灰, lid 高亮(用 z 最大面优先)
from matplotlib.collections import PolyCollection
def xy_polys(tris):
    return [t[:, :2] for t in tris]
axT.add_collection(PolyCollection(xy_polys(base_tris), facecolors="#d7dde3",
                                  edgecolors="#9aa6b2", linewidths=0.1, alpha=0.5))
axT.add_collection(PolyCollection(xy_polys(lid_tris), facecolors="#e8a04a",
                                  edgecolors="#a8651f", linewidths=0.15, alpha=0.85))
allpts = np.vstack([base_tris.reshape(-1, 3), lid_tris.reshape(-1, 3)])
axT.set_xlim(allpts[:, 0].min() - 3, allpts[:, 0].max() + 3)
axT.set_ylim(allpts[:, 1].min() - 3, allpts[:, 1].max() + 3)
axT.set_aspect("equal")
axT.set_title("俯视 Top (base 灰 + lid 橙)\n抽拉方向 -> +X(右); 前缘 -Y FPC 缺口", fontsize=10)
axT.set_xlabel("X (抽拉方向 ->)"); axT.set_ylabel("Y (+后/Type-C, -前/屏)")
axT.annotate("", xy=(50, 0), xytext=(38, 0),
             arrowprops=dict(arrowstyle="->", color="red", lw=2))
axT.text(45, 3, "抽出", color="red", fontsize=9)
axT.axhline(-21.9, color="purple", ls="--", lw=0.8)
axT.text(-60, -21.0, "斜墙边界 Y=-21.9", color="purple", fontsize=7)

# --- (2) YZ 剖面 (取 X≈+25 处薄片, 落在唇/盖板区, 避开 -X 挡位) ---
axS = figL.add_subplot(1, 2, 2)
X_SLICE = 25.0
HALF = 1.5
def yz_slice(tris, x0, half):
    segs = []
    for t in tris:
        zs = t[:, 0]
        if zs.min() <= x0 + half and zs.max() >= x0 - half:
            # 该三角形跨过切片: 投影其顶点到 YZ
            segs.append(t[:, 1:3])
    return segs
axS.add_collection(PolyCollection(yz_slice(base_tris, X_SLICE, HALF),
                   facecolors="#cdd6df", edgecolors="#8d99a6", linewidths=0.2, alpha=0.5))
axS.add_collection(PolyCollection(yz_slice(lid_tris, X_SLICE, HALF),
                   facecolors="#e8a04a", edgecolors="#a8651f", linewidths=0.3, alpha=0.9))
# 参考线: Type-C 开口 z 4.65..10.65; 元件顶 9.7; 盖板 z 10.25..11.75; 唇底 11.9; 盒顶 12.5
for zz, lab, c in [(4.65, "TypeC底4.65", "#2f7d32"), (10.65, "TypeC顶10.65", "#2f7d32"),
                   (9.7, "元件顶9.7", "#c62828"), (10.25, "盖板底10.25", "#e65100"),
                   (11.9, "唇底11.9", "#1565c0"), (12.5, "盒顶12.5", "#555")]:
    axS.axhline(zz, color=c, ls=":", lw=0.8)
    axS.text(-30, zz + 0.1, lab, color=c, fontsize=7)
axS.set_aspect("equal")
axS.set_title(f"YZ 剖面 @X={X_SLICE:.0f}\n盖板(橙)在元件(9.7)上方槽内, 不压PCB/不侵Type-C", fontsize=10)
axS.set_xlabel("Y (+后/Type-C)"); axS.set_ylabel("Z")
axS.set_xlim(-32, 32); axS.set_ylim(0, 14)

plt.tight_layout()
plt.savefig("cad/output/preview_lid_top_section.png", dpi=130)
print("saved cad/output/preview_lid_top_section.png")
