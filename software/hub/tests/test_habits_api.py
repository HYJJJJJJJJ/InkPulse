from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config
from inkpulse_hub.collectors.habits import week_dates
import time


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 habits_store=str(tmp_path / "habits.json"))
    return TestClient(create_app(cfg))


def test_get_empty_structure(tmp_path):
    r = _client(tmp_path).get("/api/habits").json()
    assert r["habits"] == [] and r["done"] == {}
    assert len(r["week"]) == 7 and 0 <= r["today_idx"] <= 6


def test_add_reject_empty_name(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/habits", json={"name": "运动"}).status_code == 200
    assert c.post("/api/habits", json={"name": "   "}).status_code == 400
    assert [h["name"] for h in c.get("/api/habits").json()["habits"]] == ["运动"]


def test_toggle_today_and_done_matrix(tmp_path):
    c = _client(tmp_path)
    hid = c.post("/api/habits", json={"name": "运动"}).json()["id"]
    dates, idx = week_dates(time.time())
    today = dates[idx]
    assert c.post(f"/api/habits/{hid}/toggle", json={"date": today}).status_code == 200
    done = c.get("/api/habits").json()["done"][hid]
    assert done[idx] is True


def test_toggle_future_rejected(tmp_path):
    c = _client(tmp_path)
    hid = c.post("/api/habits", json={"name": "运动"}).json()["id"]
    dates, idx = week_dates(time.time())
    if idx < 6:                       # 本周还有未来日
        future = dates[idx + 1]
        assert c.post(f"/api/habits/{hid}/toggle", json={"date": future}).status_code == 400
    # 显式造一个远未来日, 必拒
    assert c.post(f"/api/habits/{hid}/toggle", json={"date": "2099-01-01"}).status_code == 400


def test_toggle_unknown_id_404(tmp_path):
    c = _client(tmp_path)
    dates, idx = week_dates(time.time())
    assert c.post("/api/habits/deadbeef/toggle",
                  json={"date": dates[idx]}).status_code == 404


def test_delete_habit(tmp_path):
    c = _client(tmp_path)
    hid = c.post("/api/habits", json={"name": "运动"}).json()["id"]
    assert c.delete(f"/api/habits/{hid}").status_code == 200
    assert c.get("/api/habits").json()["habits"] == []
