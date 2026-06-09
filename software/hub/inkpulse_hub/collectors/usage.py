# inkpulse_hub/collectors/usage.py
import glob
import json
import os
from ..models import Usage


def collect_usage(logs_dir: str) -> Usage:
    u = Usage()
    if not os.path.isdir(logs_dir):
        return u
    files = glob.glob(os.path.join(logs_dir, "**", "*.jsonl"), recursive=True)
    u.session_count = len(files)
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
                    usage = (rec.get("message") or {}).get("usage")
                    if not isinstance(usage, dict):
                        continue
                    u.input_tokens += int(usage.get("input_tokens", 0) or 0)
                    u.output_tokens += int(usage.get("output_tokens", 0) or 0)
                    u.cache_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
        except OSError:
            continue
    return u
