from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _client(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"))
    return TestClient(create_app(cfg))


def test_health(tmp_path):
    assert _client(tmp_path).get("/health").json() == {"ok": True}


def test_frame_returns_binary_with_etag_and_next_refresh(tmp_path):
    c = _client(tmp_path)
    r = c.get("/frame")
    assert r.status_code == 200
    assert len(r.content) == 96000
    assert r.headers["etag"].startswith('"')
    assert int(r.headers["x-next-refresh"]) > 0


def test_frame_304_when_if_none_match(tmp_path):
    c = _client(tmp_path)
    etag = c.get("/frame").headers["etag"]
    r = c.get("/frame", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.content == b""


def test_frame_accepts_env_query(tmp_path):
    c = _client(tmp_path)
    r = c.get("/frame", params={"t": 22.5, "h": 60})
    assert r.status_code == 200


def test_ingest_claude_status_updates_frame(tmp_path):
    c = _client(tmp_path)
    before = c.get("/frame").headers["etag"]
    assert c.post("/ingest/claude-status", json={"state": "error", "project": "X"}).json()["ok"]
    after = c.get("/frame").headers["etag"]
    assert before != after


def _app_env(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 env_history_store=str(tmp_path / "env.json"))
    return create_app(cfg)


def test_frame_with_temp_records_history(tmp_path):
    import time
    app = _app_env(tmp_path)
    TestClient(app).get("/frame", params={"t": 23.4})
    hist = app.state.hub.env_history.window(time.time())
    assert len(hist) == 1 and hist[0][1] == 23.4


def test_frame_without_temp_records_nothing(tmp_path):
    import time
    app = _app_env(tmp_path)
    TestClient(app).get("/frame", params={"rssi": -55})
    assert app.state.hub.env_history.window(time.time()) == []


def test_frame_bw_426_returns_48000(tmp_path):
    r = _client(tmp_path).get("/frame?panel=bw_426")
    assert r.status_code == 200
    assert len(r.content) == 48000


def test_frame_default_panel_returns_96000(tmp_path):
    r = _client(tmp_path).get("/frame")
    assert r.status_code == 200
    assert len(r.content) == 96000


def test_frame_unknown_panel_falls_back(tmp_path):
    r = _client(tmp_path).get("/frame?panel=zzz")
    assert len(r.content) == 96000


def test_preview_png_accepts_panel(tmp_path):
    r = _client(tmp_path).get("/preview.png?panel=bw_426")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
