from inkpulse_hub.config import Config, save_runtime, load_runtime


def test_runtime_roundtrip(tmp_path):
    cfg = Config()
    cfg.layout_name = "clock"
    cfg.usage_budget_usd = 50.0
    cfg.refresh_periodic_s = 300
    p = tmp_path / "runtime.json"
    save_runtime(cfg, str(p))

    cfg2 = Config()
    load_runtime(cfg2, str(p))
    assert cfg2.layout_name == "clock"
    assert cfg2.usage_budget_usd == 50.0
    assert cfg2.refresh_periodic_s == 300


def test_load_runtime_missing_file_noop(tmp_path):
    cfg = Config()
    load_runtime(cfg, str(tmp_path / "nope.json"))   # 不存在不崩
    assert cfg.layout_name == "dash"                 # 保持默认


def test_runtime_ignores_unknown_keys(tmp_path):
    p = tmp_path / "runtime.json"
    p.write_text('{"layout_name":"usage","evil":"x"}', encoding="utf-8")
    cfg = Config()
    load_runtime(cfg, str(p))
    assert cfg.layout_name == "usage"
    assert not hasattr(cfg, "evil")
