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
# 跨平台 CJK 字体兜底：先 macOS，再 Linux 常见中文字体，
# 最后退到 DejaVuSans（无中文字形）与 Pillow 默认位图字体。
_CJK_FONT_PATHS = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Linux (文泉驿 / Noto CJK，apt 装 fonts-wqy-zenhei 或 fonts-noto-cjk)
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    # Windows (镜像/挂载场景兜底)
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
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
    # 湿度仅在有效范围 0~100% 才显示; 传感器损坏/读失败会传负值, 此时只显示温度,
    # 避免顶栏一直显示错误的 -6%。换好传感器后正常值会自动恢复显示。
    env = t
    if humidity is not None and 0 <= humidity <= 100:
        env = f"{t}  {humidity:.0f}%"
    d.text((z.x + z.w - 160, z.y + 8), env, fill=BLACK, font=f)
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
