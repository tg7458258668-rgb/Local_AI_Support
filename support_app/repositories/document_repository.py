from __future__ import annotations

from pathlib import Path

from support_app.repositories.json_file_repository import JsonFileRepository


class DocumentRepository:
    def __init__(self, chunks_path: Path):
        self.store = JsonFileRepository(chunks_path)

    def list(self, q: str = "") -> list[dict]:
        docs = self.store.load_list()
        if not q:
            return docs
        keyword = q.strip().lower()
        return [item for item in docs if keyword in str(item).lower()]

    def names(self) -> list[str]:
        return sorted({item.get("doc_name", "") for item in self.list() if item.get("doc_name")})

    def save(self, items: list[dict]) -> None:
        self.store.save_list(items)
