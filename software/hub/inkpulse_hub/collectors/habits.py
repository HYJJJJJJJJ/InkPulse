# inkpulse_hub/collectors/habits.py
import json
import os
import time
import uuid
import datetime as _dt


def week_dates(now: float) -> tuple[list[str], int]:
    """本周(周一→周日)7 个 ISO 日期串 + 今天列索引(周一=0…周日=6)。"""
    lt = time.localtime(now)
    today = _dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)
    monday = today - _dt.timedelta(days=today.weekday())
    dates = [(monday + _dt.timedelta(days=i)).isoformat() for i in range(7)]
    return dates, today.weekday()


class HabitStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self) -> dict:
        if not os.path.exists(self.path):
            return {"habits": [], "log": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError
            data.setdefault("habits", [])
            data.setdefault("log", {})
            return data
        except (json.JSONDecodeError, ValueError, OSError):
            return {"habits": [], "log": {}}

    def _write(self, data: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list(self) -> list[dict]:
        return self._read()["habits"]

    def add(self, name: str) -> dict:
        data = self._read()
        h = {"id": uuid.uuid4().hex[:8], "name": (name or "").strip()}
        data["habits"].append(h)
        self._write(data)
        return h

    def delete(self, hid: str) -> None:
        data = self._read()
        data["habits"] = [h for h in data["habits"] if h["id"] != hid]
        for day in data["log"].values():
            if hid in day:
                day.remove(hid)
        self._write(data)
