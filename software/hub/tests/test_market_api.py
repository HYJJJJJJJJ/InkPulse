from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 market_cache=str(tmp_path / "m.json"),
                 runtime_store=str(tmp_path / "rt.json"))
    return create_app(cfg)


def test_get_market_empty(tmp_path):
    r = TestClient(_app(tmp_path)).get("/api/market").json()
    assert r["symbols"] == [] and r["quotes"] == []


def test_add_symbol_and_list(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    assert c.post("/api/market/symbols", json={"type": "cn", "code": "SH000001"}).status_code == 200
    syms = c.get("/api/market/symbols").json()
    assert syms == [{"type": "cn", "code": "sh000001"}]          # cn 规范化小写
    assert app.state.cfg.market_symbols == [{"type": "cn", "code": "sh000001"}]


def test_add_crypto_uppercased(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post("/api/market/symbols", json={"type": "crypto", "code": "btc-usdt"})
    assert c.get("/api/market/symbols").json() == [{"type": "crypto", "code": "BTC-USDT"}]


def test_add_rejects_bad_type(tmp_path):
    assert TestClient(_app(tmp_path)).post("/api/market/symbols",
        json={"type": "fund", "code": "x"}).status_code == 400


def test_add_rejects_blank_code(tmp_path):
    assert TestClient(_app(tmp_path)).post("/api/market/symbols",
        json={"type": "cn", "code": "  "}).status_code == 400


def test_add_duplicate_ignored(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post("/api/market/symbols", json={"type": "cn", "code": "sh000001"})
    c.post("/api/market/symbols", json={"type": "cn", "code": "sh000001"})
    assert len(c.get("/api/market/symbols").json()) == 1


def test_delete_symbol(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post("/api/market/symbols", json={"type": "cn", "code": "sh000001"})
    assert c.request("DELETE", "/api/market/symbols",
                     json={"type": "cn", "code": "sh000001"}).status_code == 200
    assert c.get("/api/market/symbols").json() == []
