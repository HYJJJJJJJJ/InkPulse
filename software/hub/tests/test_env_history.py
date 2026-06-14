from inkpulse_hub.collectors.env_history import EnvHistoryStore, RETENTION_S


def test_append_then_window(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, 23.4)
    s.append(1600.0, 23.6)
    assert s.window(1600.0) == [[1000.0, 23.4], [1600.0, 23.6]]


def test_append_rejects_invalid(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, None)
    s.append(1000.0, -100.0)     # 哨兵/越界
    s.append(1000.0, 999.0)      # 越界
    s.append(1000.0, "nan-ish")  # 非数值
    assert s.window(1000.0) == []


def test_prunes_older_than_24h(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, 20.0)                         # 很旧
    s.append(1000.0 + RETENTION_S + 1, 21.0)       # 触发裁剪 -> 旧点被裁
    assert s.window(1000.0 + RETENTION_S + 1) == [[1000.0 + RETENTION_S + 1, 21.0]]


def test_window_filters_by_now(tmp_path):
    s = EnvHistoryStore(str(tmp_path / "env.json"))
    s.append(1000.0, 20.0)
    # now 比采样晚超过 24h -> 该点落在窗口外
    assert s.window(1000.0 + RETENTION_S + 5) == []


def test_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "env.json"
    p.write_text("{not a list", encoding="utf-8")
    assert EnvHistoryStore(str(p)).window(0.0) == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "env.json")
    EnvHistoryStore(path).append(1000.0, 22.2)
    assert EnvHistoryStore(path).window(1000.0) == [[1000.0, 22.2]]
