# inkpulse_hub/server.py
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from .config import Config
from .state import HubState
from .render.engine import render_frame


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="InkPulse Hub")
    state = HubState(cfg)
    app.state.hub = state
    app.state.cfg = cfg

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/frame")
    def frame(request: Request, t: float | None = None, h: float | None = None):
        if t is not None or h is not None:
            state.set_env(t, h)
        f = render_frame(cfg, state.build_render_state())
        if request.headers.get("if-none-match") == f.etag:
            return Response(status_code=304)
        return Response(
            content=f.body,
            media_type="application/octet-stream",
            headers={"ETag": f.etag, "X-Next-Refresh": str(cfg.refresh_periodic_s)},
        )

    @app.get("/preview.png")
    def preview():
        f = render_frame(cfg, state.build_render_state())
        return Response(content=f.png_bytes, media_type="image/png")

    # ---- 字体验证: 运行时热切换 CJK 字体, 设备下次拉帧即生效 ----
    @app.get("/debug/font")
    def debug_font(path: str | None = None):
        from .render import widgets
        widgets.set_font(path)
        return {"ok": True, "font": widgets.current_font()}

    @app.post("/ingest/claude-status")
    async def ingest(request: Request):
        data = await request.json()
        state.set_claude_status(data.get("state", "idle"), data.get("project"))
        return JSONResponse({"ok": True})

    # ---- 待办 Web UI 与 API ----
    import os
    from fastapi.responses import HTMLResponse

    _html_path = os.path.join(os.path.dirname(__file__), "web", "todos.html")

    @app.get("/todos", response_class=HTMLResponse)
    def todos_page():
        with open(_html_path, "r", encoding="utf-8") as fh:
            return HTMLResponse(fh.read())

    @app.get("/api/todos")
    def api_list():
        return [t.__dict__ for t in state.todos.list()]

    @app.post("/api/todos")
    async def api_add(request: Request):
        data = await request.json()
        return state.todos.add(data["text"]).__dict__

    @app.post("/api/todos/{tid}/toggle")
    def api_toggle(tid: str):
        state.todos.toggle(tid)
        return {"ok": True}

    @app.delete("/api/todos/{tid}")
    def api_delete(tid: str):
        state.todos.delete(tid)
        return {"ok": True}

    return app
