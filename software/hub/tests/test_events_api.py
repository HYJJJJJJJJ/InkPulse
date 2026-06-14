from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 events_store=str(tmp_path / "events.json"))
    return TestClient(create_app(cfg))


def test_get_empty(tmp_path):
    assert _client(tmp_path).get("/api/events").json() == []


def test_add_and_get(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/events", json={"title": "团队周会", "date": "2026-06-14", "time": "14:30"})
    assert r.status_code == 200 and r.json()["id"]
    got = c.get("/api/events").json()
    assert [e["title"] for e in got] == ["团队周会"]


def test_add_rejects_blank_title(tmp_path):
    assert _client(tmp_path).post("/api/events",
        json={"title": "  ", "date": "2026-06-14", "time": ""}).status_code == 400


def test_add_rejects_bad_date(tmp_path):
    assert _client(tmp_path).post("/api/events",
        json={"title": "x", "date": "2026/06/14", "time": ""}).status_code == 400


def test_add_rejects_bad_time(tmp_path):
    assert _client(tmp_path).post("/api/events",
        json={"title": "x", "date": "2026-06-14", "time": "9点"}).status_code == 400


def test_add_allday_ok(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/events",
        json={"title": "全天事", "date": "2026-06-14", "time": ""}).status_code == 200


def test_delete(tmp_path):
    c = _client(tmp_path)
    eid = c.post("/api/events", json={"title": "x", "date": "2026-06-14", "time": ""}).json()["id"]
    assert c.delete(f"/api/events/{eid}").status_code == 200
    assert c.get("/api/events").json() == []
