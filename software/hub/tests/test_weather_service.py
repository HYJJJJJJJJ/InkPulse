from inkpulse_hub.collectors.weather import WeatherService, REFRESH_S

SAMPLE_RAW = {
    "current": {"temperature_2m": 23.4, "weather_code": 2},
    "daily": {"time": ["2026-06-14", "2026-06-15", "2026-06-16", "2026-06-17"],
              "weather_code": [2, 0, 3, 61],
              "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
              "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}
}
NOW = 1749880000.0


def _svc(tmp_path):
    return WeatherService(str(tmp_path / "wcache.json"))


def test_current_none_when_no_cache(tmp_path):
    assert _svc(tmp_path).current(NOW) is None


def test_refresh_now_writes_cache_and_current_reads(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    w = s.current(NOW)
    assert w["cur_temp"] == 23.4 and w["status"] == "ok" and w["age_s"] == 0


def test_current_marks_stale(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    w = s.current(NOW + REFRESH_S + 10)
    assert w["status"] == "stale" and w["age_s"] == REFRESH_S + 10


def test_refresh_failure_keeps_old_cache(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    def boom(lat, lon):
        raise RuntimeError("down")
    s.refresh_now(30.29, 120.16, NOW + 5, fetch=boom)   # 不抛, 保留旧缓存
    assert s.current(NOW)["cur_temp"] == 23.4


def test_needs_refresh_logic(tmp_path):
    s = _svc(tmp_path)
    assert s._needs_refresh(30.29, 120.16, NOW) is True          # 无缓存
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    assert s._needs_refresh(30.29, 120.16, NOW + 10) is False    # 新鲜同坐标
    assert s._needs_refresh(30.29, 120.16, NOW + REFRESH_S + 1) is True   # 过期
    assert s._needs_refresh(99.0, 99.0, NOW + 10) is True        # 坐标变更


def test_clear_removes_cache(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    s.clear()
    assert s.current(NOW) is None


def test_current_returns_none_on_malformed_cache(tmp_path):
    import json
    p = tmp_path / "wcache.json"
    # 结构合法的 JSON + 有 "raw", 但 raw 缺 parse_weather 需要的字段, 且无 fetched_at
    p.write_text(json.dumps({"raw": {"bogus": 1}}), encoding="utf-8")
    s = WeatherService(str(p))
    assert s.current(NOW) is None      # 不抛, 降级


def test_maybe_refresh_noop_when_fresh(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(30.29, 120.16, NOW, fetch=lambda lat, lon: SAMPLE_RAW)
    def boom(lat, lon):
        raise AssertionError("should not fetch")
    s.maybe_refresh(30.29, 120.16, NOW + 10, fetch=boom)
    assert s.current(NOW)["cur_temp"] == 23.4
