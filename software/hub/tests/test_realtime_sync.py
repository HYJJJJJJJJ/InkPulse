import asyncio
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app, sse_stream
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"))
    return create_app(cfg)


def test_data_write_bumps_web_token(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    before = app.state.hub.web_token
    c.post("/api/todos", json={"text": "买牛奶"})
    assert app.state.hub.web_token > before


def test_device_pull_bumps_web_token(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    before = app.state.hub.web_token
    c.get("/frame")
    assert app.state.hub.web_token > before


def test_device_refresh_token_unchanged_by_data_or_pull(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    tok0 = c.get("/api/refresh-token").json()["token"]
    c.post("/api/todos", json={"text": "x"})
    c.get("/frame")
    tok1 = c.get("/api/refresh-token").json()["token"]
    assert tok1 == tok0   # 设备令牌只由 /api/refresh 触发


def test_manual_refresh_bumps_device_token(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    tok0 = c.get("/api/refresh-token").json()["token"]
    c.post("/api/refresh")
    tok1 = c.get("/api/refresh-token").json()["token"]
    assert tok1 == tok0 + 1


def _drain(state, max_iters=3):
    """驱动 sse_stream: 跑 max_iters 次迭代后断开, 收集产出的事件块。"""
    n = {"i": 0}

    async def disc():
        n["i"] += 1
        return n["i"] > max_iters

    async def run():
        out = []
        async for chunk in sse_stream(state, disc, poll=0):
            out.append(chunk)
        return out

    return asyncio.run(run())


def test_stream_emits_initial_token_event(tmp_path):
    app = _app(tmp_path)
    out = _drain(app.state.hub, max_iters=1)
    assert any(c.startswith("data:") and '"token"' in c for c in out)


def test_stream_emits_new_event_on_token_change(tmp_path):
    app = _app(tmp_path)
    state = app.state.hub
    # 第一拍发初值; 中途 bump; 应再发一条带新 token 的 data 事件
    n = {"i": 0}

    async def disc():
        n["i"] += 1
        if n["i"] == 2:
            state.bump_web()      # 在两次轮询之间改动
        return n["i"] > 4

    async def run():
        out = []
        async for chunk in sse_stream(state, disc, poll=0):
            out.append(chunk)
        return out

    out = asyncio.run(run())
    data_events = [c for c in out if c.startswith("data:")]
    assert len(data_events) >= 2   # 初值 + 变更各一条
