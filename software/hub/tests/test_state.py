import time
from inkpulse_hub.state import HubState
from inkpulse_hub.config import Config


def test_state_builds_render_dict(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "nolog"),
                 photos_dir=str(tmp_path / "nopics"),
                 todos_store=str(tmp_path / "todos.json"))
    st = HubState(cfg)
    st.set_claude_status("working", project="InkPulse")
    st.add_todo("买菜")
    d = st.build_render_state(now=time.mktime((2026, 6, 9, 14, 32, 0, 0, 0, -1)))
    assert d["claude"].state == "working"
    assert d["claude"].project == "InkPulse"
    assert [t.text for t in d["todos"]] == ["买菜"]
    assert "14:32" in d["clock"]
    assert d["usage"].total_tokens() == 0  # 无日志 -> 0
