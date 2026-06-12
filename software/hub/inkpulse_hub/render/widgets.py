# inkpulse_hub/render/widgets.py
from dataclasses import dataclass
from PIL import ImageDraw, ImageFont
from ..models import ClaudeStatus, Usage, TodoItem

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
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
# 选定(2026-06-12 真机验证): 全局思源黑 Medium(项目内置 fonts/), 找不到再回退系统字体。
import os as _os
_FONT_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "fonts")
_CJK_FONT_PATHS = [
    _os.path.join(_FONT_DIR, "SiYuanHei-Medium.otf"),   # ← 选定: 全局思源黑 Medium
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Linux (文泉驿 / Noto CJK)
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    # Windows (镜像/挂载场景兜底)
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


# 字体验证用: 运行时热切换字体, 不必重烧固件。
# 优先级: 显式 override > 环境变量 INKPULSE_FONT > 默认 _CJK_FONT_PATHS 列表。
_FONT_OVERRIDE: str | None = None


def set_font(path: str | None) -> None:
    """切换全局 CJK 字体文件路径(None=回到默认列表)。供 /debug/font 调用。"""
    global _FONT_OVERRIDE
    _FONT_OVERRIDE = path or None


def current_font() -> str:
    import os
    return _FONT_OVERRIDE or os.environ.get("INKPULSE_FONT") or "(default list)"


def _font(size: int) -> ImageFont.ImageFont:
    import os
    candidates = []
    if _FONT_OVERRIDE:
        candidates.append(_FONT_OVERRIDE)
    env = os.environ.get("INKPULSE_FONT")
    if env:
        candidates.append(env)
    candidates.extend(_CJK_FONT_PATHS)
    for path in candidates:
        try:
            return ImageFont.truetype(path, size, index=0)
        except OSError:
            continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _title_bar(d: ImageDraw.ImageDraw, z: Zone, text: str) -> int:
    """黑底白字分区标题栏(结构性, 不用红)。返回标题栏下方内容起始 y。"""
    h = 26
    d.rectangle((z.x, z.y, z.x + z.w - 1, z.y + h), fill=BLACK)
    d.text((z.x + 8, z.y + 3), text, fill=WHITE, font=_font(18))
    return z.y + h + 6


def _elapsed_text(since, now) -> str:
    """状态持续时长: "已 N 分钟" / "已 N 小时"。无 since/now 返回空串。"""
    if not since or not now:
        return ""
    sec = max(0, int(now - since))
    if sec < 3600:
        return f"已 {sec // 60} 分钟"
    return f"已 {sec // 3600} 小时"


def signal_bars(rssi) -> int:
    """RSSI(dBm) -> WiFi 信号格数 0..3。None/弱 -> 0。"""
    if rssi is None:
        return 0
    if rssi >= -60:
        return 3
    if rssi >= -72:
        return 2
    if rssi >= -82:
        return 1
    return 0


def _draw_signal(d: ImageDraw.ImageDraw, z: Zone, rssi) -> None:
    """右上角 WiFi 信号格(3 格竖条, 填 signal_bars 个; 空格画空心)。rssi=None 不画。"""
    if rssi is None:
        return
    bars = signal_bars(rssi)
    base_x, base_y = z.x + z.w - 26, z.y + 28
    for i in range(3):
        x0 = base_x + i * 7
        box = (x0, base_y - (6 + i * 5), x0 + 5, base_y)
        if i < bars:
            d.rectangle(box, fill=BLACK)
        else:
            d.rectangle(box, outline=BLACK)


def _center_text(d, z, txt, font, fill):
    bb = d.textbbox((0, 0), txt, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text((z.x + (z.w - tw) // 2 - bb[0], z.y + (z.h - th) // 2 - bb[1]),
           txt, fill=fill, font=font)


def draw_big_clock(d: ImageDraw.ImageDraw, z: Zone, now) -> None:
    """巨型 HH:MM 时钟, 居中(clock 布局用)。"""
    import time
    lt = time.localtime(now)
    txt = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    size = max(24, min(z.h - 16, (z.w * 2) // (len(txt) + 1)))
    _center_text(d, z, txt, _font(size), BLACK)


def draw_usage_ring(d: ImageDraw.ImageDraw, z: Zone, usage) -> None:
    """5h 窗口占用环形进度; ratio>=0.9 标红(usage 布局用)。"""
    ratio = getattr(usage, "window_used_ratio", None)
    cx, cy = z.x + z.w // 2, z.y + z.h // 2
    r = min(z.w, z.h) // 2 - 8
    if r < 6:
        return
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=BLACK, width=3)  # 底环
    if ratio is None:
        return
    ratio = max(0.0, min(1.0, float(ratio)))
    color = RED if ratio >= 0.9 else BLACK
    end = -90 + int(360 * ratio)
    d.arc((cx - r, cy - r, cx + r, cy + r), -90, end, fill=color, width=10)  # 加粗进度弧
    pct = f"{int(ratio * 100)}%"
    fp = _font(max(16, r // 2))
    _center_text(d, z, pct, fp, color)


def draw_month_calendar(d: ImageDraw.ImageDraw, z: Zone, now) -> None:
    """当月月历 7x6 网格 + 今日高亮(红框红字)(clock/split 布局用)。"""
    import time, calendar
    lt = time.localtime(now)
    year, mon, today = lt.tm_year, lt.tm_mon, lt.tm_mday
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, mon)
    cw, ch = z.w // 7, z.h // (len(weeks) + 1)
    heads = ["一", "二", "三", "四", "五", "六", "日"]
    fh = _font(max(12, ch // 3))
    for c, hd in enumerate(heads):
        d.text((z.x + c * cw + cw // 3, z.y + 2), hd, fill=BLACK, font=fh)
    f = _font(max(14, ch // 2))
    for ri, week in enumerate(weeks):
        for c, day in enumerate(week):
            if day == 0:
                continue
            x, y = z.x + c * cw, z.y + (ri + 1) * ch
            if day == today:
                d.rectangle((x + 1, y + 1, x + cw - 2, y + ch - 2), outline=RED, width=2)
            d.text((x + cw // 3, y + ch // 6), str(day),
                   fill=(RED if day == today else BLACK), font=f)


def draw_header(d: ImageDraw.ImageDraw, z: Zone, clock_text: str, lunar, temp, humidity, rssi=None) -> None:
    f1 = _font(22)
    f2 = _font(18)
    # 第一行: 日期(红强调) + 温湿度(黑)
    d.text((z.x + 6, z.y + 6), clock_text, fill=RED, font=f1)
    t = f"{temp:.0f}C" if temp is not None else "n/a"
    env = t
    if humidity is not None and 0 <= humidity <= 100:
        env = f"{t}  {humidity:.0f}%"
    d.text((z.x + z.w - 160, z.y + 8), env, fill=BLACK, font=f1)
    _draw_signal(d, z, rssi)   # 右上角 WiFi 信号格(在线状态)
    # 第二行: 农历(黑) + 节日(红)
    lx, ly = z.x + 6, z.y + 42
    text = (lunar or {}).get("text", "")
    fest = (lunar or {}).get("festival", "")
    d.text((lx, ly), text, fill=BLACK, font=f2)
    if fest:
        w = d.textlength(text + " · ", font=f2)
        d.text((lx + w, ly), fest, fill=RED, font=f2)
    d.line((z.x, z.y + z.h - 1, z.x + z.w, z.y + z.h - 1), fill=BLACK, width=1)


def draw_claude_status(d: ImageDraw.ImageDraw, z: Zone, s: ClaudeStatus, now=None) -> None:
    cy = _title_bar(d, z, "状态")
    big = _font(44)
    small = _font(20)
    color = RED if s.needs_attention() else BLACK
    # 状态色块: 不依赖字形, 保证状态色可见
    d.rectangle((z.x + 12, cy + 6, z.x + 34, cy + 30), fill=color)
    label = STATE_LABEL.get(s.state, s.state)
    d.text((z.x + 44, cy), label, fill=color, font=big)
    proj = s.project or "-"
    elapsed = _elapsed_text(getattr(s, "since", None), now)
    line2 = proj + (f" · {elapsed}" if elapsed else "")
    d.text((z.x + 12, cy + 58), line2, fill=BLACK, font=small)


def draw_usage(d: ImageDraw.ImageDraw, z: Zone, u: Usage, budget_usd=None) -> None:
    cy = _title_bar(d, z, "今日用量")
    f = _font(20)
    hero = _font(40)
    d.text((z.x + 8, cy), f"{u.total_tokens()} tok", fill=BLACK, font=f)
    # hero 花费: 超预算告警红, 否则黑(靠字号强调)
    over = budget_usd is not None and u.cost_usd > budget_usd
    d.text((z.x + 8, cy + 28), f"${u.cost_usd:.0f}", fill=(RED if over else BLACK), font=hero)
    by = cy + 84
    if u.window_used_ratio is not None:
        bx, bw, bh = z.x + 8, z.w - 92, 16
        d.rectangle((bx, by, bx + bw, by + bh), outline=BLACK, width=1)
        fillw = int(bw * max(0.0, min(1.0, u.window_used_ratio)))
        d.rectangle((bx, by, bx + fillw, by + bh), fill=BLACK)
        pct = int(round(u.window_used_ratio * 100))
        pcol = RED if u.window_used_ratio > 0.90 else BLACK   # >90% 告警红
        d.text((bx + bw + 6, by - 3), f"{pct}%", fill=pcol, font=f)
    else:
        d.text((z.x + 8, by), "窗口 n/a", fill=BLACK, font=f)
    d.text((z.x + 8, by + 28), f"今日 {u.session_count} 会话", fill=BLACK, font=f)


def draw_todos(d: ImageDraw.ImageDraw, z: Zone, items: list[TodoItem]) -> None:
    cy = _title_bar(d, z, "待办")
    f = _font(20)
    y = cy
    for t in items[:4]:
        box = "☑" if t.done else "☐"
        line = f"{box} {t.text}"
        d.text((z.x + 8, y), line, fill=BLACK, font=f)
        if t.done:   # 完成项删除线弱化
            w = d.textlength(line, font=f)
            ly = y + 13
            d.line((z.x + 8, ly, z.x + 8 + w, ly), fill=BLACK, width=1)
        y += 34
