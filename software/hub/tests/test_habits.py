from inkpulse_hub.collectors.habits import HabitStore


def test_add_list_delete(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    assert h["name"] == "运动" and len(h["id"]) == 8
    assert [x["name"] for x in store.list()] == ["运动"]

    store.add("阅读")
    assert [x["name"] for x in store.list()] == ["运动", "阅读"]

    store.delete(h["id"])
    assert [x["name"] for x in store.list()] == ["阅读"]


def test_missing_file_is_empty(tmp_path):
    assert HabitStore(str(tmp_path / "nope.json")).list() == []


def test_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "habits.json"
    p.write_text("{not json", encoding="utf-8")
    assert HabitStore(str(p)).list() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "habits.json")
    HabitStore(path).add("喝水")
    assert [x["name"] for x in HabitStore(path).list()] == ["喝水"]


def test_toggle_roundtrip_and_is_done(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    assert store.is_done(h["id"], "2026-06-10") is False
    store.toggle(h["id"], "2026-06-10")
    assert store.is_done(h["id"], "2026-06-10") is True
    store.toggle(h["id"], "2026-06-10")              # 再次 toggle => 取消
    assert store.is_done(h["id"], "2026-06-10") is False


def test_delete_clears_log_entries(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    store.toggle(h["id"], "2026-06-10")
    store.delete(h["id"])
    raw = HabitStore(str(tmp_path / "habits.json"))._read()
    assert all(h["id"] not in day for day in raw["log"].values())


def test_week_view_structure(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    h = store.add("运动")
    store.toggle(h["id"], "2026-06-08")   # 周一
    now = __import__("time").mktime((2026, 6, 14, 12, 0, 0, 0, 0, -1))
    rows, today_idx = store.week_view(now)
    assert today_idx == 6
    assert rows == [{"name": "运动", "days": [True, False, False, False, False, False, False]}]


def test_week_view_empty_when_no_habits(tmp_path):
    store = HabitStore(str(tmp_path / "habits.json"))
    now = __import__("time").mktime((2026, 6, 14, 12, 0, 0, 0, 0, -1))
    rows, today_idx = store.week_view(now)
    assert rows == [] and 0 <= today_idx <= 6
