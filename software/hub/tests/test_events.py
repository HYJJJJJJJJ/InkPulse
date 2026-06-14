from inkpulse_hub.collectors.events import EventStore, AGENDA_LIMIT
import time


def _now(y, m, d):
    return time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))


def test_add_list_delete(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    e = s.add("团队周会", "2026-06-14", "14:30")
    assert e["title"] == "团队周会" and e["date"] == "2026-06-14" and e["time"] == "14:30"
    assert len(e["id"]) == 8
    assert [x["title"] for x in s.list()] == ["团队周会"]
    s.delete(e["id"])
    assert s.list() == []


def test_list_sorted_allday_before_timed(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    s.add("定时", "2026-06-14", "09:00")
    s.add("全天", "2026-06-14", "")        # 同日全天 -> 排在 09:00 之前
    s.add("次日", "2026-06-15", "08:00")
    assert [x["title"] for x in s.list()] == ["全天", "定时", "次日"]


def test_upcoming_filters_past(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    s.add("昨天", "2026-06-13", "10:00")
    s.add("今天", "2026-06-14", "10:00")
    s.add("明天", "2026-06-15", "10:00")
    up = s.upcoming(_now(2026, 6, 14), 10)
    assert [x["title"] for x in up] == ["今天", "明天"]      # 昨天被过滤


def test_upcoming_respects_limit(tmp_path):
    s = EventStore(str(tmp_path / "events.json"))
    for i in range(5):
        s.add(f"e{i}", "2026-06-20", f"0{i}:00")
    assert len(s.upcoming(_now(2026, 6, 14), 3)) == 3


def test_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "events.json"
    p.write_text("{not a list", encoding="utf-8")
    assert EventStore(str(p)).list() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "events.json")
    EventStore(path).add("持久", "2026-06-14", "")
    assert [x["title"] for x in EventStore(path).list()] == ["持久"]


def test_agenda_limit_is_int():
    assert isinstance(AGENDA_LIMIT, int) and AGENDA_LIMIT > 0
