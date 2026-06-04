"""独立复验: PCB前移+盖板后抽 后的关键碰撞/间隙/FPC跨度。"""
import sys, math
sys.path.insert(0, "cad")
import enclosure as E
from build123d import import_step, Pos, Rot, Vector

base = E.make_base(); lid = E.make_lid()
print("CORE_CY=%.1f  FPC_CONN_Y=%.1f  LID_BOT_Z=%.2f  BASE_WALL_H=%.2f  TYPEC_H=%.2f  TYPEC_CENTER_Z=%.2f"
      % (E.CORE_CY, E.FPC_CONN_Y, E.LID_BOT_Z, E.BASE_WALL_H, E.TYPEC_H, E.TYPEC_CENTER_Z))

# 放置真实 PCB: 重定心 -> 翻Y(Type-C朝+Y) -> 抬到螺柱顶 -> 沿+Y移 CORE_CY
pcb = import_step("hardware/PCB1.step"); sol = pcb.solids()
bd = max([s for s in sol if s.bounding_box().size.Z < 3],
         key=lambda s: s.bounding_box().size.X * s.bounding_box().size.Y)
b = bd.bounding_box(); ox, oy, oz = (b.min.X+b.max.X)/2, (b.min.Y+b.max.Y)/2, b.min.Z
zlift = E.BASE_FLOOR_T + E.STANDOFF_H
loc = Pos(0, E.CORE_CY, zlift) * Rot(0, 0, 180) * Pos(-ox, -oy, -oz)
pcb_p = loc * pcb

bbp = pcb_p.bounding_box()
print("\nPCB放置后 bbox: X %.1f..%.1f  Y %.1f..%.1f  Z %.1f..%.1f"
      % (bbp.min.X, bbp.max.X, bbp.min.Y, bbp.max.Y, bbp.min.Z, bbp.max.Z))
comp_top = bbp.max.Z

# 1) FPC 跨度
exit_pt = Vector(0, -47, 8); conn = Vector(0, E.FPC_CONN_Y, zlift+E.PCB_T+1.5)
print("1) FPC 跨度 = %.2f mm  %s" % ((conn-exit_pt).length, "OK" if (conn-exit_pt).length<=16 else "超!"))

# 2) base ∩ PCB
try:
    iv = (base & pcb_p).volume
except Exception as e:
    iv = -1
print("2) base ∩ PCB = %.3f mm³  %s" % (iv, "OK" if abs(iv)<1 else "干涉!"))

# 3) lid ∩ PCB
try:
    il = (lid & pcb_p).volume
except Exception:
    il = -1
print("3) lid  ∩ PCB = %.3f mm³  %s" % (il, "OK" if abs(il)<1 else "干涉!"))

# 4) 盖板底 vs 元件顶
print("4) 盖板底 %.2f  元件顶 %.2f  余量 %.2f  %s"
      % (E.LID_BOT_Z, comp_top, E.LID_BOT_Z-comp_top, "OK" if E.LID_BOT_Z>comp_top else "压穿!"))

# 5) 螺柱 vs 真实孔 (打印 PCB 放置后四角附近; 简单报 standoff 目标)
print("5) 螺柱目标 (±30, %.0f)/(±30, %.0f)" % (E.CORE_CY+E.M3_POS_Y, E.CORE_CY-E.M3_POS_Y))
