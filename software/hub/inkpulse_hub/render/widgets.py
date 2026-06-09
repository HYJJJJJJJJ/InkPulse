# inkpulse_hub/render/widgets.py
from dataclasses import dataclass
from PIL import ImageDraw, ImageFont
from ..models import ClaudeStatus, Usage, TodoItem

BLACK = (0, 0, 0)
RED = (255, 0, 0)

STATE_LABEL = {
    "idle": "空闲",
    "working": "工作中",
    "waiting_for_input": "等你输入",
    "done": "刚完成",
    "error": "出错",
}


@dataclass
class Zone:
    x: int
    y: int
    w: int
    h: int

# 优先 CJK 字体，保证 /preview.png 能显示中文。
# PingFang 在部分 macOS 版本/路径下不一定存在，故附带 STHeiti 作为 CJK 兜底，
# 再退到 DejaVuSans（无中文字形）与 Pillow 默认位图字体。
_CJK_FONT_PATHS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]


def _font(size: int) -> ImageFont.ImageFont:
    for path in _CJK_FONT_PATHS:
        try:
            return ImageFont.truetype(path, size, index=0)
        except OSError:
            continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def draw_header(d: ImageDraw.ImageDraw, z: Zone, clock_text: str, temp, humidity) -> None:
    f = _font(22)
    d.text((z.x + 6, z.y + 8), clock_text, fill=BLACK, font=f)
    t = f"{temp:.0f}C" if temp is not None else "n/a"
    h = f"{humidity:.0f}%" if humidity is not None else "n/a"
    d.text((z.x + z.w - 160, z.y + 8), f"{t}  {h}", fill=BLACK, font=f)
    d.line((z.x, z.y + z.h - 1, z.x + z.w, z.y + z.h - 1), fill=BLACK, width=1)


def draw_claude_status(d: ImageDraw.ImageDraw, z: Zone, s: ClaudeStatus) -> None:
    big = _font(48)
    small = _font(22)
    color = RED if s.needs_attention() else BLACK
    # 状态色指示块：不依赖字体字形(默认字体可能缺中文)，保证状态色一定可见
    d.rectangle((z.x + 12, z.y + 24, z.x + 36, z.y + 48), fill=color)
    label = STATE_LABEL.get(s.state, s.state)
    d.text((z.x + 48, z.y + 20), label, fill=color, font=big)
    proj = f"project: {s.project}" if s.project else "-"
    d.text((z.x + 12, z.y + 90), proj, fill=BLACK, font=small)


def draw_usage(d: ImageDraw.ImageDraw, z: Zone, u: Usage) -> None:
    f = _font(22)
    d.text((z.x + 8, z.y + 8), "今日用量", fill=BLACK, font=f)
    d.text((z.x + 8, z.y + 40), f"{u.total_tokens()} tok", fill=BLACK, font=f)
    d.text((z.x + 8, z.y + 72), f"≈ ${u.cost_usd:.2f}", fill=BLACK, font=f)
    if u.window_used_ratio is not None:
        bx, by, bw, bh = z.x + 8, z.y + 110, z.w - 24, 18
        d.rectangle((bx, by, bx + bw, by + bh), outline=BLACK, width=1)
        fillw = int(bw * max(0.0, min(1.0, u.window_used_ratio)))
        d.rectangle((bx, by, bx + fillw, by + bh), fill=BLACK)
    else:
        d.text((z.x + 8, z.y + 110), "窗口 n/a", fill=BLACK, font=f)


def draw_todos(d: ImageDraw.ImageDraw, z: Zone, items: list[TodoItem]) -> None:
    f = _font(22)
    y = z.y + 6
    for t in items[:4]:
        box = "[x]" if t.done else "[ ]"
        d.text((z.x + 8, y), f"{box} {t.text}", fill=BLACK, font=f)
        y += 34
