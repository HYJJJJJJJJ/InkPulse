from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"))
    return create_app(cfg)


def test_device_frame_recorded_after_pull(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    assert app.state.hub.device_frame_png is None
    c.get("/frame")
    assert app.state.hub.device_frame_png is not None
    assert app.state.hub.device_frame_pulled_at is not None


def test_device_frame_png_endpoint(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    c.get("/frame")
    r = c.get("/api/device/frame.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 0


def test_device_frame_png_fallback_when_no_pull(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    r = c.get("/api/device/frame.png")   # 设备从未拉帧
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 0


def test_device_status_fields(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    c.get("/frame", params={"t": 21.0, "h": 55, "rssi": -58})
    s = c.get("/api/device/status").json()
    assert s["pulled_at"] is not None
    assert s["age_s"] is not None and s["age_s"] >= 0
    assert s["rssi"] == -58
    assert s["temp"] == 21.0
    assert s["humidity"] == 55
    assert s["etag"]


def test_304_does_not_overwrite_record(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    etag = c.get("/frame").headers["etag"]
    pulled = app.state.hub.device_frame_pulled_at
    r = c.get("/frame", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert app.state.hub.device_frame_pulled_at == pulled   # 记录未被覆盖
