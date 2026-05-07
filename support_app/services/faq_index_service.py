import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from support_app.repositories.faq_repository import FAQRepository
from support_app.schemas import ReindexResult
from support_app.services.ollama_client import OllamaClient
from support_app.settings import Settings


class FAQIndexService:
    def __init__(self, settings: Settings, faq_repo: FAQRepository, ollama: OllamaClient):
        self.settings = settings
        self.faq_repo = faq_repo
        self.ollama = ollama
        self.client = QdrantClient(url=settings.qdrant_url)

    def rebuild(self) -> ReindexResult:
        rows = self._active_rows()
        if not rows:
            raise ValueError("没有可用的 active FAQ 数据可入库")

        sample_text = f"{rows[0]['questions'][0]}\n{rows[0]['answer']}"
        first_vector = self.ollama.embedding(sample_text)
        self._recreate_collection(len(first_vector))

        points = []
        for row in rows:
            for question in row["questions"]:
                text = f"问题：{question}\n答案：{row['answer']}"
                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=self.ollama.embedding(text),
                    payload={
                        "faq_id": row["id"],
                        "question": question,
                        "answer": row["answer"],
                        "category": row.get("category", ""),
                        "source": row.get("source", ""),
                        "tags": row.get("tags", []),
                        "updated_at": row.get("updated_at", ""),
                        "priority": row.get("priority", 999),
                        "text": text,
                    },
                ))

        self.client.upsert(collection_name=self.settings.faq_collection, points=points)
        return ReindexResult(
            collection=self.settings.faq_collection,
            faq_count=len(rows),
            point_count=len(points),
        )

    def _active_rows(self) -> list[dict]:
        rows = []
        for item in self.faq_repo.list():
            if str(item.get("status", "active")).lower() != "active":
                continue
            questions = [str(q).strip() for q in item.get("questions", []) if str(q).strip()]
            answer = str(item.get("answer", "")).strip()
            if questions and answer:
                rows.append({**item, "questions": questions, "answer": answer})
        return rows

    def _recreate_collection(self, vector_size: int) -> None:
        existing = [collection.name for collection in self.client.get_collections().collections]
        if self.settings.faq_collection in existing:
            self.client.delete_collection(collection_name=self.settings.faq_collection)
        self.client.create_collection(
            collection_name=self.settings.faq_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

