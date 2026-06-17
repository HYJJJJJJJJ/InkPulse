"""核查: bezel 唇是否遮挡墨水屏可视区 AA."""
import importlib.util as ilu
from build123d import Pos, BuildPart, Box, Locations, Align

spec = ilu.spec_from_file_location("E", "cad/enclosure_426.py")
E = ilu.module_from_spec(spec); spec.loader.exec_module(E)
E.make_bracket()                 # 填充 make_bracket.mate
place = E.body_placement()

# AA 实体 (世界): 装配里屏居中, AA 在屏内上偏 WINDOW_OFFSET_Y
with BuildPart() as _aa:
    with Locations((0, E.WINDOW_OFFSET_Y, E.FRONT_WALL_T)):
        Box(E.AA_W, E.AA_H, E.SCREEN_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
aa = place * _aa.part
bezel = place * E.make_bezel()


def iv(a, b):
    v = 0.0
    for sa in (a.solids() or [a]):
        for sb in (b.solids() or [b]):
            r = sa & sb; vol = getattr(r, "volume", None)
            if vol and vol > 1e-9: v += vol
    return v


print("=== bezel(含唇) ∩ AA 可视区体 ===")
v = iv(bezel, aa)
print(f"   bezel ∩ AA = {v:.4f} mm³  -> {'唇遮挡了 AA!' if v > 0.01 else '未遮挡 (唇不进 AA)'}")

print("\n=== 视窗开口 vs AA 逐边余量 (局部, 屏体) ===")
# 视窗: WINDOW_W×WINDOW_H, X 居中, Y 偏 WINDOW_OFFSET_Y
win_x0, win_x1 = -E.WINDOW_W / 2, E.WINDOW_W / 2
win_y0 = E.WINDOW_OFFSET_Y - E.WINDOW_H / 2
win_y1 = E.WINDOW_OFFSET_Y + E.WINDOW_H / 2
aa_x0, aa_x1 = -E.AA_W / 2, E.AA_W / 2
aa_y0 = E.WINDOW_OFFSET_Y - E.AA_H / 2
aa_y1 = E.WINDOW_OFFSET_Y + E.AA_H / 2
print(f"   AA   X[{aa_x0:.2f},{aa_x1:.2f}] Y[{aa_y0:.2f},{aa_y1:.2f}]  ({E.AA_W}×{E.AA_H})")
print(f"   视窗 X[{win_x0:.2f},{win_x1:.2f}] Y[{win_y0:.2f},{win_y1:.2f}]  ({E.WINDOW_W}×{E.WINDOW_H})")
print(f"   每边余量(视窗比AA大出, >0 才不遮挡):")
print(f"     左 {aa_x0-win_x0:+.3f}  右 {win_x1-aa_x1:+.3f}  下 {aa_y0-win_y0:+.3f}  上 {win_y1-aa_y1:+.3f} (mm)")
print(f"   WINDOW_MARGIN={E.WINDOW_MARGIN} (总余量, 单边 = /2 = {E.WINDOW_MARGIN/2})")
print(f"\n   注: WINDOW_OFFSET_Y={E.WINDOW_OFFSET_Y} 是'待实测'值(设计§8). 若实物 AA 纵向位置与此差 >{E.WINDOW_MARGIN/2}mm, 唇会压住 AA 上/下沿.")
