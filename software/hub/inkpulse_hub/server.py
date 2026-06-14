# inkpulse_hub/server.py
from fastapi import FastAPI, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from .config import Config, save_runtime, RUNTIME_FIELDS
from .state import HubState
from .render.engine import render_frame
from .render import layouts as L
from .render.registry import REGISTRY
import time
import datetime as _dt
from .collectors.habits import week_dates
from .collectors import weather as weather_mod


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
        if t is not None:
            state.env_history.append(time.time(), t)
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

    # ---- 习惯打卡 API ----
    @app.get("/api/habits")
    def api_habits_list():
        dates, today_idx = week_dates(time.time())
        habits = state.habits.list()
        done = {h["id"]: [state.habits.is_done(h["id"], dt) for dt in dates]
                for h in habits}
        return {"habits": habits, "week": dates, "done": done, "today_idx": today_idx}

    @app.post("/api/habits")
    async def api_habits_add(request: Request):
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "empty name"}, status_code=400)
        return state.habits.add(name)

    @app.delete("/api/habits/{hid}")
    def api_habits_delete(hid: str):
        state.habits.delete(hid)
        return {"ok": True}

    @app.post("/api/habits/{hid}/toggle")
    async def api_habits_toggle(hid: str, request: Request):
        data = await request.json()
        date_iso = (data.get("date") or "").strip()
        if hid not in {h["id"] for h in state.habits.list()}:
            return JSONResponse({"error": "unknown habit"}, status_code=404)
        dates, today_idx = week_dates(time.time())
        if date_iso > dates[today_idx]:        # ISO 串字典序即日期序
            return JSONResponse({"error": "future date"}, status_code=400)
        state.habits.toggle(hid, date_iso)
        return {"ok": True}

    @app.get("/api/weather/search")
    def api_weather_search(q: str = ""):
        return weather_mod.geocode(q)

    @app.post("/api/weather/location")
    async def api_weather_set_location(request: Request):
        data = await request.json()
        lat, lon, name = data.get("lat"), data.get("lon"), data.get("name")
        if lat is None or lon is None or not (name or "").strip():
            return JSONResponse({"error": "lat/lon/name required"}, status_code=400)
        cfg.weather_lat, cfg.weather_lon, cfg.weather_place = float(lat), float(lon), name.strip()
        save_runtime(cfg, cfg.runtime_store)
        state.weather.clear()
        return {"ok": True}

    @app.delete("/api/weather/location")
    def api_weather_del_location():
        cfg.weather_lat, cfg.weather_lon, cfg.weather_place = None, None, ""
        save_runtime(cfg, cfg.runtime_store)
        state.weather.clear()
        return {"ok": True}

    @app.get("/api/weather")
    def api_weather_get():
        w = None
        if cfg.weather_lat is not None and cfg.weather_lon is not None:
            w = state.weather.current(time.time())
        return {"place": cfg.weather_place, "lat": cfg.weather_lat,
                "lon": cfg.weather_lon, "weather": w}

    def _valid_event(title, date, time):
        if not (title or "").strip():
            return False
        try:
            _dt.date.fromisoformat(date)
        except (TypeError, ValueError):
            return False
        if time:
            try:
                _dt.time.fromisoformat(time)
            except (TypeError, ValueError):
                return False
        return True

    @app.get("/api/events")
    def api_events_list():
        return state.events.list()

    @app.post("/api/events")
    async def api_events_add(request: Request):
        data = await request.json()
        title, date, time = data.get("title", ""), data.get("date", ""), data.get("time", "") or ""
        if not _valid_event(title, date, time):
            return JSONResponse({"error": "invalid event"}, status_code=400)
        return state.events.add(title.strip(), date, time)

    @app.delete("/api/events/{eid}")
    def api_events_delete(eid: str):
        state.events.delete(eid)
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
        data["layouts"] = list(L.load_store(cfg.layouts_store)["layouts"].keys())
        return data

    @app.post("/api/config")
    async def api_config_set(request: Request):
        data = await request.json()
        names = L.load_store(cfg.layouts_store)["layouts"]
        if "layout_name" in data and data["layout_name"] not in names:
            return JSONResponse({"error": "unknown layout"}, status_code=400)
        for k in RUNTIME_FIELDS:
            if k in data:
                setattr(cfg, k, data[k])
        save_runtime(cfg, cfg.runtime_store)
        return {"ok": True}

    # ---- 布局编辑: 网格 + widget 目录 + 自定义布局 CRUD ----
    @app.get("/api/layouts")
    def api_layouts_get():
        store = L.load_store(cfg.layouts_store)
        widgets = [{"name": s.name, "label": s.label,
                    "default_span": s.default_span, "params": s.params}
                   for s in REGISTRY.values()]
        return {"grid": store["grid"], "layouts": store["layouts"], "widgets": widgets}

    @app.put("/api/layouts/{name}")
    async def api_layouts_put(name: str, request: Request):
        data = await request.json()
        placements = data.get("placements", [])
        grid = L.load_store(cfg.layouts_store)["grid"]
        for p in placements:
            if p.get("widget") not in REGISTRY:
                return JSONResponse({"error": f"unknown widget {p.get('widget')}"}, status_code=400)
            try:
                col, row = int(p["col"]), int(p["row"])
                cs, rs = int(p["colspan"]), int(p["rowspan"])
            except (KeyError, TypeError, ValueError):
                return JSONResponse({"error": "bad placement"}, status_code=400)
            if not (0 <= col and 0 <= row and cs >= 1 and rs >= 1
                    and col + cs <= grid["cols"] and row + rs <= grid["rows"]):
                return JSONResponse({"error": "out of grid"}, status_code=400)
        try:
            L.save_layout(cfg.layouts_store, name, placements)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"ok": True}

    @app.delete("/api/layouts/{name}")
    def api_layouts_delete(name: str):
        try:
            L.delete_layout(cfg.layouts_store, name)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"ok": True}

    # ---- 照片管理(photo 布局用) ----
    def _list_photos():
        os.makedirs(cfg.photos_dir, exist_ok=True)
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
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

    # ---- 刷新令牌: web 请求刷新真机 -> 令牌+1; 设备每 ~10s 轮询, 变化即立即拉帧刷屏 ----
    _refresh = {"token": 0}

    @app.post("/api/refresh")
    def api_refresh():
        _refresh["token"] += 1
        return {"ok": True, "token": _refresh["token"]}

    @app.get("/api/refresh-token")
    def api_refresh_token():
        return {"token": _refresh["token"]}

    return app
