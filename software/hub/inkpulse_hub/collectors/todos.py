# inkpulse_hub/collectors/todos.py
import json
import os
import uuid
from ..models import TodoItem


class TodoStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self) -> list[TodoItem]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [TodoItem(**d) for d in raw]

    def _write(self, items: list[TodoItem]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([t.__dict__ for t in items], f, ensure_ascii=False, indent=2)

    def list(self) -> list[TodoItem]:
        return self._read()

    def add(self, text: str) -> TodoItem:
        items = self._read()
        item = TodoItem(id=uuid.uuid4().hex[:8], text=text, done=False)
        items.append(item)
        self._write(items)
        return item

    def toggle(self, item_id: str) -> None:
        items = self._read()
        for t in items:
            if t.id == item_id:
                t.done = not t.done
        self._write(items)

    def delete(self, item_id: str) -> None:
        self._write([t for t in self._read() if t.id != item_id])
