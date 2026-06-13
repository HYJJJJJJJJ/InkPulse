import json
import os
from datetime import datetime, timedelta, timezone
from inkpulse_hub.collectors.usage import collect_project_usage

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc).astimezone()


def _iso(dt_local):
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_log(d, name, records):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(dt_local, cwd, inp, out):
    return {"timestamp": _iso(dt_local), "cwd": cwd,
            "message": {"model": "claude-opus-4-8",
                        "usage": {"input_tokens": inp, "output_tokens": out}}}


def test_groups_by_basename_today_only_desc(tmp_path):
    _write_log(str(tmp_path), "a.jsonl", [
        _rec(NOW, "/p/InkPulse", 100, 0),
        _rec(NOW, "/p/InkPulse", 50, 0),
        _rec(NOW, "/p/webapp", 30, 0),
        _rec(NOW - timedelta(days=1), "/p/old", 999, 0),
    ])
    out = collect_project_usage(str(tmp_path), now=NOW)
    assert [x["project"] for x in out] == ["InkPulse", "webapp"]
    assert out[0]["tokens"] == 150


def test_empty_dir_returns_empty(tmp_path):
    assert collect_project_usage(str(tmp_path / "nope"), now=NOW) == []
