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
