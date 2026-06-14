# inkpulse_hub/collectors/env_history.py
import json
import os

RETENTION_S = 86400                 # 24h
TEMP_MIN, TEMP_MAX = -40.0, 85.0    # 合理温度范围, 挡 None/哨兵/越界


class EnvHistoryStore:
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

    def _write(self, samples: list) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False)

    def append(self, ts: float, temp) -> None:
        if temp is None:
            return
        try:
            t = float(temp)
        except (TypeError, ValueError):
            return
        if not (TEMP_MIN <= t <= TEMP_MAX):
            return
        samples = self._read()
        samples.append([float(ts), t])
        cutoff = float(ts) - RETENTION_S
        samples = [s for s in samples if s[0] >= cutoff]
        self._write(samples)

    def window(self, now: float) -> list:
        cutoff = now - RETENTION_S
        return sorted((s for s in self._read() if s[0] >= cutoff),
                      key=lambda s: s[0])
