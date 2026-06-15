# inkpulse_hub/collectors/agent_tasks.py
import json
import os

STALE_S = 7200   # 2 小时未更新视为会话可能已结束

_STATUSES = ("pending", "in_progress", "completed")


def _norm_tasks(tasks):
    out = []
    for t in tasks or []:
        if not isinstance(t, dict):
            continue
        content = str(t.get("content", "")).strip()
        if not content:
            continue
        status = t.get("status")
        out.append({"content": content,
                    "status": status if status in _STATUSES else "pending"})
    return out


class AgentTaskStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _read(self):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    def _write(self, snap):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)

    def ingest(self, now, project, tasks=None, highlights=None):
        old = self._read()
        if old and old.get("project") == project:
            snap = old
        else:
            snap = {"project": project, "tasks": [], "highlights": []}
        if tasks is not None:
            snap["tasks"] = _norm_tasks(tasks)
        if highlights is not None:
            snap["highlights"] = [str(h) for h in highlights]
        snap["project"] = project
        snap["updated_at"] = now
        self._write(snap)

    def current(self, now):
        snap = self._read()
        if not snap or "updated_at" not in snap:
            return None
        return {"project": snap.get("project", ""),
                "tasks": snap.get("tasks", []),
                "highlights": snap.get("highlights", []),
                "age_s": now - snap["updated_at"]}
