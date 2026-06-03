"""把 STL 渲染成 PNG 预览（独立校验几何用）。binary STL -> matplotlib 3D。"""
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
         ("base.stl", "Base 底座")]
fig = plt.figure(figsize=(15, 5))
for i, (fn, t) in enumerate(parts):
    ax = fig.add_subplot(1, 3, i + 1, projection="3d")
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
