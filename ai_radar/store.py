"""去重存储：把见过的条目记到 seen.json，避免重复推送。"""
import json
import os
import time


class SeenStore:
    def __init__(self, path: str = "seen.json"):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_new(self, key: str) -> bool:
        return key not in self.data

    def mark(self, key: str, meta: dict | None = None) -> None:
        self.data[key] = {"seen_at": int(time.time()), "meta": meta or {}}
