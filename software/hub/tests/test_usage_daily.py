import json
import os
from datetime import datetime, timedelta, timezone
from inkpulse_hub.collectors.usage import collect_daily_usage

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc).astimezone()


def _iso(dt_local):
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_log(d, name, records):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(dt_local, inp, out):
    return {"timestamp": _iso(dt_local), "cwd": "/p/InkPulse",
            "message": {"model": "claude-opus-4-8",
                        "usage": {"input_tokens": inp, "output_tokens": out}}}


def test_buckets_length_equals_days_and_ordered_old_to_new(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [_rec(NOW, 10, 5)])
    out = collect_daily_usage(str(tmp_path), days=7, now=NOW)
    assert len(out) == 7
    assert out[0]["date"] < out[-1]["date"]
    assert out[-1]["date"] == NOW.date()


def test_missing_days_are_zero_filled(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [
        _rec(NOW, 10, 5),
        _rec(NOW - timedelta(days=3), 4, 1),
    ])
    out = collect_daily_usage(str(tmp_path), days=7, now=NOW)
    by_date = {x["date"]: x["tokens"] for x in out}
    assert by_date[NOW.date()] == 15
    assert by_date[(NOW - timedelta(days=3)).date()] == 5
    assert by_date[(NOW - timedelta(days=1)).date()] == 0


def test_cost_summed(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [_rec(NOW, 1_000_000, 0)])
    out = collect_daily_usage(str(tmp_path), days=1, now=NOW)
    assert out[-1]["cost"] > 0


def test_empty_dir_all_zero(tmp_path):
    out = collect_daily_usage(str(tmp_path / "nope"), days=5, now=NOW)
    assert len(out) == 5 and all(x["tokens"] == 0 and x["cost"] == 0 for x in out)
