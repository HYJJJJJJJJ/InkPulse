import json
import os
from datetime import datetime, timezone
from inkpulse_hub.collectors.usage import _iter_usage_records, UsageRecord

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc).astimezone()


def _iso(dt_local):
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_log(d, name, records):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(dt_local, cwd, inp, out, model="claude-opus-4-8"):
    return {"timestamp": _iso(dt_local), "cwd": cwd,
            "message": {"model": model,
                        "usage": {"input_tokens": inp, "output_tokens": out}}}


def test_iter_yields_records_with_project_basename(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [
        _rec(NOW, "/home/u/workspace/InkPulse", 10, 5),
        _rec(NOW, "/home/u/webapp", 3, 2),
    ])
    recs = list(_iter_usage_records(str(tmp_path)))
    assert len(recs) == 2
    assert all(isinstance(r, UsageRecord) for r in recs)
    assert {r.project for r in recs} == {"InkPulse", "webapp"}
    one = next(r for r in recs if r.project == "InkPulse")
    assert one.input == 10 and one.output == 5


def test_iter_skips_bad_lines_and_no_usage(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text(
        "{ not json\n"
        + json.dumps({"timestamp": _iso(NOW), "cwd": "/x/y", "message": {}}) + "\n"
        + json.dumps(_rec(NOW, "/x/y", 1, 1)) + "\n",
        encoding="utf-8")
    recs = list(_iter_usage_records(str(tmp_path)))
    assert len(recs) == 1


def test_iter_missing_cwd_is_question_mark(tmp_path):
    _write_log(str(tmp_path), "c.jsonl", [
        {"timestamp": _iso(NOW), "message": {"usage": {"input_tokens": 1, "output_tokens": 0}}},
    ])
    recs = list(_iter_usage_records(str(tmp_path)))
    assert recs and recs[0].project == "?"


def test_iter_empty_dir(tmp_path):
    assert list(_iter_usage_records(str(tmp_path / "nope"))) == []
