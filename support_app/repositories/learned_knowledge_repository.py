from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from support_app.repositories.json_file_repository import JsonFileRepository


class LearnedKnowledgeRepository:
    def __init__(self, path: Path):
        self.store = JsonFileRepository(path)

    def list(self, q: str = "") -> list[dict]:
        items = self.store.load_list()
        if q:
            keyword = q.strip().lower()
            items = [item for item in items if keyword in str(item).lower()]
        return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)

    def add(self, payload: dict) -> dict:
        items = self.store.load_list()
        now = self._now()
        item = {
            "id": payload.get("id") or f"learned_{uuid.uuid4().hex[:12]}",
            "question_hint": str(payload.get("question_hint", "") or "").strip(),
            "corrected_fact": str(payload.get("corrected_fact", "") or "").strip(),
            "category": str(payload.get("category", "") or "学习知识").strip(),
            "source_message": str(payload.get("source_message", "") or "").strip(),
            "channel": str(payload.get("channel", "") or "").strip(),
            "user_id": str(payload.get("user_id", "") or "").strip(),
            "conversation_id": str(payload.get("conversation_id", "") or "").strip(),
            "created_at": now,
            "updated_at": now,
        }
        items = [old for old in items if old.get("id") != item["id"]]
        items.append(item)
        self.store.save_list(items)
        return item

    def delete(self, learned_id: str) -> dict:
        target = str(learned_id or "").strip()
        items = self.store.load_list()
        kept = [item for item in items if item.get("id") != target]
        if len(kept) == len(items):
            raise KeyError(f"未找到学习知识: {target}")
        self.store.save_list(kept)
        return {"id": target}

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
