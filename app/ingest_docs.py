import json
import uuid
import requests
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "docs_kb"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"

client = QdrantClient(url=QDRANT_URL)

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
    if COLLECTION_NAME in existing:
        client.delete_collection(collection_name=COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

def main():
    with open("data/docs_chunks/docs_chunks.json", "r", encoding="utf-8") as f:
        rows = json.load(f)

    sample_text = rows[0]["text"]
    first_vec = get_embedding(sample_text)
    recreate_collection(len(first_vec))

    points = []
    for row in rows:
        text = row["text"]
        vec = get_embedding(text)

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "chunk_id": row["id"],
                    "doc_name": row.get("doc_name", ""),
                    "section": row.get("section", ""),
                    "category": row.get("category", ""),
                    "source": row.get("source", ""),
                    "text": row.get("text", ""),
                    "updated_at": row.get("updated_at", ""),
                    "priority": row.get("priority", 999)
                },
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"已写入 {len(points)} 条文档向量数据到 {COLLECTION_NAME}")

if __name__ == "__main__":
    main()
