import json
import uuid
from pathlib import Path

import requests
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from config import QDRANT_URL, FAQ_COLLECTION, OLLAMA_URL, EMBED_MODEL

client = QdrantClient(url=QDRANT_URL)
FAQ_JSON_PATH = Path("data/faq.json")


def get_embedding(text: str):
    resp = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def recreate_collection(vector_size: int):
    existing = [c.name for c in client.get_collections().collections]
    if FAQ_COLLECTION in existing:
        client.delete_collection(collection_name=FAQ_COLLECTION)

    client.create_collection(
        collection_name=FAQ_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def load_faq_rows():
    if not FAQ_JSON_PATH.exists():
        raise FileNotFoundError(f"未找到 FAQ 文件: {FAQ_JSON_PATH}")

    with open(FAQ_JSON_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("data/faq.json 不是 list 结构")

    active_rows = []
    for row in rows:
        status = str(row.get("status", "active")).strip().lower()
        if status != "active":
            continue

        questions = row.get("questions", [])
        if not isinstance(questions, list):
            questions = []

        questions = [str(q).strip() for q in questions if str(q).strip()]
        if not questions:
            continue

        answer = str(row.get("answer", "")).strip()
        if not answer:
            continue

        active_rows.append({
            "id": str(row.get("id", "")).strip(),
            "questions": questions,
            "answer": answer,
            "category": str(row.get("category", "")).strip(),
            "source": str(row.get("source", "")).strip(),
            "tags": row.get("tags", []) if isinstance(row.get("tags", []), list) else [],
            "updated_at": str(row.get("updated_at", "")).strip(),
            "priority": int(row.get("priority", 999) or 999),
        })

    if not active_rows:
        raise ValueError("没有可用的 active FAQ 数据可入库")

    return active_rows


def sync_faq_vectors():
    rows = load_faq_rows()

    sample_text = rows[0]["questions"][0] + "\n" + rows[0]["answer"]
    first_vec = get_embedding(sample_text)
    recreate_collection(len(first_vec))

    points = []

    for row in rows:
        questions = row.get("questions", [])
        answer = row.get("answer", "")

        for q in questions:
            text = f"问题：{q}\n答案：{answer}"
            vec = get_embedding(text)

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload={
                        "faq_id": row["id"],
                        "question": q,
                        "answer": answer,
                        "category": row.get("category", ""),
                        "source": row.get("source", ""),
                        "tags": row.get("tags", []),
                        "updated_at": row.get("updated_at", ""),
                        "priority": row.get("priority", 999),
                        "text": text,
                    },
                )
            )

    client.upsert(collection_name=FAQ_COLLECTION, points=points)

    return {
        "collection": FAQ_COLLECTION,
        "faq_count": len(rows),
        "point_count": len(points),
    }


def main():
    result = sync_faq_vectors()
    print(
        f"已写入 {result['point_count']} 条FAQ向量数据到 {result['collection']} "
        f"(active FAQ: {result['faq_count']} 条)"
    )


if __name__ == "__main__":
    main()