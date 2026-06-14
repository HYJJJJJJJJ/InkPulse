from inkpulse_hub.config import Config
from inkpulse_hub.state import HubState


def test_render_state_has_daily_and_projects(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")   # 不存在 -> 聚合返回空/全零, 不崩
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "usage_daily" in state and isinstance(state["usage_daily"], list)
    assert "usage_projects" in state and isinstance(state["usage_projects"], list)
    assert len(state["usage_daily"]) == 14   # 默认 14 天全零桶


def test_render_state_has_habits(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "habits" in state and isinstance(state["habits"], list)
    assert "habit_today_idx" in state and 0 <= state["habit_today_idx"] <= 6


def test_render_state_has_env_history(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "env_history" in state and isinstance(state["env_history"], list)


def test_render_state_weather_none_without_location(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert state["weather"] is None and state["weather_place"] is None


def test_render_state_has_events(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert "events" in state and isinstance(state["events"], list)


def test_render_state_weather_from_fresh_cache(tmp_path):
    import json
    now = 1718000000.0
    raw = {"current": {"temperature_2m": 23.4, "weather_code": 2},
           "daily": {"time": ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13"],
                     "weather_code": [2, 0, 3, 61],
                     "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
                     "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}}
    wpath = tmp_path / "w.json"
    wpath.write_text(json.dumps({"fetched_at": now, "lat": 30.29, "lon": 120.16,
                                 "raw": raw}), encoding="utf-8")
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(wpath)
    cfg.weather_lat, cfg.weather_lon, cfg.weather_place = 30.29, 120.16, "杭州"
    st = HubState(cfg)
    state = st.build_render_state(now=now)
    assert state["weather"]["cur_temp"] == 23.4
    assert state["weather_place"] == "杭州"


def test_render_state_market_empty_without_symbols(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    cfg.market_cache = str(tmp_path / "m.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert state["market"] == []


def test_render_state_market_from_fresh_cache(tmp_path):
    import json
    now = 1718000000.0
    quotes = [{"type": "cn", "code": "sh000001", "name": "上证指数", "price": 4031.51, "change_pct": 1.12}]
    mpath = tmp_path / "m.json"
    sig = [["cn", "sh000001"]]
    mpath.write_text(json.dumps({"fetched_at": now, "sig": sig, "quotes": quotes}), encoding="utf-8")
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    cfg.market_cache = str(mpath)
    cfg.market_symbols = [{"type": "cn", "code": "sh000001"}]   # 与缓存 sig 一致 -> 不触发刷新线程
    st = HubState(cfg)
    state = st.build_render_state(now=now)
    assert [q["code"] for q in state["market"]] == ["sh000001"]
