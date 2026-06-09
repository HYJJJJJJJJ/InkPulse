# inkpulse_hub/collectors/photos.py
import glob
import os
from typing import Optional
from ..models import Photo

_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif")


def pick_photo(photos_dir: str) -> Optional[Photo]:
    if not os.path.isdir(photos_dir):
        return None
    files: list[str] = []
    for pat in _EXTS:
        files += glob.glob(os.path.join(photos_dir, pat))
    if not files:
        return None
    files.sort()
    return Photo(path=files[0])  # v1 取首张;轮换策略后续接 refresh tick
