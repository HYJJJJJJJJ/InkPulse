import time
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 agent_tasks_store=str(tmp_path / "at.json"))
    return create_app(cfg)


def test_ingest_tasks(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    r = c.post("/ingest/agent-tasks",
               json={"project": "P", "tasks": [{"content": "x", "status": "pending"}]})
    assert r.status_code == 200
    cur = app.state.hub.agent_tasks.current(time.time())
    assert cur["project"] == "P" and cur["tasks"][0]["content"] == "x"


def test_ingest_blank_project_400(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.post("/ingest/agent-tasks", json={"project": "  ", "tasks": []}).status_code == 400


def test_ingest_highlights_only_keeps_tasks(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    c.post("/ingest/agent-tasks", json={"project": "P", "tasks": [{"content": "x", "status": "pending"}]})
    c.post("/ingest/agent-tasks", json={"project": "P", "highlights": ["h"]})
    cur = app.state.hub.agent_tasks.current(time.time())
    assert [t["content"] for t in cur["tasks"]] == ["x"] and cur["highlights"] == ["h"]
