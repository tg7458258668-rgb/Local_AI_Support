from __future__ import annotations

from typing import Any

from support_app.repositories.quote_archive_repository import QuoteArchiveRepository


class QuoteArchiveService:
    def __init__(self, repo: QuoteArchiveRepository):
        self.repo = repo

    def list(self, q: str = "") -> dict[str, Any]:
        items = self.repo.list(q)
        return {"total": len(items), "items": items[:200]}

    def recent_for_customer(self, channel: str, user_id: str | None) -> list[dict[str, Any]]:
        if not user_id:
            return []
        return self.repo.recent_for_customer(channel, user_id)

    def add_for_customer(self, channel: str, user_id: str | None, quote: dict[str, Any]) -> dict[str, Any] | None:
        if not user_id:
            return None
        return self.repo.add(channel, user_id, quote)

    def update(self, channel: str, user_id: str, quote_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.update(channel, user_id, quote_id, payload)
