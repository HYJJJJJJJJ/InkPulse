from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_agent_tasks, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has_black(img):
    return any(img.getpixel((x, y)) == (0, 0, 0)
               for x in range(img.width) for y in range(img.height))


def _data(age_s=120, highlights=None):
    return {"project": "InkPulse", "age_s": age_s,
            "tasks": [{"content": "写端点", "status": "in_progress"},
                      {"content": "做 widget", "status": "pending"},
                      {"content": "探索 hook", "status": "completed"}],
            "highlights": highlights or []}


def test_draws_with_data():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), _data())
    assert _has_black(img)


def test_none_shows_hint_no_crash():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), None)
    assert _has_black(img)   # "无活动会话" 提示


def test_highlights_rendered_no_crash():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), _data(highlights=["记得加测试"]))
    assert _has_black(img)


def test_stale_no_crash():
    img, d = _img()
    draw_agent_tasks(d, Zone(0, 0, 400, 240), _data(age_s=99999))   # >2h
    assert _has_black(img)


def test_long_content_truncated_no_crash():
    img, d = _img(280, 120)
    data = {"project": "X" * 40, "age_s": 60, "highlights": [],
            "tasks": [{"content": "超长任务" * 12, "status": "pending"}]}
    draw_agent_tasks(d, Zone(0, 0, 280, 120), data)
    assert _has_black(img)
