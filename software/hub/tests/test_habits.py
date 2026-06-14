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
