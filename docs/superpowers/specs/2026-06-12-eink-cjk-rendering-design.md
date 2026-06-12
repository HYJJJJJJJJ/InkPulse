# 墨水屏汉字显示优化 · 设计记录

- 日期: 2026-06-12
- 分支: `feat/eink-cjk-font-eval`
- 状态: 候选已产出, 待真机验证拍板

## 背景与问题

7.5" 三色墨水屏 E075A42 / UC8179, 800×480, 黑/白/红三色, **无灰阶**, 全刷。
汉字渲染在 PC 端 Hub(Pillow)完成, 设备只整屏 blit。

主诉: 汉字"显示效果差"。经真实样张定位, 痛点是两项(用户确认):
- **B 边缘锯齿毛糙**: 斜笔/弧线呈台阶状。
- **C 笔画偏细、整体发灰**: 远看不够黑、对比度低。

根因**不是分辨率**(~133 DPI 不低), 而是渲染方式: `render/engine.py` 设
`d.fontmode = "1"` 关掉抗锯齿——因为三色屏无灰阶, 抗锯齿灰边会在 `to_planes`
(严格等于黑/白/红才取色)时丢失, 反而让小字发虚。于是只能纯 1-bit, 斜笔必锯齿、笔画必细。

## 关键约束

- 三色严格量化: 帧里每个像素必须**恰好** = 白/黑/红, 否则 `to_planes` 丢像素。
- 设备帧 = 96000B(48000 黑plane + 48000 红plane), `/frame` 带 ETag 去重、304 不刷。
- PC 预览 ≠ 真机观感(对比度/残影/可视角), **必须真机验证**。
- 渲染在 Hub(PC)端, 可自由用任意字体/算法, 不受 MCU 资源限制。

## 探索过的方向(真实渲染对比)

1. 换粗字重(Medium 阈值): 治 C, 不治 B。
2. 抗锯齿→Floyd-Steinberg 抖动: 治 B, 但小字抖动噪点、发"麻"。
3. 超采样+粗体+锐化阈值: B+C 都缓解, **但密集横笔字(量/输/赢)易糊**(用户实测确认)。
4. 专用像素字库: 12px 网格逐像素手工设计, 笔画缝由设计师保住, 密集字也不糊;
   代价是复古点阵风、仅整数倍字号最干净。

## 决定: 3 候选交真机定夺

不在 PC 上拍板, 产出 3 个设备帧让 partner 上真机比对:

| ID | 方案 | 取向 | 取舍 |
|----|------|------|------|
| **A** | 方舟像素 12px + 大字 24px | 最锐/最省空间 | 字小、复古风 |
| **C** | 方舟像素 24px + 大字 48px | 像素干净且醒目 | 占空间多 |
| **D** | 黑体 Medium 超采样4×+锐化阈值 | 保留现代黑体 | 密集字偏糊 |

字体: 方舟像素 Ark Pixel(SIL OFL 1.1, 可分发/嵌入)。
**排除 Zpix 最像素**(商业付费字体, 禁止再分发)。

## 交付物(本分支)

- `software/hub/tools/font_eval/render_candidates.py` — 离屏渲染 3 候选(复用生产 `pack_frame`)
- `software/hub/tools/font_eval/serve_candidate.py` — 按设备 `/frame` 契约喂帧的验证服务
- `software/hub/tools/font_eval/out/candidate_{A,C,D}.{png,bin}` — 预览图 + 设备帧
- `software/hub/tools/font_eval/fonts/` — 方舟像素 TTF + OFL 许可证
- `software/hub/tools/font_eval/README.md` — 验证步骤

## 真机验证(partner)

```bash
cd software/hub
# 停掉真 Hub(占 8080) 后, 依次:
python3 tools/font_eval/serve_candidate.py A   # 设备 ≤60s 自动刷屏, 拍照
python3 tools/font_eval/serve_candidate.py C
python3 tools/font_eval/serve_candidate.py D
```

设备 `HUB_FRAME_URL` 指向运行机 `:8080` 即可, 无需改固件。切换候选 etag 变, 设备自动刷新。

## 验收标准

真机上对比 A/C/D, 重点看:
1. 锯齿是否可接受(B)。
2. 密集字"量/输/赢/躁/囊"笔画是否清晰不糊(核心)。
3. 整体黑度/对比度是否醒目(C)。
4. 信息密度: 字号是否过小/布局是否够用。

## 选定后(下一步, 不在本分支)

把胜出策略落进生产 `render/`: 字体路径 + 字号映射(像素字库走整数倍), 若选 D 补超采样阈值
路径; 更新 `engine.py`/`widgets.py`; 删除或保留本评测目录为回归基准。
