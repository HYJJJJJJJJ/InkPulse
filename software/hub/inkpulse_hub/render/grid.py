# inkpulse_hub/render/grid.py
# 网格坐标(col/row/colspan/rowspan) -> 像素 Zone。
# 用累计 round 保证相邻格无缝相接, 即使 800/cols 不整除。
from .planes import WIDTH, HEIGHT
from .widgets import Zone


def cell_to_zone(grid: dict, p: dict) -> Zone:
    cols = grid["cols"]
    rows = grid["rows"]
    cw = WIDTH / cols
    ch = HEIGHT / rows
    x = round(p["col"] * cw)
    y = round(p["row"] * ch)
    x2 = round((p["col"] + p["colspan"]) * cw)
    y2 = round((p["row"] + p["rowspan"]) * ch)
    return Zone(x, y, x2 - x, y2 - y)
