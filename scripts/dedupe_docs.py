import json
import math
from pathlib import Path

import requests

BASE_DIR = Path.home() / "ai-cs-mvp"
ANALYSIS_DIR = BASE_DIR / "data" / "docs_analysis"
OUTPUT_PATH = BASE_DIR / "data" / "docs_analysis" / "duplicate_report.json"

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"


def get_embedding(text: str):
    resp = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embedding"]


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_doc_text_for_compare(doc):
    summary = doc.get("summary", "")
    key_points = " ".join(doc.get("key_points", []))
    text_preview = doc.get("text", "")[:2000]
    return f"{summary}\n{key_points}\n{text_preview}".strip()


def main():
    files = sorted(ANALYSIS_DIR.glob("*.json"))
    docs = []

    for file_path in files:
        data = json.load(open(file_path, "r", encoding="utf-8"))
        compare_text = build_doc_text_for_compare(data)
        emb = get_embedding(compare_text)

        docs.append({
            "doc_name": data.get("doc_name", file_path.stem),
            "source_file": data.get("source_file", ""),
            "doc_type": data.get("doc_type", "其他"),
            "summary": data.get("summary", ""),
            "embedding": emb,
        })

    report = []

    for i in range(len(docs)):
        current = docs[i]
        similar_docs = []

        for j in range(len(docs)):
            if i == j:
                continue
            other = docs[j]
            score = cosine_similarity(current["embedding"], other["embedding"])

            if score >= 0.75:
                similar_docs.append({
                    "doc_name": other["doc_name"],
                    "source_file": other["source_file"],
                    "doc_type": other["doc_type"],
                    "score": round(score, 4),
                    "level": "high" if score >= 0.90 else "medium"
                })

        similar_docs.sort(key=lambda x: x["score"], reverse=True)

        report.append({
            "doc_name": current["doc_name"],
            "source_file": current["source_file"],
            "doc_type": current["doc_type"],
            "similar_candidates": similar_docs
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"已生成重复/相似文档报告: {OUTPUT_PATH}")
    for item in report:
        print(f"\n文档: {item['doc_name']}")
        if not item["similar_candidates"]:
            print("  未发现明显重复或相似文档")
        else:
            for candidate in item["similar_candidates"]:
                print(
                    f"  相似文档: {candidate['doc_name']} | "
                    f"相似度: {candidate['score']} | "
                    f"等级: {candidate['level']}"
                )


if __name__ == "__main__":
    main()