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
