from fastapi.testclient import TestClient
import inkpulse_hub.collectors.weather as W
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 weather_cache=str(tmp_path / "w.json"),
                 runtime_store=str(tmp_path / "rt.json"))
    return create_app(cfg)


def test_search_proxies_geocode(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "geocode",
                        lambda q: [{"name": "杭州", "lat": 30.29, "lon": 120.16, "admin": "中国 浙江省"}])
    r = TestClient(_app(tmp_path)).get("/api/weather/search", params={"q": "杭州"})
    assert r.status_code == 200 and r.json()[0]["name"] == "杭州"


def test_set_and_get_location(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    assert c.post("/api/weather/location",
                  json={"lat": 30.29, "lon": 120.16, "name": "杭州"}).status_code == 200
    assert app.state.cfg.weather_place == "杭州" and app.state.cfg.weather_lat == 30.29
    got = c.get("/api/weather").json()
    assert got["place"] == "杭州" and got["lat"] == 30.29 and got["weather"] is None


def test_set_location_missing_field_400(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.post("/api/weather/location", json={"lat": 30.29}).status_code == 400


def test_delete_location(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    c.post("/api/weather/location", json={"lat": 30.29, "lon": 120.16, "name": "杭州"})
    assert c.delete("/api/weather/location").status_code == 200
    assert app.state.cfg.weather_place == "" and app.state.cfg.weather_lat is None
    assert c.get("/api/weather").json()["weather"] is None
