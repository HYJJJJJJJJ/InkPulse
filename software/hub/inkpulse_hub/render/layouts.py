# inkpulse_hub/render/layouts.py
# 布局存储: 内置 6 预设(builtin, 不可删) + 用户自建(写 layouts.json)。
# 读取时把文件与内置合并; 写入只存用户布局, 不灌入内置。
import json
import os
from copy import deepcopy

GRID = {"cols": 8, "rows": 6}


def _p(widget, col, row, colspan, rowspan, **params):
    return {"widget": widget, "col": col, "row": row,
            "colspan": colspan, "rowspan": rowspan, "params": params}


BUILTIN_LAYOUTS = {
    "dash": {"builtin": True, "placements": [
        _p("header", 0, 0, 8, 1),
        _p("claude_status", 0, 1, 4, 3),
        _p("usage", 4, 1, 4, 3),
        _p("todos", 0, 4, 8, 2),
    ]},
    "photo": {"builtin": True, "placements": [
        _p("photo", 0, 0, 8, 6),
    ]},
    "clock": {"builtin": True, "placements": [
        _p("big_clock", 0, 0, 8, 4),
        _p("calendar", 1, 4, 6, 2),
    ]},
    "usage": {"builtin": True, "placements": [
        _p("usage", 0, 0, 5, 4),
        _p("usage_ring", 5, 0, 3, 4),
        _p("claude_status", 0, 4, 4, 2),
        _p("todos", 4, 4, 4, 2),
    ]},
    "split": {"builtin": True, "placements": [
        _p("header", 0, 0, 4, 1),
        _p("claude_status", 0, 1, 4, 3),
        _p("usage", 0, 4, 4, 2),
        _p("calendar", 4, 0, 4, 3),
        _p("todos", 4, 3, 4, 3),
    ]},
    "todo": {"builtin": True, "placements": [
        _p("todos", 0, 0, 5, 6),
        _p("calendar", 5, 0, 3, 3),
        _p("claude_status", 5, 3, 3, 3),
    ]},
}


def _default_store():
    return {"version": 1, "grid": dict(GRID), "layouts": deepcopy(BUILTIN_LAYOUTS)}


def _load_raw(path: str) -> dict:
    """读文件原始内容(只含用户布局); 不存在/损坏 -> 空骨架。"""
    if not path or not os.path.exists(path):
        return {"version": 1, "grid": dict(GRID), "layouts": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "grid": dict(GRID), "layouts": {}}
    data.setdefault("grid", dict(GRID))
    data.setdefault("layouts", {})
    return data


def load_store(path: str) -> dict:
    """对外读取: 内置 + 用户文件合并(同名时用户覆盖内置)。"""
    raw = _load_raw(path)
    merged = deepcopy(BUILTIN_LAYOUTS)
    merged.update(raw["layouts"])
    return {"version": 1, "grid": raw["grid"], "layouts": merged}


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


def get_layout(path: str, name: str) -> dict:
    """取某布局(含 clamp); 未知名回退 dash。返回 {grid, placements}。"""
    store = load_store(path)
    layouts = store["layouts"]
    lay = layouts.get(name) or layouts["dash"]
    return {"grid": store["grid"], "placements": _clamp(lay["placements"], store["grid"])}


def save_layout(path: str, name: str, placements: list) -> None:
    if name in BUILTIN_LAYOUTS:
        raise ValueError("内置布局只读, 请另存为新名")
    raw = _load_raw(path)
    raw["layouts"][name] = {"placements": placements}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)


def delete_layout(path: str, name: str) -> None:
    if name in BUILTIN_LAYOUTS:
        raise ValueError("内置布局不可删")
    raw = _load_raw(path)
    raw["layouts"].pop(name, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
