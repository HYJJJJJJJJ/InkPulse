# inkpulse_hub/render/profiles.py
# 屏幕 profile: 把"尺寸/颜色/旋转/网格/帧字节"集中, 由设备上报的 panel id 选取。
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenProfile:
    id: str
    w: int           # 渲染画布宽(竖屏=逻辑宽)
    h: int           # 渲染画布高
    color: str       # "bwr"(双plane) | "bw"(单plane)
    rotate: int      # 渲染画布 -> 面板 的顺时针旋转角(0/90/180/270)
    cols: int        # 默认网格列
    rows: int        # 默认网格行
    frame_bytes: int # 期望帧字节(校验/文档用)


PROFILES: dict[str, ScreenProfile] = {
    "bwr_750": ScreenProfile("bwr_750", 800, 480, "bwr", 0, 8, 6, 96000),
    "bw_426":  ScreenProfile("bw_426",  480, 800, "bw",  90, 4, 8, 48000),
}

DEFAULT_PROFILE = PROFILES["bwr_750"]


def get_profile(panel_id: str | None) -> ScreenProfile:
    """按设备上报的 panel id 选 profile; 缺省/未知回退默认(bwr_750), 保证零回归。"""
    return PROFILES.get(panel_id or "", DEFAULT_PROFILE)
