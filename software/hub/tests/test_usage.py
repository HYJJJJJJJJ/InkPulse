import shutil
from datetime import date
from pathlib import Path
from inkpulse_hub.collectors.usage import collect_usage, _record_local_date

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
