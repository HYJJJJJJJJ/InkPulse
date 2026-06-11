# inkpulse_hub/collectors/photos.py
import glob
import os
import time
from typing import Optional
from ..models import Photo

_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif")


def pick_photo(
    photos_dir: str,
    now: Optional[float] = None,
    rotate_s: int = 1800,
) -> Optional[Photo]:
    """从照片目录选一张; 按 rotate_s(默认 30min)随时间轮换, 无需持久 tick。"""
    if not os.path.isdir(photos_dir):
        return None
    files: list[str] = []
    for pat in _EXTS:
        files += glob.glob(os.path.join(photos_dir, pat))
    if not files:
        return None
    files.sort()
    if now is None:
        now = time.time()
    idx = int(now // max(1, rotate_s)) % len(files)
    return Photo(path=files[idx])
