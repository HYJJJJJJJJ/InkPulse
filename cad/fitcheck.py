"""把真实 PCB1.step 放进底座做装配核对 + 合成渲染。"""
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from build123d import import_step
import enclosure as E

# --- 底座 ---
base = E.make_base()
bb = base.bounding_box()
print(f"base bbox {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f}  valid={base.is_valid}")
print(f"PCB 仓 (内腔) X +-{E.BASE_INNER_W/2:.2f}  Y +-{E.BASE_INNER_D/2:.2f}  深 {E.BASE_INNER_H}")
print(f"螺柱 (±{E.M3_POS_X}, ±{E.M3_POS_Y}) 柱顶 z={E.BASE_FLOOR_T+E.STANDOFF_H}")
print(f"Type-C 开口: +Y壁, 中心z={E.TYPEC_CENTER_Z:.2f}, 宽{E.TYPEC_W} 高{E.TYPEC_H}")

# --- 真实 PCB: 重定心(板中心->原点, 板底->z0), 再翻Y(Type-C朝+Y), 抬到螺柱顶 ---
pcb = import_step("/Users/huangyongjie/Workspace/xmut/InkPulse/hardware/PCB1.step")
sol = pcb.solids()
def board_of(sol):
    cands=[s for s in sol if s.bounding_box().size.Z<3]
    return max(cands, key=lambda s:s.bounding_box().size.X*s.bounding_box().size.Y)
bd=board_of(sol); bbb=bd.bounding_box()
ox,oy,oz=(bbb.min.X+bbb.max.X)/2,(bbb.min.Y+bbb.max.Y)/2,bbb.min.Z
z_lift=E.BASE_FLOOR_T+E.STANDOFF_H   # PCB 底坐到螺柱顶

# 采样所有 solid 顶点(粗), 应用变换: 重定心 -> 翻Y(x->-x,y->-y) -> 抬z
pts=[]
for s in sol:
    try: v,f=s.tessellate(1.2)
    except Exception: continue
    for p in v: pts.append((p.X,p.Y,p.Z))
P=np.array(pts)
P[:,0]-=ox; P[:,1]-=oy; P[:,2]-=oz       # 重定心
P[:,0]*=-1; P[:,1]*=-1                    # 翻Y(绕Z 180): Type-C -> +Y
P[:,2]+=z_lift                            # 抬到螺柱顶
print(f"\nPCB 放置后: X {P[:,0].min():.1f}~{P[:,0].max():.1f}  Y {P[:,1].min():.1f}~{P[:,1].max():.1f}  Z {P[:,2].min():.1f}~{P[:,2].max():.1f}")
print(f"  pocket X 容许 ±{E.BASE_INNER_W/2:.1f}, Y 容许 ±{E.BASE_INNER_D/2:.1f}  => "
      f"{'OK' if P[:,0].max()<=E.BASE_INNER_W/2+.1 and P[:,1].max()<=E.BASE_INNER_D/2+.1 else '超出!'}")

# --- 合成渲染 (base 网格 + PCB 点) ---
bv=[]
for s in base.solids():
    v,f=s.tessellate(1.0)
    for p in v: bv.append((p.X,p.Y,p.Z))
B=np.array(bv)
fig=plt.figure(figsize=(13,6))
ax=fig.add_subplot(121,projection='3d')
ax.scatter(B[:,0],B[:,1],B[:,2],s=1,c='#bbbbbb',alpha=.25)
ax.scatter(P[:,0],P[:,1],P[:,2],s=1,c='#2e7d32',alpha=.5)
ax.set_box_aspect((1,1,.6)); ax.view_init(elev=22,azim=-60)
ax.set_title('PCB(green) in base(gray)'); ax.set_xlabel('X');ax.set_ylabel('Y');ax.set_zlabel('Z')
# 俯视
ax2=fig.add_subplot(122)
ax2.scatter(B[:,0],B[:,1],s=1,c='#bbbbbb',alpha=.3)
ax2.scatter(P[:,0],P[:,1],s=1,c='#2e7d32',alpha=.4)
for sx in (E.M3_POS_X,-E.M3_POS_X):
    for sy in (E.M3_POS_Y,-E.M3_POS_Y): ax2.plot(sx,sy,'rx',ms=8)
ax2.set_aspect('equal'); ax2.grid(alpha=.3); ax2.set_title('Top: holes(red x)=standoffs'); ax2.set_xlabel('X');ax2.set_ylabel('Y')
plt.tight_layout(); plt.savefig('/Users/huangyongjie/Workspace/xmut/InkPulse/cad/output/fitcheck.png',dpi=110); print('saved cad/output/fitcheck.png')
