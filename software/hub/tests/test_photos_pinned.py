import os
from inkpulse_hub.collectors.photos import pick_photo


def _make(d, *names):
    os.makedirs(d, exist_ok=True)
    for n in names:
        open(os.path.join(d, n), "wb").write(b"x")


def test_pinned_photo_always_returned(tmp_path):
    d = str(tmp_path)
    _make(d, "a.png", "b.png", "c.png")
    # 不同时间都应返回钉住的 b.png(否则会随时间轮换)
    for t in (0, 100000, 9999999):
        assert pick_photo(d, now=t, pinned="b.png").path.endswith("b.png")


def test_pinned_missing_falls_back_to_rotation(tmp_path):
    d = str(tmp_path)
    _make(d, "a.png", "b.png")
    p = pick_photo(d, now=0, pinned="gone.png")   # 钉住的文件不存在
    assert p is not None and os.path.basename(p.path) in {"a.png", "b.png"}


def test_empty_pinned_rotates(tmp_path):
    d = str(tmp_path)
    _make(d, "a.png", "b.png")
    # rotate_s=1 时, now=0 -> idx0=a, now=1 -> idx1=b
    assert pick_photo(d, now=0, rotate_s=1, pinned="").path.endswith("a.png")
    assert pick_photo(d, now=1, rotate_s=1, pinned="").path.endswith("b.png")


def test_pinned_basename_only(tmp_path):
    # 传入带路径的值也按 basename 处理(防注入)
    d = str(tmp_path)
    _make(d, "a.png")
    assert pick_photo(d, now=0, pinned="../a.png").path.endswith("a.png")
