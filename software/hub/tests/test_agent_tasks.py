from inkpulse_hub.collectors.agent_tasks import AgentTaskStore, STALE_S


def test_ingest_tasks_then_current(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "InkPulse", tasks=[{"content": "写端点", "status": "in_progress"}])
    c = s.current(1000.0)
    assert c["project"] == "InkPulse" and c["age_s"] == 0
    assert c["tasks"] == [{"content": "写端点", "status": "in_progress"}]
    assert c["highlights"] == []


def test_same_project_merges_fields(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "InkPulse", tasks=[{"content": "A", "status": "pending"}])
    s.ingest(1100.0, "InkPulse", highlights=["记得加测试"])   # 只更 highlights
    c = s.current(1100.0)
    assert [t["content"] for t in c["tasks"]] == ["A"]        # tasks 保留
    assert c["highlights"] == ["记得加测试"]


def test_different_project_replaces(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "InkPulse", tasks=[{"content": "A", "status": "pending"}],
             highlights=["h1"])
    s.ingest(1200.0, "Other", tasks=[{"content": "B", "status": "pending"}])
    c = s.current(1200.0)
    assert c["project"] == "Other"
    assert [t["content"] for t in c["tasks"]] == ["B"]
    assert c["highlights"] == []                              # 旧项目 highlights 清空


def test_tasks_normalized(tmp_path):
    s = AgentTaskStore(str(tmp_path / "a.json"))
    s.ingest(1000.0, "P", tasks=[
        {"content": "ok", "status": "weird"},   # 未知 status -> pending
        {"content": "", "status": "pending"},   # 空 content -> 丢弃
        {"status": "pending"},                   # 无 content -> 丢弃
    ])
    assert s.current(1000.0)["tasks"] == [{"content": "ok", "status": "pending"}]


def test_age_and_corrupt(tmp_path):
    p = tmp_path / "a.json"
    s = AgentTaskStore(str(p))
    s.ingest(1000.0, "P", tasks=[{"content": "x", "status": "pending"}])
    assert s.current(1000.0 + 5)["age_s"] == 5
    p.write_text("{bad", encoding="utf-8")
    assert AgentTaskStore(str(p)).current(0.0) is None        # 坏文件 -> None
    assert STALE_S == 7200
