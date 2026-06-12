#!/usr/bin/env python3
"""墨水屏汉字渲染 —— 候选方案离屏渲染器(用于真机验证)。

为同一份 demo 内容渲染 3 个候选, 各产出:
  out/<id>.png   预览图(电脑上看个大概)
  out/<id>.bin   设备帧(96000B = 黑plane + 红plane, 直接喂给真机)

候选(对应 brainstorm 里点选的 A / C / D):
  A  arkpixel12   方舟像素 12px 原生 + 大字 24px   —— 最锐、最省空间、复古点阵
  C  arkpixel24   方舟像素 24px(2×) + 大字 48px    —— 像素干净且更醒目, 占空间多
  D  superbold    黑体 Medium 超采样 4× + 锐化阈值 —— 现代黑体, 笔画饱满(密集字可能偏糊)

三色屏只有 黑/白/红, 无灰阶: A/C 直接 1-bit 渲染出严格三色;
D 走超采样→下采样→阈值, 最后量化到严格三色, 保证 to_planes 不丢像素。

字体许可: 方舟像素 = SIL OFL 1.1(可自由分发/嵌入, 见 fonts/ark-pixel-OFL.txt)。
注意: Zpix(最像素) 为商业付费字体, 禁止再分发, 故未采用。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# 复用生产管线的打帧逻辑, 保证 .bin 与真 Hub 字节级一致
_HUB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _HUB_ROOT)
from inkpulse_hub.render.planes import pack_frame, frame_etag, WIDTH, HEIGHT  # noqa: E402

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
ARK = os.path.join(_FONT_DIR, "ark-pixel-12px-proportional-zh_cn.ttf")
# D 方案的黑体(Medium 字重); 烘焙 out/ 时在 macOS 上跑, 用系统黑体即可。
_BOLD_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf",
]


def _bold_path() -> str:
    for p in _BOLD_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("找不到 D 方案所需的黑体, 请安装 Noto Sans CJK 或在 macOS 上运行")


# ---- demo 内容: 故意塞入密集横笔的字(量/输/赢/躁/囊)来压测 ----
DEMO = {
    "clock": "14:32  6月12日",
    "env": "26C  58%",
    "status_red": True,          # 等你输入 -> 红色, 顺便压测红 plane
    "status_label": "等你输入",
    "project": "项目 墨水屏·汉字渲染(量/输/赢/躁)",
    "usage_title": "今日用量",
    "usage_tokens": "1,234,567 tok",
    "usage_cost": "≈ $34.56",
    "usage_ratio": 0.63,
    "todos": [
        ("[ ]", "评估像素字库:量、输、赢、躁、囊"),
        ("[x]", "修复湿度传感器读数异常"),
        ("[ ]", "重构显示组件渲染路径"),
        ("[ ]", "压测固件三色刷新稳定性"),
    ],
}


class Painter:
    """统一的布局绘制器。S=1 直接 1-bit 出三色(像素字库);
    S>1 时超采样+抗锯齿, finalize 再下采样并量化到严格三色(D 方案)。"""

    def __init__(self, scale: int, font_path: str, small_px: int, big_px: int,
                 antialias: bool):
        self.S = scale
        self.img = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), WHITE)
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "L" if antialias else "1"
        self.small = ImageFont.truetype(font_path, small_px * scale, index=0)
        self.big = ImageFont.truetype(font_path, big_px * scale, index=0)

    def text(self, x, y, s, color, big=False):
        f = self.big if big else self.small
        self.d.text((x * self.S, y * self.S), s, fill=color, font=f)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1):
        S = self.S
        self.d.rectangle((x0 * S, y0 * S, x1 * S, y1 * S),
                         fill=fill, outline=outline, width=width * S)

    def line(self, x0, y0, x1, y1, color, width=1):
        S = self.S
        self.d.line((x0 * S, y0 * S, x1 * S, y1 * S), fill=color, width=width * S)

    def finalize(self) -> Image.Image:
        if self.S == 1:
            return self.img
        small = self.img.resize((WIDTH, HEIGHT), Image.LANCZOS)
        return _quantize_3color(small)


def _quantize_3color(img: Image.Image) -> Image.Image:
    """把下采样后的 RGB 量化到 严格 {白,黑,红}。阈值偏低=笔画更粗更黑。"""
    px = img.load()
    out = Image.new("RGB", img.size, WHITE)
    op = out.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = px[x, y]
            if r > 150 and g < 110 and b < 110:
                op[x, y] = RED
            elif (r + g + b) // 3 < 145:
                op[x, y] = BLACK
            # 否则保持白
    return out


def _paint(p: Painter):
    D = DEMO
    # header (0,0,800,60)
    p.text(6, 8, D["clock"], BLACK)
    p.text(800 - 200, 8, D["env"], BLACK)
    p.line(0, 59, 800, 59, BLACK, width=1)
    # claude_status (0,60,480,200)
    sc = RED if D["status_red"] else BLACK
    p.rect(12, 84, 36, 108, fill=sc)               # 状态色块
    p.text(48, 80, D["status_label"], sc, big=True)
    p.text(12, 150, D["project"], BLACK)
    # usage (480,60,320,200)
    p.text(488, 68, D["usage_title"], BLACK)
    p.text(488, 100, D["usage_tokens"], BLACK)
    p.text(488, 132, D["usage_cost"], BLACK)
    bx, by, bw, bh = 488, 170, 320 - 24, 18
    p.rect(bx, by, bx + bw, by + bh, outline=BLACK, width=1)
    p.rect(bx, by, bx + int(bw * D["usage_ratio"]), by + bh, fill=BLACK)
    # todos (0,260,800,220)
    y = 272
    for box, txt in D["todos"]:
        p.text(8, y, f"{box} {txt}", BLACK)
        y += 40


CANDIDATES = {
    "A_arkpixel12": dict(scale=1, font=ARK, small=12, big=24, antialias=False),
    "C_arkpixel24": dict(scale=1, font=ARK, small=24, big=48, antialias=False),
    "D_superbold":  dict(scale=4, font=None, small=22, big=48, antialias=True),
}


def render(cid: str) -> Image.Image:
    cfg = CANDIDATES[cid]
    font = cfg["font"] or _bold_path()
    p = Painter(cfg["scale"], font, cfg["small"], cfg["big"], cfg["antialias"])
    _paint(p)
    return p.finalize()


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    for cid in CANDIDATES:
        img = render(cid)
        png = os.path.join(out_dir, f"candidate_{cid}.png")
        img.save(png)
        body = pack_frame(img)
        assert len(body) == WIDTH // 8 * HEIGHT * 2, len(body)
        with open(os.path.join(out_dir, f"candidate_{cid}.bin"), "wb") as f:
            f.write(body)
        print(f"{cid:14s} png={png}  bin={len(body)}B  etag={frame_etag(body)}")


if __name__ == "__main__":
    main()
