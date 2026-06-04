"""算装配姿态下: 屏 FPC 出线点 -> PCB 显示排座 的实际走线距离, 判断 FPC 是否够长。"""
import sys, math
sys.path.insert(0, "cad")
import enclosure as E
from build123d import Rot, Pos, Vector

# --- 复现 make_assembly 的 R, T ---
run = E.GUSSET_HEIGHT / math.tan(math.radians(E.ANGLE_DEG))
seam_z0 = E.BASE_FOOT_T
front_y = -E.BASE_FOOT_D / 2
A = Vector(0, front_y, seam_z0)
R = Rot(-120, 0, 0) * Rot(0, 0, 180)
p_rot = (R * Pos(0, -E.BEZEL_OUT_H / 2, E.BEZEL_DEPTH)).position
T = p_rot_T = A - p_rot

def to_world(xl, yl, zl):
    p = (Pos(T.X, T.Y, T.Z) * R * Pos(xl, yl, zl)).position
    return Vector(p.X, p.Y, p.Z)

# 屏 FPC 出线点 (bezel 局部): 玻璃底边中点, 玻璃背面.
#   Y_local = -GLASS_CAV_H/2 (屏底边);  z_local = FRONT_WALL_T + SCREEN_T (玻璃背面)
fpc_exit = to_world(0, -E.GLASS_CAV_H / 2, E.FRONT_WALL_T + E.SCREEN_T)
# 屏底边铰接点(参考)
hinge = to_world(0, -E.BEZEL_OUT_H / 2, E.BEZEL_DEPTH)

# PCB 显示排座 (整机坐标): 前侧 -Y, X=0, PCB 顶面
pcb_top_z = E.BASE_FLOOR_T + E.STANDOFF_H + E.PCB_T   # 2+4+1.6 = 7.6
conn = Vector(0, E.FPC_CONN_Y, pcb_top_z + 1.5)        # 排座座体约+1.5

print(f"屏 FPC 出线点 (整机坐标): ({fpc_exit.X:.1f}, {fpc_exit.Y:.1f}, {fpc_exit.Z:.1f})")
print(f"屏底铰接点:               ({hinge.X:.1f}, {hinge.Y:.1f}, {hinge.Z:.1f})")
print(f"PCB 显示排座:             ({conn.X:.1f}, {conn.Y:.1f}, {conn.Z:.1f})")
d_exit = (conn - fpc_exit).length
d_hinge = (conn - hinge).length
print(f"\n出线点 -> 排座 直线距离 = {d_exit:.1f} mm")
print(f"铰接点 -> 排座 直线距离 = {d_hinge:.1f} mm")
print(f"裸露弯折段 FPC_EXPOSED = {E.FPC_EXPOSED} mm (规格书标注的可弯折段)")
print(f"\n判断: FPC 实际可用长度需 >= 直线距离 + 弯折余量. 若总长仅 ~{E.FPC_EXPOSED+15:.0f}mm 量级,")
print(f"      而需跨 {d_exit:.0f}mm, 则可能不够 -> 需把 PCB/排座前移靠近出线点.")
