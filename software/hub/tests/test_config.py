from inkpulse_hub.config import load_config, Config


def test_defaults_when_empty(tmp_path):
    cfg = load_config(None)
    assert isinstance(cfg, Config)
    assert cfg.refresh_min_interval_s == 60
    assert cfg.refresh_periodic_s == 600
    assert cfg.layout == ["header_clock_env", "claude_status", "usage", "todos"]


def test_yaml_override(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "refresh:\n  min_interval_s: 30\n"
        "sources:\n  photos_dir: /tmp/pics\n"
        "layout:\n  widgets: [claude_status]\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.refresh_min_interval_s == 30
    assert cfg.photos_dir == "/tmp/pics"
    assert cfg.layout == ["claude_status"]


def test_layouts_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    # 默认值在家目录下
    assert Config().layouts_store.endswith("inkpulse/layouts.json")
    # 可被 config.yaml 的 sources.layouts_store 覆盖
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  layouts_store: /tmp/my-layouts.json\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.layouts_store == "/tmp/my-layouts.json"


def test_habits_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().habits_store.endswith("inkpulse/habits.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  habits_store: /tmp/h.json\n", encoding="utf-8")
    assert load_config(str(p)).habits_store == "/tmp/h.json"


def test_env_history_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().env_history_store.endswith("inkpulse/env_history.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  env_history_store: /tmp/e.json\n", encoding="utf-8")
    assert load_config(str(p)).env_history_store == "/tmp/e.json"


def test_events_store_default_and_override(tmp_path):
    from inkpulse_hub.config import Config, load_config
    assert Config().events_store.endswith("inkpulse/events.json")
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  events_store: /tmp/ev.json\n", encoding="utf-8")
    assert load_config(str(p)).events_store == "/tmp/ev.json"


def test_weather_config_fields(tmp_path):
    from inkpulse_hub.config import Config, load_config, RUNTIME_FIELDS, save_runtime, load_runtime
    c = Config()
    assert c.weather_cache.endswith("inkpulse/weather_cache.json")
    assert c.weather_lat is None and c.weather_lon is None and c.weather_place == ""
    assert {"weather_lat", "weather_lon", "weather_place"} <= set(RUNTIME_FIELDS)
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  weather_cache: /tmp/w.json\n", encoding="utf-8")
    assert load_config(str(p)).weather_cache == "/tmp/w.json"
    c.weather_lat, c.weather_lon, c.weather_place = 30.29, 120.16, "杭州"
    rt = tmp_path / "rt.json"
    save_runtime(c, str(rt))
    c2 = Config()
    load_runtime(c2, str(rt))
    assert c2.weather_place == "杭州" and c2.weather_lat == 30.29
