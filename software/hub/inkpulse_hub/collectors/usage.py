# inkpulse_hub/collectors/usage.py
import glob
import json
import os
from datetime import datetime, date
from ..models import Usage


def _record_local_date(rec: dict):
    """从记录顶层 timestamp(UTC ISO, 如 2026-06-09T01:35:28.636Z) 解析出本地日期。"""
    ts = rec.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()  # 转本地时区
    return dt.date()


def collect_usage(logs_dir: str, today: date | None = None) -> Usage:
    """解析 Claude Code 会话日志(.jsonl), 仅统计【今天】的 token 用量。"""
    u = Usage()
    if not os.path.isdir(logs_dir):
        return u
    if today is None:
        today = date.today()
    files = glob.glob(os.path.join(logs_dir, "**", "*.jsonl"), recursive=True)
    sessions_today = set()
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
                    if _record_local_date(rec) != today:
                        continue  # 只统计今天
                    usage = (rec.get("message") or {}).get("usage")
                    if not isinstance(usage, dict):
                        continue
                    u.input_tokens += int(usage.get("input_tokens", 0) or 0)
                    u.output_tokens += int(usage.get("output_tokens", 0) or 0)
                    u.cache_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
                    sessions_today.add(fp)
        except OSError:
            continue
    u.session_count = len(sessions_today)
    return u
