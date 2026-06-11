import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from inkpulse_hub.collectors.usage import collect_usage, _record_local_date


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

# 用与 fixture 中"今天"记录同一时刻推导本地日期，使断言与时区无关
TODAY = _record_local_date({"timestamp": "2026-06-09T12:00:00.000Z"})


def _setup_logs(tmp_path) -> str:
    proj = tmp_path / "proj"
    proj.mkdir()
    src = Path(__file__).parent / "fixtures" / "session_sample.jsonl"
    shutil.copy(src, proj / "session_sample.jsonl")
    return str(tmp_path)


def test_collect_usage_today_only_and_tolerates_garbage(tmp_path):
    # fixture: 今天两条(160/60/10) + 5/1旧记录 + 无timestamp记录 + 坏行
    u = collect_usage(_setup_logs(tmp_path), today=TODAY)
    assert u.input_tokens == 160      # 旧记录9999与无时间戳5555都不计入
    assert u.output_tokens == 60
    assert u.cache_tokens == 10
    assert u.total_tokens() == 220
    assert u.session_count == 1


def test_other_day_excluded(tmp_path):
    # 把"今天"设为旧记录那天, 则只剩那条旧记录被统计(今天的两条被排除)
    old_day = _record_local_date({"timestamp": "2026-05-01T12:00:00.000Z"})
    u = collect_usage(_setup_logs(tmp_path), today=old_day)
    assert u.input_tokens == 9999
    assert u.output_tokens == 9999


def test_missing_dir_returns_zero_usage(tmp_path):
    u = collect_usage(str(tmp_path / "nope"))
    assert u.total_tokens() == 0
    assert u.session_count == 0


def test_cost_estimation_by_model(tmp_path):
    # opus 定价(per 1M): input 15 / output 75 / cache_write 18.75 / cache_read 1.5
    ts = "2026-06-09T12:00:00.000Z"
    rec = {"timestamp": ts, "message": {"model": "claude-opus-4-8", "usage": {
        "input_tokens": 1_000_000, "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000}}}
    _write_jsonl(tmp_path / "s.jsonl", [rec])
    today = _record_local_date({"timestamp": ts})
    u = collect_usage(str(tmp_path), today=today)
    assert abs(u.cost_usd - (15 + 75 + 18.75 + 1.5)) < 1e-6   # 110.25


def test_synthetic_and_unknown_model_not_billed(tmp_path):
    ts = "2026-06-09T12:00:00.000Z"
    recs = [{"timestamp": ts, "message": {"model": m, "usage": {"input_tokens": 1_000_000}}}
            for m in ("<synthetic>", "weird-model")]
    _write_jsonl(tmp_path / "s.jsonl", recs)
    u = collect_usage(str(tmp_path), today=_record_local_date({"timestamp": ts}))
    assert u.cost_usd == 0.0


def test_window_used_ratio(tmp_path):
    now = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc).astimezone()  # 窗口起点 07:00Z
    recs = [
        # 窗口内(11:00Z, now-1h): 100k token 计入
        {"timestamp": "2026-06-09T11:00:00.000Z", "message": {"model": "claude-opus-4-8",
         "usage": {"input_tokens": 100_000}}},
        # 窗口外(05:00Z, now-7h): 不计入
        {"timestamp": "2026-06-09T05:00:00.000Z", "message": {"model": "claude-opus-4-8",
         "usage": {"input_tokens": 999_999}}},
    ]
    _write_jsonl(tmp_path / "s.jsonl", recs)
    u = collect_usage(str(tmp_path), now=now, window_token_limit=200_000)
    assert abs(u.window_used_ratio - 0.5) < 1e-6   # 100k / 200k


def test_window_ratio_none_without_limit(tmp_path):
    _write_jsonl(tmp_path / "s.jsonl", [])
    u = collect_usage(str(tmp_path))
    assert u.window_used_ratio is None             # 未配上限 → n/a
