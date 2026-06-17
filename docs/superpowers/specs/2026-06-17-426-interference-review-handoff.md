# InkPulse 4.26" 外壳 — 实体干涉 Review 交接文档

- 日期：2026-06-17
- 目的：把 4.26" 磁吸侧挂外壳的**实体干涉问题**交给独立 session 做彻底 review。当前模型经多轮迭代，外壳/屏/PCB/磁铁/POGO/Type-C 之间仍有干涉，需系统性审计、定位根因、给出修复建议。
- 设计依据（必读）：[`docs/superpowers/specs/2026-06-16-inkpulse-426-magnetic-dock-design.md`](./2026-06-16-inkpulse-426-magnetic-dock-design.md)

---

## 1. 环境与文件

- conda 环境 **`cad`**（build123d 0.10.0）。每条命令前 `source ~/miniforge3/etc/profile.d/conda.sh && conda activate cad`。**禁止 pip 安装**，缺依赖向用户索取。
- **从仓库根运行**：`python cad/enclosure_426.py`（生成 + 自检）、`python cad/render_preview_426.py`（预览）。
- 关键文件：
  - `cad/enclosure_426.py` — 参数化建模 + 自检（**唯一建模源**）。
  - `cad/render_preview_426.py` — 多视图预览。
  - `cad/output/426/{bezel,back_cover,bracket}.{step,stl}` + `assembly_{print,context}.step` + `preview_426.png`。
  - `hardware/PCB1.step`（真实驱动板，元件高度参考）、`hardware/docs/*`（屏/POGO/Type-C 规格图）。

## 2. 坐标系

世界系：**X+ 朝显示器（右）**；**Y+ 上**（显示器顶/墨水屏顶 ≈ Y=0，屏体向下延伸）；**Z+ 朝用户**（墨水屏前表面 Z=0，向 −Z 叠厚度，结构藏屏后）。屏体局部系 z=0 在前面板正面、向 +z 入背腔；装配经 `body_placement()`（含 `Rot(0,180,0)`）翻转到世界。后盖另经 `back_cover_local()`（`Pos(0,0,BODY_T_ACTUAL)*Rot(0,180,0)`）翻转。

## 3. 实体清单（11 个参与干涉的实体 + 以"腔"存在的特征）

**打印件**：`bezel`（前框托盘+唇+4角M2螺柱boss+视窗）、`back_cover`（盖板+plug凸台+PCB支柱+定位销+磁腔+POGO配对腔）、`bracket`（卡钉+直支柱+对接板+POGO凹腔+Type-C壳块+走线腔+磁腔）。

**参考/装配模拟体**：`screen`（墨水屏 62.37×105.33×1.0）、`pcb`（60×95×1.6）、`comp`（元件包络）、`pads`（4 pogo 接触 pad）、`fpc`（24P 排座）、`pogo`（支架 POGO 连接器实体）、`typec`（防水 Type-C 母座实体）、`monitor`（显示器左上角参考块）。

**⚠️ 以"腔"存在、未作为实体参与干涉矩阵（reviewer 必须补建实体再查）**：
- **8×Φ8×3 磁铁**（后盖 4 + 支架 4）：当前是 `Mode.SUBTRACT` 的盲腔，没有"磁铁实体"。**review 必须在 `MAG_POSITIONS`/`mate['mag_world']` 处建 Φ8×3 圆柱实体**，检查磁铁是否与 PCB/元件/屏/POGO/对方磁/走线腔干涉、是否真能装入。
- **POGO 的 N/S 磁、4 pogo 针**：在连接器实体内，但 pogo↔back_cover 配对腔、pogo 针↔pad 的接触/间隙需单列核查。
- bezel 4 角 M2 螺柱 boss、后盖 PCB 支柱/定位销：是 bezel/back_cover 的一部分，但**历史上多次戳屏/戳板**，需单独点探。

## 4. 在内存里复现 world 放置（review 必用——避开导出 STEP 误判）

```python
import importlib.util as ilu
from build123d import Pos
spec=ilu.spec_from_file_location("E","cad/enclosure_426.py"); E=ilu.module_from_spec(spec); spec.loader.exec_module(E)
bracket=E.make_bracket()                      # 必须先调用以填充 make_bracket.mate
place=E.body_placement()
p=E.make_pcba()                               # dict: pcb/comp/pads/fpc/comp_w/comp_h
B={
 "bezel":      place*E.make_bezel(),
 "back_cover": place*(E.back_cover_local()*E.make_back_cover()),
 "bracket":    bracket,                        # bracket 直接建在世界系
 "screen":     place*(Pos(0,0,E.FRONT_WALL_T+E.SCREEN_T/2)*E.make_screen_ref()),
 "pcb":  place*p["pcb"], "comp": place*p["comp"], "pads": place*p["pads"], "fpc": place*p["fpc"],
 "pogo":  E.make_pogo_connector(),             # 世界原位
 "typec": E.make_typec_receptacle(),           # 世界原位
 "monitor": E.make_monitor_corner(),
}
def iv(a,b):                                   # 稳健: 分解到单实体两两求交
    v=0.0
    for sa in (a.solids() or [a]):
        for sb in (b.solids() or [b]):
            r=sa&sb; vol=getattr(r,"volume",None)
            if vol: v+=vol
    return v
```

## 5. 当前干涉基线（2026-06-17，内存真实相交，>0.5mm³）

| 对 | 体积 mm³ | 初判 |
|---|---|---|
| comp ∩ fpc | 42.0 | 多半建模假象（FPC 排座落在元件包络内，二者都是板上抽象块）——需确认是否双重计入 |
| bracket ∩ typec | 11.56 | **待查**：Type-C 母座实体 vs 支架壳体，应为间隙配合，11.56 偏大 |
| back_cover ∩ fpc | 10.50 | **待查**：板底 24P 排座（z=4.1–5.6 凸出）可能撞后盖 plug/支柱 |
| comp ∩ pads | 3.62 | 建模假象（pad 在元件区 z 内） |
| bracket ∩ pogo | 2.76 | POGO 实体 vs 凹腔，应为配合，需确认是否过盈 |

> 注：此矩阵**未含磁铁实体**（见 §3 ⚠️）。用户反馈"干涉还是很严重"，可能涉及磁铁实体、连接器 vs 壳体配合、或下述历史易错点。**不要以此 5 对为全集**——按 §7 重新穷举。

## 6. "设计内接触" vs "真干涉"（分类基线，避免误报/漏报）

判为**设计内接触**（≈0 或薄接触，正常）：plug rim 贴 PCB 背沿（预压已改 0）、PCB 支柱顶 vs PCB 背、磁铁底 vs 腔底、pogo 针尖 vs pad（接触受电）、卡钉抱边 vs 显示器（0.3 间隙）、前舌压黑边。
判为**真干涉**（须修）：任何实体侵入墨水屏 AA/玻璃体、螺柱/支柱/定位销戳屏或戳板元件、连接器本体撞壳壁（非配合腔）、磁铁实体撞 PCB/元件/对方、走线腔/凹腔切穿不该穿的壁、屏戳出屏腔/外壳。

## 7. 历史易错点 & 验证坑（务必避开）

1. **导出 STEP 后再 import 做 pairwise 相交会误判 0**（多次把真碰撞报成 0，例：M2 螺柱戳屏曾被导出 STEP pairwise 报 0、却被内存点探确认戳屏）。**一律用 §4 的内存单实体相交 + 点探**，并与导出 STEP 交叉对照。
2. **`make_pcba()` 返回 dict**（非实体），取 `p['pcb'/'comp'/'pads'/'fpc']`。
3. **装配翻转 `Rot(0,180,0)` 会镜像 X**：后盖/屏体上的特征（Type-C、定位销、磁、POGO）局部 X 映射到世界要乘 −1，历史上多次因此对错位/切错壁。
4. **磁铁、POGO 针是“腔/连接器内”特征**，默认不在实体集里——必须显式补建实体再查（§3）。
5. **共面布尔毛刺**：屏前面 z=1.0 与屏腔底共面会产生薄壳假相交（~数十 mm³），用"缩 0.1mm 的测试体"或点探区分真假。
6. 历史已修但需回归确认：螺柱戳屏（已加宽边框移屏外）、PCB 支柱戳屏（已移后盖）、Type-C 切薄板无壳（已建壳块 boss）、后盖磁腔两头封死（已开内侧）、POGO 焊面埋死（已改背面装入）、plug 撞 PCB/元件（已按 PCB 派生、预压0）。**review 要确认这些没回退**。

## 8. Review 交付要求

1. 用 §4 方法（含补建磁铁/针实体）穷举**所有实体两两干涉矩阵**，每对给体积 + 相交区 bbox + 截图/截面。
2. 每个 >阈值 的对：判定"设计内接触"还是"真干涉"，给**根因**（哪个特征、哪个参数、哪行代码）。
3. 对真干涉给**可制造性结论**（能否装入/装配顺序）与**修复建议**（改哪个参数/几何，预计副作用）。
4. 单独核查 §3 ⚠️ 的磁铁实体、POGO 配对接触、螺柱/支柱/定位销点探。
5. 回归 §7.6 历史项未回退。
6. 产出一份干涉审计报告（矩阵 + 根因 + 修复优先级），不直接改模型（除非用户要求）。

---

## 9. Review 提示词（复制到新 session）

```
你是资深 3D 结构/CAD 干涉审计工程师。对 InkPulse 4.26" 磁吸侧挂外壳做一次彻底的实体干涉 review，只审计与定位、不擅自改模型（除非我要求）。

环境：conda 环境 `cad`(build123d 0.10.0)，从仓库根运行，禁止 pip 安装。
先读：docs/superpowers/specs/2026-06-17-426-interference-review-handoff.md（本交接文档，含坐标系/实体清单/world放置配方/已知干涉基线/验证坑）与 docs/superpowers/specs/2026-06-16-inkpulse-426-magnetic-dock-design.md（设计依据）。建模源：cad/enclosure_426.py。

任务：
1. 用交接文档 §4 的"内存单实体相交"配方（先 make_bracket() 填 mate）复现 world 装配，穷举所有实体两两干涉矩阵（含 bezel/back_cover/bracket/screen/pcb/comp/pads/fpc/pogo/typec/monitor）。**额外补建实体**：8×Φ8×3 磁铁（在 MAG_POSITIONS / make_bracket.mate['mag_world'] 处建圆柱）、POGO 4 针/N-S 磁，纳入矩阵。
2. ⚠️ 不要信任"导出 STEP 再 import 的 pairwise"（会误判 0，见 §7.1）。一律内存相交 + 关键点探，并与导出 STEP 交叉对照，发现不一致要追因。
3. 每个 >0.5mm³ 的干涉对：给 体积 + 相交区 bbox；判定"设计内接触(§6)"还是"真干涉"；定位根因到具体特征/参数/代码行。
4. 重点核查（历史易错，见 §7.6 回归 + §3 ⚠️）：M2 螺柱/PCB 支柱/定位销是否戳屏或戳板元件；Type-C 母座 vs 支架壳体配合(基线11.56)；24P 排座 vs 后盖(基线10.5)；POGO 本体 vs 凹腔/配对腔、pogo针 vs pad；8 磁实体 vs PCB/元件/屏/对方磁/走线腔、磁能否装入；屏是否被完整包住且 AA 不被唇遮挡；Rot(0,180,0) 镜像导致的对位错。
5. 对每个真干涉给：可制造性/装配顺序结论 + 修复建议（改哪个参数/几何 + 预计副作用）。
6. 产出《干涉审计报告》：完整矩阵 + 真干涉清单(按严重度排序) + 根因 + 修复优先级。必要处附截面/点探数值佐证。不改模型，等我确认修复方案。
```
