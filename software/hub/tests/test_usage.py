import shutil
from pathlib import Path
from inkpulse_hub.collectors.usage import collect_usage


def _setup_logs(tmp_path) -> str:
    proj = tmp_path / "proj"
    proj.mkdir()
    src = Path(__file__).parent / "fixtures" / "session_sample.jsonl"
    shutil.copy(src, proj / "session_sample.jsonl")
    return str(tmp_path)


def test_collect_usage_sums_tokens_and_tolerates_garbage(tmp_path):
    u = collect_usage(_setup_logs(tmp_path))
    assert u.input_tokens == 160
    assert u.output_tokens == 60
    assert u.cache_tokens == 10
    assert u.total_tokens() == 220
    assert u.session_count == 1


def test_missing_dir_returns_zero_usage(tmp_path):
    u = collect_usage(str(tmp_path / "nope"))
    assert u.total_tokens() == 0
    assert u.session_count == 0
