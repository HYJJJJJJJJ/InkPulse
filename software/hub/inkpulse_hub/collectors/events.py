# inkpulse_hub/collectors/events.py
import json
import os
import uuid
import datetime as _dt

AGENDA_LIMIT = 8   # state 注入上限(widget 再按高度截断)


class EventStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError
            return data
        except (json.JSONDecodeError, ValueError, OSError):
            return []

    def _write(self, items: list) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _key(e):
        return (e.get("date", ""), e.get("time") or "00:00")

    def list(self) -> list:
        return sorted(self._read(), key=self._key)

    def add(self, title: str, date: str, time: str = "") -> dict:
        items = self._read()
        e = {"id": uuid.uuid4().hex[:8], "title": title, "date": date, "time": time or ""}
        items.append(e)
        self._write(items)
        return e

    def delete(self, eid: str) -> None:
        self._write([e for e in self._read() if e.get("id") != eid])

    def upcoming(self, now: float, limit: int) -> list:
        today = _dt.date.fromtimestamp(now).isoformat()
        future = [e for e in self.list() if e.get("date", "") >= today]
        return future[:limit]
