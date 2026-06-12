from fastapi.testclient import TestClient
from inkpulse_hub.config import Config
from inkpulse_hub.server import create_app


def _client(tmp_path):
    cfg = Config()
    cfg.runtime_store = str(tmp_path / "runtime.json")
    cfg.photos_dir = str(tmp_path / "photos")
    return cfg, TestClient(create_app(cfg))


def test_api_config_get_and_post(tmp_path):
    cfg, c = _client(tmp_path)
    body = c.get("/api/config").json()
    assert body["layout_name"] == "dash"
    assert "layouts" in body and "clock" in body["layouts"]   # 可选布局列表

    r = c.post("/api/config", json={"layout_name": "clock", "usage_budget_usd": 30})
    assert r.status_code == 200
    assert cfg.layout_name == "clock"                          # 内存即时生效
    import os
    assert os.path.exists(cfg.runtime_store)                   # 持久化
    assert c.get("/api/config").json()["layout_name"] == "clock"


def test_api_config_rejects_unknown_layout(tmp_path):
    cfg, c = _client(tmp_path)
    r = c.post("/api/config", json={"layout_name": "bogus"})
    assert r.status_code == 400
    assert cfg.layout_name == "dash"                           # 未被改


def test_api_photos_upload_list_delete(tmp_path):
    cfg, c = _client(tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    assert c.post("/api/photos", files={"file": ("a.png", png, "image/png")}).status_code == 200
    assert "a.png" in c.get("/api/photos").json()
    assert c.delete("/api/photos/a.png").status_code == 200
    assert "a.png" not in c.get("/api/photos").json()


def test_api_refresh_bumps_token(tmp_path):
    cfg, c = _client(tmp_path)
    t0 = c.get("/api/refresh-token").json()["token"]
    r = c.post("/api/refresh")
    assert r.status_code == 200
    t1 = c.get("/api/refresh-token").json()["token"]
    assert t1 == t0 + 1   # 每次请求刷新, 令牌递增(设备据此判断要不要立即拉帧)
