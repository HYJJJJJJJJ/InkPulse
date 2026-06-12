# 墨水屏汉字渲染 · 候选方案真机验证

7.5" 三色墨水屏(800×480, 黑/白/红, 无灰阶)上汉字"锯齿毛糙 + 笔画偏细发灰"。
根因不是分辨率(~133 DPI), 而是渲染方式: 现生产管线 `engine.py` 用 `fontmode="1"`
关掉抗锯齿(三色屏无灰阶, 抗锯齿灰边会在三色量化时丢失), 导致斜笔锯齿、笔画发虚。

这里准备了 3 个候选, 渲染成**设备可直接显示的帧**, 交由真机拍板(PC 预览 ≠ 真机观感)。

## 三个候选

| ID | 方案 | 字体 | 取向 | 已知取舍 |
|----|------|------|------|----------|
| **A** | 方舟像素 12px 原生 + 大字 24px | Ark Pixel(OFL) | 最锐、最省空间 | 字偏小、复古点阵风 |
| **C** | 方舟像素 24px(2×) + 大字 48px | Ark Pixel(OFL) | 像素干净且醒目 | 占空间多 |
| **D** | 黑体 Medium 超采样 4× + 锐化阈值 | 系统黑体 | 保留现代黑体观感 | 密集横笔字(量/输/赢)易糊 |

- A/C 是像素字库路线: 每个字在 12px 网格上逐像素手工设计, 笔画间的缝是设计师刻意保住的,
  所以密集字在小尺寸下也不糊。像素字库只在**整数倍字号**(12/24/36…)下最干净。
- D 是非像素路线: 超采样+下采样+阈值, 边缘比直接 1-bit 干净, 但加粗会吃掉密集字的缝。

字体许可: 方舟像素 = SIL OFL 1.1(`fonts/ark-pixel-OFL.txt`, 可自由分发/嵌入/商用)。
> 注: Zpix(最像素) 视觉也合适, 但为**商业付费字体, 禁止再分发**, 故未采用。

## 产物

```
fonts/   ark-pixel-12px-proportional-zh_cn.ttf  + OFL 许可证
out/     candidate_{A,C,D}*.png   预览图(电脑上看)
         candidate_{A,C,D}*.bin   设备帧(96000B = 黑plane + 红plane, 真机直接显示)
```

`.bin` 用生产管线 `inkpulse_hub.render.planes.pack_frame` 打包, 与真 Hub 字节级一致。

## 真机验证步骤(partner)

设备固件里 `HUB_FRAME_URL = http://<HubIP>:8080/frame`。临时用本工具顶替真 Hub:

```bash
cd software/hub
# 1. 停掉正在跑的真 Hub(它占着 8080)
# 2. 在设备指向的那台机器上, 依次起每个候选:
python3 tools/font_eval/serve_candidate.py A     # 看候选 A
#   设备在 ≤60s 后自动拉帧刷屏; 拍照记录
# Ctrl-C 后换 C / D:
python3 tools/font_eval/serve_candidate.py C
python3 tools/font_eval/serve_candidate.py D
```

切换候选时 etag 改变, 设备会在下次轮询(`X-Next-Refresh=60s`)自动刷新。
浏览器看预览: `http://localhost:8080/preview.png`。

> 代理环境注意: 本机若设了 http_proxy, curl/设备同网段访问前 `unset http_proxy https_proxy`。

## 重新生成 out/(可选)

```bash
cd software/hub
python3 tools/font_eval/render_candidates.py
```

A/C 跨平台一致(字体随仓库)。D 用系统黑体, 不同机器字重略有差异;
out/ 里已提交的 D 帧是在 macOS(STHeiti Medium) 上烘焙的, 真机验证以**已提交的 .bin** 为准。

## 选定之后

真机选出 A/C/D 之一后, 再把对应策略落进生产 `render/`(字体路径 + 字号映射 +
若选 D 则补超采样阈值路径), 并删除本评测目录或保留为回归基准。
设计记录见 `docs/superpowers/specs/2026-06-12-eink-cjk-rendering-design.md`。
