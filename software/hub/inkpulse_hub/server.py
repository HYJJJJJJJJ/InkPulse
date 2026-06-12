# inkpulse_hub/server.py
from fastapi import FastAPI, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from .config import Config, save_runtime, RUNTIME_FIELDS
from .state import HubState
from .render.engine import render_frame, LAYOUTS


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="InkPulse Hub")
    state = HubState(cfg)
    app.state.hub = state
    app.state.cfg = cfg

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/frame")
    def frame(request: Request, t: float | None = None, h: float | None = None,
              rssi: int | None = None):
        if t is not None or h is not None or rssi is not None:
            state.set_env(t, h, rssi)
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

    # ---- 配置中心: 选布局 / 调参数 ----
    @app.get("/config", response_class=HTMLResponse)
    def config_page():
        cp = os.path.join(os.path.dirname(__file__), "web", "config.html")
        with open(cp, "r", encoding="utf-8") as fh:
            return HTMLResponse(fh.read())

    @app.get("/api/config")
    def api_config_get():
        data = {f: getattr(cfg, f) for f in RUNTIME_FIELDS}
        data["layouts"] = list(LAYOUTS.keys())   # 供 UI 列布局选项
        return data

    @app.post("/api/config")
    async def api_config_set(request: Request):
        data = await request.json()
        if "layout_name" in data and data["layout_name"] not in LAYOUTS:
            return JSONResponse({"error": "unknown layout"}, status_code=400)
        for k in RUNTIME_FIELDS:
            if k in data:
                setattr(cfg, k, data[k])
        save_runtime(cfg, cfg.runtime_store)     # 持久化 + 闭包 cfg 即时生效
        return {"ok": True}

    # ---- 照片管理(photo 布局用) ----
    def _list_photos():
        os.makedirs(cfg.photos_dir, exist_ok=True)
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
        return sorted(f for f in os.listdir(cfg.photos_dir) if f.lower().endswith(exts))

    @app.get("/api/photos")
    def api_photos_list():
        return _list_photos()

    @app.post("/api/photos")
    async def api_photos_upload(file: UploadFile = File(...)):
        os.makedirs(cfg.photos_dir, exist_ok=True)
        name = os.path.basename(file.filename or "upload")
        with open(os.path.join(cfg.photos_dir, name), "wb") as fh:
            fh.write(await file.read())
        return {"ok": True, "name": name}

    @app.delete("/api/photos/{name}")
    def api_photos_delete(name: str):
        p = os.path.join(cfg.photos_dir, os.path.basename(name))
        if os.path.exists(p):
            os.remove(p)
        return {"ok": True}

    @app.get("/photos/{name}")
    def photo_file(name: str):
        from fastapi.responses import FileResponse
        p = os.path.join(cfg.photos_dir, os.path.basename(name))
        return FileResponse(p) if os.path.exists(p) else Response(status_code=404)

    return app
