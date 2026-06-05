"""装配体各件两两干涉检查。"""
import sys, math
sys.path.insert(0, "cad")
import enclosure as E
from build123d import Pos, Rot, Vector

bezel = E.make_bezel(); back = E.make_back_cover(); base = E.make_base(); lid = E.make_lid()

run = E.GUSSET_HEIGHT / math.tan(math.radians(E.ANGLE_DEG))
A = Vector(0, -E.BASE_FOOT_D/2, E.BASE_FOOT_T)
R = Rot(-120, 0, 0) * Rot(0, 0, 180)
T = A - (R * Pos(0, -E.BEZEL_OUT_H/2, E.BEZEL_DEPTH + E.BACK_COVER_PLATE_T)).position
bezel_a = Pos(T.X, T.Y, T.Z) * R * bezel
back_a = Pos(T.X, T.Y, T.Z) * R * (Pos(0, 0, E.BEZEL_DEPTH + E.BACK_COVER_PLATE_T) * Rot(0, 180, 0) * back)
base_a = base
lid_a = lid

parts = [("base", base_a), ("bezel", bezel_a), ("back_cover", back_a), ("lid", lid_a)]
print("装配体各件两两干涉体积 (mm³):")
for i in range(len(parts)):
    for j in range(i+1, len(parts)):
        n1, p1 = parts[i]; n2, p2 = parts[j]
        try:
            v = (p1 & p2).volume
        except Exception as e:
            v = f"ERR({e})"
        flag = ""
        if isinstance(v, float):
            flag = "  <<< 冲突!" if v > 1.0 else "  ok"
        print(f"  {n1:11s} ∩ {n2:11s} = {v if isinstance(v,str) else f'{v:10.2f}'}{flag}")

# 各件在装配坐标的 bbox, 帮助定位
print("\n装配坐标 bbox:")
for n, p in parts:
    b = p.bounding_box()
    print(f"  {n:11s} X {b.min.X:7.1f}..{b.max.X:6.1f}  Y {b.min.Y:7.1f}..{b.max.Y:6.1f}  Z {b.min.Z:6.1f}..{b.max.Z:6.1f}")
