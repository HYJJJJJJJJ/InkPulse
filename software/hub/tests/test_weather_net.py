import inkpulse_hub.collectors.weather as W


def test_geocode_parses_results(monkeypatch):
    sample = {"results": [
        {"name": "杭州", "latitude": 30.29, "longitude": 120.16,
         "country": "中国", "admin1": "浙江省"},
        {"name": "Hangzhou", "latitude": 30.0, "longitude": 120.0, "country": "中国"},
    ]}
    monkeypatch.setattr(W, "_get_json", lambda url: sample)
    out = W.geocode("杭州")
    assert out[0] == {"name": "杭州", "lat": 30.29, "lon": 120.16, "admin": "中国 浙江省"}
    assert out[1]["admin"] == "中国"


def test_geocode_empty_name_returns_empty(monkeypatch):
    monkeypatch.setattr(W, "_get_json", lambda url: {"results": []})
    assert W.geocode("   ") == []


def test_geocode_swallows_errors(monkeypatch):
    def boom(url):
        raise RuntimeError("network down")
    monkeypatch.setattr(W, "_get_json", boom)
    assert W.geocode("杭州") == []


def test_geocode_retries_with_shi_suffix(monkeypatch):
    calls = []
    def fake(url):
        calls.append(url)
        # 编码后 "市" = %E5%B8%82; 带"市"的二次查询才有结果, 首次(厦门)无结果
        if "%E5%B8%82" in url:
            return {"results": [{"name": "厦门市", "latitude": 24.48, "longitude": 118.08,
                                 "country": "中国", "admin1": "福建省"}]}
        return {}      # 无 results 字段
    monkeypatch.setattr(W, "_get_json", fake)
    out = W.geocode("厦门")
    assert len(calls) == 2                       # 重试了一次
    assert out and out[0]["name"] == "厦门市"


def test_geocode_no_retry_when_first_hits(monkeypatch):
    calls = []
    def fake(url):
        calls.append(url)
        return {"results": [{"name": "杭州", "latitude": 30.29, "longitude": 120.16,
                             "country": "中国", "admin1": "浙江"}]}
    monkeypatch.setattr(W, "_get_json", fake)
    out = W.geocode("杭州")
    assert len(calls) == 1 and out[0]["name"] == "杭州"   # 首次命中, 不重试


def test_fetch_weather_passes_through(monkeypatch):
    captured = {}
    def fake(url):
        captured["url"] = url
        return {"ok": True}
    monkeypatch.setattr(W, "_get_json", fake)
    assert W.fetch_weather(30.29, 120.16) == {"ok": True}
    assert "latitude=30.29" in captured["url"] and "forecast_days=4" in captured["url"]
