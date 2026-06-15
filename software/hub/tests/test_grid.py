from inkpulse_hub.render.grid import cell_to_zone

GRID = {"cols": 8, "rows": 6}   # 800x480 -> 格子 100x80


def test_single_cell():
    z = cell_to_zone(GRID, {"col": 0, "row": 0, "colspan": 1, "rowspan": 1})
    assert (z.x, z.y, z.w, z.h) == (0, 0, 100, 80)


def test_span_and_offset():
    z = cell_to_zone(GRID, {"col": 4, "row": 1, "colspan": 4, "rowspan": 3})
    assert (z.x, z.y, z.w, z.h) == (400, 80, 400, 240)


def test_full_bleed_covers_screen():
    z = cell_to_zone(GRID, {"col": 0, "row": 0, "colspan": 8, "rowspan": 6})
    assert (z.x, z.y, z.w, z.h) == (0, 0, 800, 480)


def test_adjacent_cells_tile_without_gap():
    # 非整除网格也要无缝相接: 右格的 x 必须等于左格的 x+w
    g = {"cols": 3, "rows": 1}   # 800/3 非整除
    left = cell_to_zone(g, {"col": 0, "row": 0, "colspan": 1, "rowspan": 1})
    mid = cell_to_zone(g, {"col": 1, "row": 0, "colspan": 1, "rowspan": 1})
    assert mid.x == left.x + left.w


def test_portrait_dims_4x8():
    g = {"cols": 4, "rows": 8}
    z = cell_to_zone(g, {"col": 0, "row": 0, "colspan": 4, "rowspan": 1}, 480, 800)
    assert (z.x, z.y, z.w, z.h) == (0, 0, 480, 100)
    z2 = cell_to_zone(g, {"col": 0, "row": 0, "colspan": 4, "rowspan": 8}, 480, 800)
    assert (z2.x, z2.y, z2.w, z2.h) == (0, 0, 480, 800)
