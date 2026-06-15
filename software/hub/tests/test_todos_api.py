from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"))
    return TestClient(create_app(cfg))


def test_todos_crud_api(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/todos").json() == []
    created = c.post("/api/todos", json={"text": "写计划"}).json()
    tid = created["id"]
    assert [x["text"] for x in c.get("/api/todos").json()] == ["写计划"]
    c.post(f"/api/todos/{tid}/toggle")
    assert c.get("/api/todos").json()[0]["done"] is True
    c.delete(f"/api/todos/{tid}")
    assert c.get("/api/todos").json() == []
