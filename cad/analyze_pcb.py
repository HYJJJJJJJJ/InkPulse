"""分析 hardware/PCB1.step, 提取外壳设计所需机械接口: 外形/板厚/孔位/高元件/边缘连接器。
坐标重定心到板几何中心(XY), Z 以板底为 0。只打印精简结论。"""
from build123d import import_step, GeomType
import numpy as np

sh = import_step("hardware/PCB1.step")
solids = sh.solids()
print(f"solids 数量: {len(solids)}")

# bbox 工具
def bb(s):
    b = s.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)

infos = []
for i, s in enumerate(solids):
    x0, y0, z0, x1, y1, z1 = bb(s)
    infos.append(dict(i=i, s=s, dx=x1-x0, dy=y1-y0, dz=z1-z0,
                      cx=(x0+x1)/2, cy=(y0+y1)/2, z0=z0, z1=z1,
                      foot=(x1-x0)*(y1-y0)))

# 板 = footprint 最大且较薄(dz<3)
cands = [d for d in infos if d["dz"] < 3.0]
board = max(cands, key=lambda d: d["foot"]) if cands else max(infos, key=lambda d: d["foot"])
bx0, by0, bz0, bx1, by1, bz1 = bb(board["s"])
ox, oy = (bx0+bx1)/2, (by0+by1)/2   # 板中心 -> 新原点
oz = bz0                             # 板底 -> z=0
print(f"\n=== 板 (PCB) ===")
print(f"外形 dx x dy = {board['dx']:.2f} x {board['dy']:.2f} mm   板厚 dz = {board['dz']:.2f} mm")
print(f"原板坐标中心 = ({ox:.2f}, {oy:.2f}), 板底 z={oz:.2f}  (以下坐标已重定心: 板中心=XY原点, 板底=Z0)")

def rc(d):  # 重定心后的 center/Z
    return d["cx"]-ox, d["cy"]-oy, d["z0"]-oz, d["z1"]-oz

# 高元件 (顶面 z1 最高), 排除板本身
comps = [d for d in infos if d["i"] != board["i"]]
comps.sort(key=lambda d: d["z1"], reverse=True)
print(f"\n=== 最高的 12 个元件 (重定心坐标) ===")
print(f"{'idx':>4} {'cx':>7} {'cy':>7} {'顶高z1':>7} {'dz':>6} {'dx':>6} {'dy':>6}")
for d in comps[:12]:
    cx, cy, zz0, zz1 = rc(d)
    print(f"{d['i']:>4} {cx:>7.1f} {cy:>7.1f} {zz1:>7.1f} {d['dz']:>6.1f} {d['dx']:>6.1f} {d['dy']:>6.1f}")

# 靠近板边的元件 (连接器候选: Type-C / FPC 排座通常贴边)
hw = board["dx"]/2; hh = board["dy"]/2
print(f"\n=== 贴近板边(<6mm)的元件 (连接器候选) ===")
print(f"{'idx':>4} {'cx':>7} {'cy':>7} {'顶高':>6} {'dx':>6} {'dy':>6}  近边")
for d in comps:
    cx, cy, zz0, zz1 = rc(d)
    edges = []
    if abs(cx - hw) < 6 or hw-abs(cx) < 6:
        edges.append("X+" if cx>0 else "X-")
    if hh-abs(cy) < 6:
        edges.append("Y+" if cy>0 else "Y-")
    if edges and d["dz"] > 1.5:
        print(f"{d['i']:>4} {cx:>7.1f} {cy:>7.1f} {zz1:>6.1f} {d['dx']:>6.1f} {d['dy']:>6.1f}  {','.join(edges)}")

# 安装孔: 板 solid 上半径 1.0~2.5mm 的圆边 (排除微小过孔)
print(f"\n=== 安装孔候选 (板上 R=1.0~2.5mm 圆边, 重定心) ===")
seen = set()
for e in board["s"].edges().filter_by(GeomType.CIRCLE):
    try:
        r = e.radius
    except Exception:
        continue
    if 1.0 <= r <= 2.5:
        c = e.arc_center
        key = (round(c.X-ox), round(c.Y-oy))
        if key in seen:
            continue
        seen.add(key)
        print(f"  孔心 ({c.X-ox:>7.2f}, {c.Y-oy:>7.2f})  R={r:.2f} (Φ{2*r:.1f})")
print("\n(注: X+/X-/Y+/Y- 为板的四条边; 需你确认哪条边朝 Type-C/朝屏)")
