# inkpulse_hub/collectors/photos.py
import glob
import os
import time
from typing import Optional
from ..models import Photo

_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp")


def pick_photo(
    photos_dir: str,
    now: Optional[float] = None,
    rotate_s: int = 1800,
    pinned: str = "",
) -> Optional[Photo]:
    """从照片目录选一张。
    pinned 非空且对应文件存在 -> 永远返回该张(手动钉住);
    否则按 rotate_s(默认 30min)随时间轮换, 无需持久 tick。"""
    if not os.path.isdir(photos_dir):
        return None
    if pinned:
        p = os.path.join(photos_dir, os.path.basename(pinned))
        if os.path.isfile(p):
            return Photo(path=p)
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
