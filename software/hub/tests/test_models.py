from inkpulse_hub.models import ClaudeStatus, Usage, TodoItem, Photo


def test_claude_status_defaults():
    s = ClaudeStatus()
    assert s.state == "idle"
    assert s.project is None
    assert s.needs_attention() is False


def test_claude_status_attention_states():
    assert ClaudeStatus(state="waiting_for_input").needs_attention() is True
    assert ClaudeStatus(state="error").needs_attention() is True
    assert ClaudeStatus(state="working").needs_attention() is False


def test_usage_and_todo_and_photo():
    u = Usage(input_tokens=10, output_tokens=5, cost_usd=0.0, session_count=1, window_used_ratio=0.5)
    assert u.total_tokens() == 15
    t = TodoItem(id="a1", text="买菜", done=False)
    assert t.text == "买菜" and t.done is False
    p = Photo(path="/x/a.jpg")
    assert p.path.endswith("a.jpg")
