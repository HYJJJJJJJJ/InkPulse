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

    @app.post("/ingest/claude-status")
    async def ingest(request: Request):
        data = await request.json()
        state.set_claude_status(data.get("state", "idle"), data.get("project"))
        return JSONResponse({"ok": True})

    return app
