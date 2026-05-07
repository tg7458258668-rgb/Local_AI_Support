from __future__ import annotations

from datetime import datetime
from pathlib import Path

from support_app.repositories.json_file_repository import JsonFileRepository


class FAQRepository:
    def __init__(self, path: Path):
        self.store = JsonFileRepository(path)

    def list(self, q: str = "") -> list[dict]:
        items = self.store.load_list()
        if not q:
            return self._sort(items)

        keyword = q.strip().lower()
        return self._sort([
            item for item in items
            if keyword in str(item).lower()
        ])

    def create(self, payload: dict) -> dict:
        items = self.store.load_list()
        item = self._normalize(payload)
        item["id"] = self._next_id(items)
        item["updated_at"] = self._now()
        items.append(item)
        self.store.save_list(self._sort(items))
        return item

    def update(self, faq_id: str, payload: dict) -> dict:
        items = self.store.load_list()
        for index, item in enumerate(items):
            if str(item.get("id")) == faq_id:
                updated = self._normalize(payload)
                updated["id"] = faq_id
                updated["updated_at"] = self._now()
                items[index] = updated
                self.store.save_list(self._sort(items))
                return updated
        raise KeyError(f"FAQ 不存在: {faq_id}")

    def delete(self, faq_id: str) -> None:
        items = self.store.load_list()
        filtered = [item for item in items if str(item.get("id")) != faq_id]
        if len(filtered) == len(items):
            raise KeyError(f"FAQ 不存在: {faq_id}")
        self.store.save_list(filtered)

    @staticmethod
    def _normalize(payload: dict) -> dict:
        questions = [str(q).strip() for q in payload.get("questions", []) if str(q).strip()]
        tags = [str(t).strip() for t in payload.get("tags", []) if str(t).strip()]
        if not questions:
            raise ValueError("questions 不能为空")
        answer = str(payload.get("answer", "")).strip()
        if not answer:
            raise ValueError("answer 不能为空")
        return {
            "questions": questions,
            "answer": answer,
            "category": str(payload.get("category", "")).strip(),
            "source": str(payload.get("source", "")).strip(),
            "tags": tags,
            "status": "inactive" if str(payload.get("status", "")).lower() == "inactive" else "active",
            "priority": max(1, int(payload.get("priority", 1) or 1)),
        }

    @staticmethod
    def _sort(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda item: (int(item.get("priority", 999) or 999), str(item.get("id", ""))))

    @staticmethod
    def _next_id(items: list[dict]) -> str:
        max_num = 0
        for item in items:
            raw_id = str(item.get("id", ""))
            if raw_id.startswith("faq_"):
                try:
                    max_num = max(max_num, int(raw_id.split("_")[1]))
                except Exception:
                    pass
        return f"faq_{max_num + 1:03d}"

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
