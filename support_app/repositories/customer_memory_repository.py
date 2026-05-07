from __future__ import annotations

from datetime import datetime
from pathlib import Path

from support_app.repositories.json_file_repository import JsonFileRepository


MEMORY_FIELDS = [
    "customer_name",
    "contact",
    "products",
    "preferences",
    "common_questions",
    "risk_flags",
    "scenario",
    "budget",
    "project_time",
    "decision_status",
    "concerns",
    "quoted_schemes",
    "notes",
]


class CustomerMemoryRepository:
    def __init__(self, path: Path):
        self.store = JsonFileRepository(path)

    def list(self, q: str = "") -> list[dict]:
        memories = list(self.store.load_object().values())
        if q:
            keyword = q.strip().lower()
            memories = [item for item in memories if keyword in str(item).lower()]
        return sorted(memories, key=lambda item: item.get("updated_at", ""), reverse=True)

    def get(self, channel: str, user_id: str) -> dict | None:
        return self.store.load_object().get(self._key(channel, user_id))

    def upsert(self, channel: str, user_id: str, updates: dict) -> dict:
        data = self.store.load_object()
        key = self._key(channel, user_id)
        current = data.get(key) or self._empty(channel, user_id)
        for field in MEMORY_FIELDS:
            if field not in updates:
                continue
            if isinstance(current.get(field), list):
                current[field] = self._merge_list(current.get(field, []), updates.get(field, []))
            else:
                value = str(updates.get(field, "") or "").strip()
                if value:
                    current[field] = value
        current["updated_at"] = self._now()
        data[key] = current
        self.store.save_object(data)
        return current

    def replace(self, channel: str, user_id: str, payload: dict) -> dict:
        data = self.store.load_object()
        key = self._key(channel, user_id)
        item = self._empty(channel, user_id)
        for field in MEMORY_FIELDS:
            if isinstance(item[field], list):
                raw = payload.get(field, [])
                item[field] = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
            else:
                item[field] = str(payload.get(field, "") or "").strip()
        item["updated_at"] = self._now()
        data[key] = item
        self.store.save_object(data)
        return item

    def delete(self, channel: str, user_id: str) -> None:
        data = self.store.load_object()
        data.pop(self._key(channel, user_id), None)
        self.store.save_object(data)

    @staticmethod
    def _key(channel: str, user_id: str) -> str:
        return f"{channel}:{user_id}"

    @staticmethod
    def _empty(channel: str, user_id: str) -> dict:
        return {
            "channel": channel,
            "user_id": user_id,
            "customer_name": "",
            "contact": "",
            "products": [],
            "preferences": [],
            "common_questions": [],
            "risk_flags": [],
            "scenario": "",
            "budget": "",
            "project_time": "",
            "decision_status": "",
            "concerns": [],
            "quoted_schemes": [],
            "notes": "",
            "updated_at": "",
        }

    @staticmethod
    def _merge_list(current: list, updates: list) -> list:
        values = []
        seen = set()
        for item in [*current, *updates]:
            text = str(item or "").strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                values.append(text)
        return values[:30]

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
