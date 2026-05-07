from dataclasses import dataclass

import requests

from support_app.services.ollama_client import OllamaClient
from support_app.settings import Settings


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict


class VectorRepository:
    def __init__(self, settings: Settings, ollama: OllamaClient):
        self.settings = settings
        self.ollama = ollama

    def search_faq(self, query: str):
        return self._search(self.settings.faq_collection, query, self.settings.top_k_faq)

    def search_docs(self, query: str):
        return self._search(self.settings.doc_collection, query, self.settings.top_k_doc)

    def search_faq_by_vector(self, vector: list[float]):
        return self._search_by_vector(self.settings.faq_collection, vector, self.settings.top_k_faq)

    def search_docs_by_vector(self, vector: list[float]):
        return self._search_by_vector(self.settings.doc_collection, vector, self.settings.top_k_doc)

    def _search(self, collection_name: str, query: str, limit: int):
        vector = self.ollama.embedding(query)
        return self._search_by_vector(collection_name, vector, limit)

    def _search_by_vector(self, collection_name: str, vector: list[float], limit: int):
        resp = requests.post(
            f"{self.settings.qdrant_url}/collections/{collection_name}/points/query",
            json={"query": vector, "limit": limit, "with_payload": True},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        points = data.get("result", {}).get("points", [])
        return [
            VectorHit(
                id=str(item.get("id", "")),
                score=float(item.get("score", 0) or 0),
                payload=item.get("payload") or {},
            )
            for item in points
        ]
