# inkpulse_hub/render/layouts.py
# 布局存储: 内置布局按屏 profile 分组(每 profile 自带网格), 用户自建写文件。
# 读取时把内置与用户合并; 写入只存用户布局, 按 profile 命名空间隔离。
import json
import os
from copy import deepcopy

GRIDS = {
    "bwr_750": {"cols": 8, "rows": 6},
    "bw_426":  {"cols": 4, "rows": 8},
}
DEFAULT_PID = "bwr_750"


def _p(widget, col, row, colspan, rowspan, **params):
    return {"widget": widget, "col": col, "row": row,
            "colspan": colspan, "rowspan": rowspan, "params": params}


# 7.5 寸 8x6(原内置, 保持不变)
_BWR_750 = {
    "dash": {"builtin": True, "placements": [
        _p("header", 0, 0, 8, 1), _p("claude_status", 0, 1, 4, 3),
        _p("usage", 4, 1, 4, 3), _p("todos", 0, 4, 8, 2)]},
    "photo": {"builtin": True, "placements": [_p("photo", 0, 0, 8, 6)]},
    "clock": {"builtin": True, "placements": [
        _p("big_clock", 0, 0, 8, 4), _p("calendar", 1, 4, 6, 2)]},
    "usage": {"builtin": True, "placements": [
        _p("usage", 0, 0, 5, 4), _p("usage_ring", 5, 0, 3, 4),
        _p("claude_status", 0, 4, 4, 2), _p("todos", 4, 4, 4, 2)]},
    "split": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1), _p("claude_status", 0, 1, 4, 2),
        _p("usage", 0, 3, 4, 3), _p("calendar", 4, 0, 4, 3),
        _p("todos", 4, 3, 4, 3)]},
    "todo": {"builtin": True, "placements": [
        _p("todos", 0, 0, 5, 6), _p("calendar", 5, 0, 3, 3),
        _p("claude_status", 5, 3, 3, 3)]},
}

# 4.2 寸 4x8 竖版(同名, 每个布局行合计=8, 列<=4)
_BW_426 = {
    "dash": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1), _p("claude_status", 0, 1, 4, 2),
        _p("usage", 0, 3, 4, 2), _p("todos", 0, 5, 4, 3)]},
    "photo": {"builtin": True, "placements": [_p("photo", 0, 0, 4, 8)]},
    "clock": {"builtin": True, "placements": [
        _p("big_clock", 0, 0, 4, 3), _p("calendar", 0, 3, 4, 3),
        _p("todos", 0, 6, 4, 2)]},
    "usage": {"builtin": True, "placements": [
        _p("usage", 0, 0, 4, 3), _p("usage_ring", 0, 3, 4, 3),
        _p("todos", 0, 6, 4, 2)]},
    "split": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1), _p("claude_status", 0, 1, 4, 2),
        _p("calendar", 0, 3, 4, 3), _p("todos", 0, 6, 4, 2)]},
    "todo": {"builtin": True, "placements": [
        _p("todos", 0, 0, 4, 4), _p("calendar", 0, 4, 4, 4)]},
}

BUILTIN_LAYOUTS = {"bwr_750": _BWR_750, "bw_426": _BW_426}


def _builtin(pid: str) -> dict:
    return BUILTIN_LAYOUTS.get(pid, _BWR_750)


def _grid(pid: str) -> dict:
    return dict(GRIDS.get(pid, GRIDS[DEFAULT_PID]))


def _load_raw(path: str) -> dict:
    """读用户文件 -> {profiles: {pid: {layouts:{...}}}}。兼容旧扁平格式(归入 bwr_750)。"""
    empty = {"version": 2, "profiles": {}}
    if not path or not os.path.exists(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return empty
    if "profiles" in data:
        return {"version": 2, "profiles": data.get("profiles") or {}}
    # 旧扁平格式 {version, grid, layouts} -> 归 bwr_750
    return {"version": 2, "profiles": {DEFAULT_PID: {"layouts": data.get("layouts", {})}}}


def load_store(path: str, profile: str = DEFAULT_PID) -> dict:
    """对外读取: 该 profile 的内置 + 用户文件合并(同名用户覆盖)。"""
    raw = _load_raw(path)
    user = (raw["profiles"].get(profile) or {}).get("layouts", {})
    merged = deepcopy(_builtin(profile))
    merged.update(user)
    return {"version": 2, "grid": _grid(profile), "layouts": merged}


def _clamp(placements: list, grid: dict) -> list:
    cols, rows = grid["cols"], grid["rows"]
    out = []
    for p in placements:
        col = max(0, min(int(p["col"]), cols - 1))
        row = max(0, min(int(p["row"]), rows - 1))
        colspan = max(1, min(int(p["colspan"]), cols - col))
        rowspan = max(1, min(int(p["rowspan"]), rows - row))
        out.append({"widget": p["widget"], "col": col, "row": row,
                    "colspan": colspan, "rowspan": rowspan,
                    "params": p.get("params", {})})
    return out


def get_layout(path: str, name: str, profile: str = DEFAULT_PID) -> dict:
    """取某布局(含 clamp); 未知名回退 dash。返回 {grid, placements}。"""
    store = load_store(path, profile)
    lay = store["layouts"].get(name) or store["layouts"]["dash"]
    return {"grid": store["grid"], "placements": _clamp(lay["placements"], store["grid"])}


def save_layout(path: str, name: str, placements: list, profile: str = DEFAULT_PID) -> None:
    if name in _builtin(profile):
        raise ValueError("内置布局只读, 请另存为新名")
    raw = _load_raw(path)
    raw["profiles"].setdefault(profile, {}).setdefault("layouts", {})[name] = {"placements": placements}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)


def delete_layout(path: str, name: str, profile: str = DEFAULT_PID) -> None:
    if name in _builtin(profile):
        raise ValueError("内置布局不可删")
    raw = _load_raw(path)
    (raw["profiles"].get(profile) or {}).get("layouts", {}).pop(name, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
