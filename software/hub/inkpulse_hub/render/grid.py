# inkpulse_hub/render/grid.py
# 网格坐标(col/row/colspan/rowspan) -> 像素 Zone。
# 用累计 round 保证相邻格无缝相接, 即使尺寸/cols 不整除。
from .widgets import Zone


def cell_to_zone(grid: dict, p: dict, w: int = 800, h: int = 480) -> Zone:
    cols = grid["cols"]
    rows = grid["rows"]
    cw = w / cols
    ch = h / rows
    x = round(p["col"] * cw)
    y = round(p["row"] * ch)
    x2 = round((p["col"] + p["colspan"]) * cw)
    y2 = round((p["row"] + p["rowspan"]) * ch)
    return Zone(x, y, x2 - x, y2 - y)
