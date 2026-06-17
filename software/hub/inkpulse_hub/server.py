# inkpulse_hub/server.py
import asyncio
import json
from fastapi import FastAPI, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from .config import Config, save_runtime, RUNTIME_FIELDS
from .state import HubState
from .render.engine import render_frame
from .render.profiles import get_profile
from .render import layouts as L
from .render.registry import REGISTRY
import time
import datetime as _dt
from .collectors.habits import week_dates
from .collectors import weather as weather_mod


async def sse_stream(state: HubState, is_disconnected, *, poll: float = 1.0):
    """SSE 事件生成器: web 同步令牌变化即推送 data 事件, 否则发心跳维持连接。
    抽成模块级以便直接单测(不经 TestClient 无限流, 避免死锁)。
    is_disconnected: 返回 bool 的 async 可调用; poll: 轮询间隔(秒)。"""
    last = None
    while True:
        if await is_disconnected():
            break
        tok = state.web_token
        if tok != last:
            last = tok
            payload = {"token": tok, "device_pulled_at": state.device_frame_pulled_at}
            yield f"data: {json.dumps(payload)}\n\n"
        else:
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll)


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="InkPulse Hub")
    state = HubState(cfg)
    app.state.hub = state
    app.state.cfg = cfg

    def _lpid() -> str:
        """web 布局/网格跟随真机配对的 panel; 未配对回退默认 profile。"""
        return cfg.active_panel or L.DEFAULT_PID

    @app.middleware("http")
    async def _bump_web_on_write(request: Request, call_next):
        """任何成功的写请求(配置/数据)都递增 web 同步令牌, 让网页经 SSE 自动刷新。
        设备 refresh_token 不在此处触碰; /frame(GET) 经 record_device_frame 单独 bump。"""
        resp = await call_next(request)
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and 200 <= resp.status_code < 300:
            p = request.url.path
            if p.startswith("/api/") or p.startswith("/ingest/"):
                state.bump_web()
        return resp

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/frame")
    def frame(request: Request, t: float | None = None, h: float | None = None,
              rssi: int | None = None, panel: str | None = None):
        if t is not None or h is not None or rssi is not None:
            state.set_env(t, h, rssi)
        if t is not None:
            state.env_history.append(time.time(), t)
        # 真机上报屏型 = web 各处的事实源; 变化即持久化(跨重启记住配对)。
        if panel and panel != cfg.active_panel:
            cfg.active_panel = panel
            save_runtime(cfg, cfg.runtime_store)
        f = render_frame(cfg, state.build_render_state(), get_profile(panel))
        if request.headers.get("if-none-match") == f.etag:
            return Response(status_code=304)   # 设备复用缓存, 屏上内容未变, 不更新记录
        # 设备真正取走了一帧 = 此刻物理显示的内容, 记录下来供网页镜像
        state.record_device_frame(f.png_bytes, f.etag, time.time())
        # 周期≤60s 时把"下次刷新"对齐到下一个整分钟, 让真机在 :00 附近醒来,
        # 时钟显示尽量贴合真实时间(自校正: 任何相位漂移下一周期即被拉回整分钟)。
        # 固件最小钳制 30s; 稳态拉帧落在 :00~:21, 余 39~60s, 不触发钳制。
        period = cfg.refresh_periodic_s
        next_refresh = period if period > 60 else max(1, 60 - int(time.time() % 60))
        return Response(
            content=f.body,
            media_type="application/octet-stream",
            headers={"ETag": f.etag, "X-Next-Refresh": str(next_refresh)},
        )

    @app.get("/preview.png")
    def preview(panel: str | None = None):
        # 显式 panel 优先; 否则跟随真机配对的屏型(而非写死 7.5 寸)。
        f = render_frame(cfg, state.build_render_state(),
                         get_profile(panel or cfg.active_panel or None))
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

    @app.post("/ingest/agent-tasks")
    async def ingest_agent_tasks(request: Request):
        data = await request.json()
        project = (data.get("project") or "").strip()
        if not project:
            return JSONResponse({"error": "project required"}, status_code=400)
        state.agent_tasks.ingest(time.time(), project,
                                 tasks=data.get("tasks"),
                                 highlights=data.get("highlights"))
        return JSONResponse({"ok": True})

    # ---- 待办 API (页面由 Vue SPA 接管, 见末尾 StaticFiles 挂载) ----
    import os

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

    # ---- 行情 widget API ----
    def _norm_symbol(data):
        t = data.get("type")
        code = (data.get("code") or "").strip()
        if t not in ("cn", "crypto") or not code:
            return None
        code = code.lower() if t == "cn" else code.upper()
        return {"type": t, "code": code}

    @app.get("/api/market")
    def api_market_get():
        return {"symbols": cfg.market_symbols, "quotes": state.market.current()}

    @app.get("/api/market/symbols")
    def api_market_symbols():
        return cfg.market_symbols

    @app.post("/api/market/symbols")
    async def api_market_add(request: Request):
        sym = _norm_symbol(await request.json())
        if sym is None:
            return JSONResponse({"error": "invalid symbol"}, status_code=400)
        if sym not in cfg.market_symbols:
            cfg.market_symbols = cfg.market_symbols + [sym]
            save_runtime(cfg, cfg.runtime_store)
            state.market.clear()
        return {"ok": True}

    @app.delete("/api/market/symbols")
    async def api_market_del(request: Request):
        sym = _norm_symbol(await request.json())
        if sym is None:
            return JSONResponse({"error": "invalid symbol"}, status_code=400)
        cfg.market_symbols = [s for s in cfg.market_symbols if s != sym]
        save_runtime(cfg, cfg.runtime_store)
        state.market.clear()
        return {"ok": True}

    # ---- 配置中心: 选布局 / 调参数 (页面由 Vue SPA 接管) ----
    @app.get("/api/config")
    def api_config_get():
        data = {f: getattr(cfg, f) for f in RUNTIME_FIELDS}
        data["layouts"] = list(L.load_store(cfg.layouts_store, _lpid())["layouts"].keys())
        return data

    @app.post("/api/config")
    async def api_config_set(request: Request):
        data = await request.json()
        names = L.load_store(cfg.layouts_store, _lpid())["layouts"]
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
        store = L.load_store(cfg.layouts_store, _lpid())
        widgets = [{"name": s.name, "label": s.label,
                    "default_span": s.default_span, "params": s.params}
                   for s in REGISTRY.values()]
        return {"grid": store["grid"], "layouts": store["layouts"], "widgets": widgets}

    @app.put("/api/layouts/{name}")
    async def api_layouts_put(name: str, request: Request):
        data = await request.json()
        placements = data.get("placements", [])
        grid = L.load_store(cfg.layouts_store, _lpid())["grid"]
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
            L.save_layout(cfg.layouts_store, name, placements, profile=_lpid())
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"ok": True}

    @app.delete("/api/layouts/{name}")
    def api_layouts_delete(name: str):
        try:
            L.delete_layout(cfg.layouts_store, name, profile=_lpid())
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

    # ---- 真机当前帧镜像: 网页查看设备此刻物理显示的内容 ----
    @app.get("/api/device/frame.png")
    def api_device_frame():
        if state.device_frame_png is not None:
            return Response(content=state.device_frame_png, media_type="image/png")
        # 设备尚未拉过帧: 回退到当前预览(按配对屏型, 而非写死 7.5 寸), 不报错
        f = render_frame(cfg, state.build_render_state(),
                         get_profile(cfg.active_panel or None))
        return Response(content=f.png_bytes, media_type="image/png")

    @app.get("/api/device/status")
    def api_device_status():
        pulled = state.device_frame_pulled_at
        env = state.device_frame_env
        return {
            "pulled_at": pulled,
            "age_s": (time.time() - pulled) if pulled is not None else None,
            "rssi": env.get("rssi"),
            "temp": env.get("temp"),
            "humidity": env.get("humidity"),
            "etag": state.device_frame_etag,
            "panel": cfg.active_panel or None,
        }

    # ---- SSE 实时流: web 同步令牌变化即推送, 网页据此自动刷新预览与真机帧 ----
    @app.get("/api/stream")
    async def api_stream(request: Request):
        return StreamingResponse(
            sse_stream(state, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---- Vue SPA: 挂载 web-ui/dist 到 /, 接管配置中心页面 ----
    # 必须在所有 /api、/frame、/preview.png、/photos 路由之后挂载(显式路由优先匹配)。
    # dist 未构建(纯源码 checkout / 测试)时跳过, 开发期走 vite dev server 反代。
    _dist = os.path.join(os.path.dirname(__file__), "..", "web-ui", "dist")
    if os.path.isdir(_dist):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=_dist, html=True), name="webui")

    return app
