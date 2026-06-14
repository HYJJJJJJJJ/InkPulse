# inkpulse_hub/render/widgets.py
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
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


def draw_na(d: ImageDraw.ImageDraw, z: Zone) -> None:
    """缺失/出错 widget 的占位框(供引擎按 widget 隔离容错调用)。"""
    d.rectangle((z.x, z.y, z.x + z.w - 1, z.y + z.h - 1), outline=BLACK)
    _center_text(d, z, "n/a", _font(20), BLACK)


def draw_big_clock(d: ImageDraw.ImageDraw, z: Zone, now) -> None:
    """巨型 HH:MM 时钟, 居中(clock 布局用)。"""
    import time
    lt = time.localtime(now)
    txt = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    # 留出上下/左右余白: 高度取 ~60%, 宽度按字符数估算, 取较小者
    size = max(24, int(min(z.h * 0.6, z.w / (len(txt) * 0.62))))
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
    fh = _font(max(14, int(ch * 0.45)))   # 表头与日期数字字号更接近
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


def _parse_clock(clock_text: str):
    """把 '2026-06-13 17:01 周六' 拆成 (时间, 中文日期, 星期)。
    格式异常时返回 (None, 原串, '')。"""
    parts = (clock_text or "").split()
    if len(parts) != 3:
        return None, clock_text or "", ""
    ymd, hm, weekday = parts
    try:
        _, m, dd = ymd.split("-")
        date_cn = f"{int(m)}月{int(dd)}日"
    except ValueError:
        date_cn = ymd
    return hm, date_cn, weekday


def draw_header(d: ImageDraw.ImageDraw, z: Zone, clock_text: str, lunar, temp, humidity, rssi=None) -> None:
    """头部: 左大时间 + 中文日期(周X红) + 农历; 右上温度/湿度/WiFi。
    按 zone 宽度自适应(窄区如 split 用小号), 避免内容互相覆盖。"""
    f2 = _font(18)
    narrow = z.w < 560
    time_str, date_cn, weekday = _parse_clock(clock_text)
    text = (lunar or {}).get("text", "")
    fest = (lunar or {}).get("festival", "")
    # 右上角: 温度(°C)[+湿度] + WiFi 信号格; 按实际文字宽度右对齐
    t = f"{temp:.0f}°C" if temp is not None else "n/a"
    env = t
    if humidity is not None and 0 <= humidity <= 100:
        env = f"{t}  {humidity:.0f}%"
    env_font = _font(20 if narrow else 22)
    sig_w = 30 if rssi is not None else 0
    env_x = z.x + z.w - int(d.textlength(env, font=env_font)) - sig_w - 6
    d.text((env_x, z.y + 8), env, fill=BLACK, font=env_font)
    _draw_signal(d, z, rssi)
    right_limit = env_x - 8   # 左侧内容右边界, 不得越过

    if time_str:
        big = _font(34 if narrow else 46)
        d.text((z.x + 8, z.y + 2), time_str, fill=BLACK, font=big)
        cx = z.x + 8 + int(d.textlength(time_str, font=big)) + (10 if narrow else 18)
        sub = _font(18 if narrow else 20)
        ly2 = z.y + (30 if narrow else 36)
        # 右栏上: 中文日期(黑) + 星期(红); 星期越界则省略
        d.text((cx, z.y + 6), date_cn, fill=BLACK, font=sub)
        wx = cx + int(d.textlength(date_cn + " ", font=sub))
        if wx + d.textlength(weekday, font=sub) <= right_limit:
            d.text((wx, z.y + 6), weekday, fill=RED, font=sub)
        # 右栏下: 农历(黑) + 节日(红)
        d.text((cx, ly2), text, fill=BLACK, font=f2)
        if fest:
            d.text((cx + int(d.textlength(text + " · ", font=f2)), ly2),
                   fest, fill=RED, font=f2)
    else:
        # 兜底: 时钟串格式异常时退回旧式整行
        d.text((z.x + 6, z.y + 6), clock_text, fill=RED, font=_font(22))
        d.text((z.x + 6, z.y + 42), text, fill=BLACK, font=f2)
        if fest:
            d.text((z.x + 6 + int(d.textlength(text + " · ", font=f2)), z.y + 42),
                   fest, fill=RED, font=f2)
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
    d.text((z.x + 8, cy), f"{u.total_tokens()} tokens", fill=BLACK, font=f)
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
        box = "✓" if t.done else "□"   # 思源黑无 ☑/☐ 字形, 用确有的 ✓/□
        line = f"{box} {t.text}"
        d.text((z.x + 8, y), line, fill=BLACK, font=f)
        if t.done:   # 完成项删除线弱化
            w = d.textlength(line, font=f)
            ly = y + 13
            d.line((z.x + 8, ly, z.x + 8 + w, ly), fill=BLACK, width=1)
        y += 34


def draw_countdown(d: ImageDraw.ImageDraw, z: Zone, now, date_str, label="") -> None:
    """倒计时/纪念日: 顶部标题栏(label) + 居中 D-N。0..3 天内标红。"""
    import datetime, time
    cy = _title_bar(d, z, label or "倒计时")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    try:
        target = datetime.date.fromisoformat((date_str or "").strip())
        today = datetime.date.fromtimestamp(now if now else time.time())
        days = (target - today).days
    except (ValueError, TypeError):
        _center_text(d, body, "日期?", _font(24), BLACK)
        return
    if days > 0:
        big = f"D-{days}"
    elif days == 0:
        big = "就在今天"
    else:
        big = f"已过{-days}天"
    color = RED if 0 <= days <= 3 else BLACK
    _center_text(d, body, big, _font(min(48, max(20, body.h - 8))), color)


def draw_usage_trend(d: ImageDraw.ImageDraw, z: Zone, daily,
                     days: int = 7, metric: str = "tokens") -> None:
    """近 days 天用量竖直柱状图。daily: [{date, tokens, cost}] 旧->新。"""
    days = max(1, min(int(days), 14))
    key = metric if metric in ("tokens", "cost") else "tokens"
    cy = _title_bar(d, z, f"用量趋势 · 近{days}天")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    series = (daily or [])[-days:]
    vals = [max(0, x.get(key, 0)) for x in series]
    if not series or max(vals, default=0) <= 0:
        _center_text(d, body, "无数据", _font(20), BLACK)
        return
    n = len(series)
    gap, label_h = 4, 16
    chart_h = body.h - label_h
    bw = max(2, (body.w - gap * (n + 1)) // n)
    vmax = max(vals)
    f = _font(12)
    for i, (x, v) in enumerate(zip(series, vals)):
        bx = body.x + gap + i * (bw + gap)
        bh = int((chart_h - 2) * (v / vmax))
        top = body.y + chart_h - bh
        d.rectangle((bx, top, bx + bw - 1, body.y + chart_h - 1), fill=BLACK)
        dt = x["date"]
        lbl = f"{dt.month}/{dt.day}"
        tw = d.textlength(lbl, font=f)
        d.text((bx + (bw - tw) / 2, body.y + chart_h + 2), lbl, fill=BLACK, font=f)


def draw_project_dist(d: ImageDraw.ImageDraw, z: Zone, projects,
                      top_n: int = 5, metric: str = "tokens") -> None:
    """今日各项目占比横向条。projects: [{project, tokens, cost}]。"""
    top_n = max(1, int(top_n))
    key = metric if metric in ("tokens", "cost") else "tokens"
    cy = _title_bar(d, z, "项目分布 · 今日")
    body = Zone(z.x, cy, z.w, z.y + z.h - cy)
    items = sorted(projects or [], key=lambda x: x.get(key, 0), reverse=True)
    total = sum(max(0, x.get(key, 0)) for x in items)
    if not items or total <= 0:
        _center_text(d, body, "无数据", _font(20), BLACK)
        return
    rows = [(x["project"], max(0, x.get(key, 0))) for x in items[:top_n]]
    rest = items[top_n:]
    if rest:
        rows.append(("其他", sum(max(0, x.get(key, 0)) for x in rest)))
    f = _font(16)
    row_h = max(18, min(28, body.h // len(rows)))
    name_w, pct_w = 84, 48
    bar_x = body.x + name_w
    bar_max = max(4, body.w - name_w - pct_w)
    for i, (name, v) in enumerate(rows):
        ry = body.y + i * row_h
        nm = name if len(name) <= 6 else name[:5] + "…"
        d.text((body.x + 4, ry), nm, fill=BLACK, font=f)
        frac = v / total
        bw = int(bar_max * frac)
        d.rectangle((bar_x, ry + 3, bar_x + bw, ry + row_h - 6), fill=BLACK)
        d.text((bar_x + bw + 4, ry), f"{int(round(frac * 100))}%", fill=BLACK, font=f)


def draw_qrcode(img: Image.Image, z: Zone, content: str) -> None:
    """在 zone 内居中画纯黑白二维码(墨水屏友好)。空内容不画。"""
    import qrcode
    if not content:
        return
    qr = qrcode.QRCode(border=1, box_size=1)
    qr.add_data(content)
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    size = max(1, min(z.w, z.h))
    q = q.resize((size, size), Image.NEAREST)   # 最近邻, 保持纯黑白不出灰边
    ox = z.x + (z.w - size) // 2
    oy = z.y + (z.h - size) // 2
    img.paste(q, (ox, oy))


def draw_habits(d: ImageDraw.ImageDraw, z: Zone, habits: list, today_idx: int) -> None:
    """本周(周一→周日)打卡墙。habits=[{"name","days":[bool×7]}], today_idx=今天列(周一=0)。
    实心方块=已打卡, 空心方块=已过未打, 留空=未来; 今天列额外描边。纯黑, 无红。"""
    cy = _title_bar(d, z, "习惯打卡")
    if not habits:
        _center_text(d, z, "无习惯 · 去网页添加", _font(18), BLACK)
        return
    heads = ["一", "二", "三", "四", "五", "六", "日"]
    name_w = max(60, z.w // 4)                 # 左侧习惯名列宽
    grid_x = z.x + name_w
    cw = (z.x + z.w - grid_x - 6) // 7          # 每列宽
    hf = _font(15)
    for c, hd in enumerate(heads):             # 星期表头, 与下方格子列对齐
        d.text((grid_x + c * cw + cw // 2 - 7, cy), hd, fill=BLACK, font=hf)
    row_y0 = cy + 22
    avail = z.y + z.h - row_y0 - 4
    row_h = 30
    max_rows = max(1, avail // row_h)
    nf = _font(18)
    for r, hb in enumerate(habits[:max_rows]):
        y = row_y0 + r * row_h
        name = hb["name"]
        while name and d.textlength(name, font=nf) > name_w - 10:   # 超长截断
            name = name[:-1]
        d.text((z.x + 6, y + 4), name, fill=BLACK, font=nf)
        box = min(cw, row_h) - 12
        midy = y + row_h // 2
        for c in range(7):
            cx = grid_x + c * cw + (cw - box) // 2
            by = midy - box // 2
            rect = (cx, by, cx + box, by + box)
            if c > today_idx:
                pass                                   # 未来: 留空
            elif hb["days"][c]:
                d.rectangle(rect, fill=BLACK)          # ■ 已打卡
            else:
                d.rectangle(rect, outline=BLACK)       # □ 已过未打
            if c == today_idx:                         # 今天列描边强调
                d.rectangle((cx - 3, by - 3, cx + box + 3, by + box + 3),
                            outline=BLACK, width=1)
