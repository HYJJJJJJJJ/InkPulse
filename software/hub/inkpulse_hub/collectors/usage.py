# inkpulse_hub/collectors/usage.py
import glob
import json
import os
from datetime import datetime, date, timedelta
from ..models import Usage

# 各模型族 per-1M-token 估算单价 (USD): (input, output, cache_write, cache_read)
# 订阅制无官方计费 API, 按 Anthropic 公开 API 定价估算花费(ccusage 思路)。
_PRICING = {
    "opus":   (15.0, 75.0, 18.75, 1.50),
    "sonnet": (3.0,  15.0, 3.75,  0.30),
    "haiku":  (0.80, 4.0,  1.00,  0.08),
}
_WINDOW_HOURS = 5  # Max 计划滚动用量窗口


def _model_family(model) -> str | None:
    """从 model 名(如 claude-opus-4-8)归一到定价族; <synthetic>/未知 → None(不计费)。"""
    if not isinstance(model, str):
        return None
    m = model.lower()
    for fam in _PRICING:
        if fam in m:
            return fam
    return None


def _cost_of(usage: dict, model) -> float:
    """按模型定价估算单条记录花费(含写/读缓存)。未知模型记 0。"""
    fam = _model_family(model)
    if fam is None:
        return 0.0
    pin, pout, pcw, pcr = _PRICING[fam]
    it = int(usage.get("input_tokens", 0) or 0)
    ot = int(usage.get("output_tokens", 0) or 0)
    cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    return (it * pin + ot * pout + cw * pcw + cr * pcr) / 1e6


def _record_dt(rec: dict):
    """从记录顶层 timestamp(UTC ISO, 如 2026-06-09T01:35:28.636Z) 解析本地 datetime。"""
    ts = rec.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()  # 转本地时区
    return dt


def _record_local_date(rec: dict):
    """从记录解析本地日期(date)。"""
    dt = _record_dt(rec)
    return dt.date() if dt else None


def collect_usage(
    logs_dir: str,
    today: date | None = None,
    now: datetime | None = None,
    window_token_limit: int | None = None,
) -> Usage:
    """解析 Claude Code 会话日志(.jsonl):
    - 今日 token 用量 + 估算花费(cost_usd)
    - 近 5h 滚动窗口 token 占 window_token_limit 的比例(window_used_ratio)
    """
    u = Usage()
    if not os.path.isdir(logs_dir):
        return u
    if now is None:
        now = datetime.now().astimezone()
    if today is None:
        today = now.date()
    window_start = now - timedelta(hours=_WINDOW_HOURS)

    files = glob.glob(os.path.join(logs_dir, "**", "*.jsonl"), recursive=True)
    sessions_today = set()
    window_tokens = 0
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # 容错：坏行跳过
                    dt = _record_dt(rec)
                    if dt is None:
                        continue
                    msg = rec.get("message") or {}
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    # 今日累计 token + 花费
                    if dt.date() == today:
                        u.input_tokens += int(usage.get("input_tokens", 0) or 0)
                        u.output_tokens += int(usage.get("output_tokens", 0) or 0)
                        u.cache_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
                        u.cost_usd += _cost_of(usage, msg.get("model"))
                        sessions_today.add(fp)
                    # 近 5h 滚动窗口 token(可能跨到昨天)。口径取净输入+输出,
                    # 不含缓存读写——缓存量级极大(可上亿)会让任何上限秒满, 失去意义。
                    if dt >= window_start:
                        window_tokens += (
                            int(usage.get("input_tokens", 0) or 0)
                            + int(usage.get("output_tokens", 0) or 0)
                        )
        except OSError:
            continue
    u.session_count = len(sessions_today)
    if window_token_limit and window_token_limit > 0:
        u.window_used_ratio = min(1.0, window_tokens / window_token_limit)
    return u
