from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository


class QuoteArchiveRepository:
    def __init__(self, path: Path):
        self.store = JsonFileRepository(path)

    def list(self, q: str = "") -> list[dict[str, Any]]:
        rows = []
        for item in self.store.load_object().values():
            rows.extend(item.get("quotes", []))
        if q:
            keyword = q.strip().lower()
            rows = [item for item in rows if keyword in str(item).lower()]
        return sorted(rows, key=lambda item: item.get("updated_at", ""), reverse=True)

    def recent_for_customer(self, channel: str, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        data = self.store.load_object()
        item = data.get(self._key(channel, user_id), {})
        quotes = item.get("quotes", [])
        return sorted(quotes, key=lambda row: row.get("updated_at", ""), reverse=True)[:limit]

    def add(self, channel: str, user_id: str, quote: dict[str, Any]) -> dict[str, Any]:
        data = self.store.load_object()
        key = self._key(channel, user_id)
        item = data.get(key) or {"channel": channel, "user_id": user_id, "quotes": []}
        now = self._now()
        quote_id = quote.get("quote_id") or f"quote_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        row = {
            "quote_id": quote_id,
            "channel": channel,
            "user_id": user_id,
            "status": quote.get("status", "draft"),
            "follow_up_note": quote.get("follow_up_note", ""),
            "created_at": quote.get("created_at") or now,
            "updated_at": now,
            **quote,
        }
        item["quotes"] = [row, *item.get("quotes", [])][:100]
        data[key] = item
        self.store.save_object(data)
        return row

    def update(self, channel: str, user_id: str, quote_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        data = self.store.load_object()
        key = self._key(channel, user_id)
        item = data.get(key)
        if not item:
            raise KeyError("报价档案不存在")
        for row in item.get("quotes", []):
            if row.get("quote_id") == quote_id:
                row.update({
                    "status": updates.get("status", row.get("status", "draft")),
                    "follow_up_note": updates.get("follow_up_note", row.get("follow_up_note", "")),
                    "updated_at": self._now(),
                })
                self.store.save_object(data)
                return row
        raise KeyError("报价记录不存在")

    @staticmethod
    def _key(channel: str, user_id: str) -> str:
        return f"{channel}:{user_id}"

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
