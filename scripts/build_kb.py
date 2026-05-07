import csv
import json
from pathlib import Path

BASE_DIR = Path.home() / "ai-cs-mvp"
INPUT_CSV = BASE_DIR / "data" / "knowledge.csv"
OUTPUT_JSON = BASE_DIR / "data" / "faq.json"

def main():
    rows = []

    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            status = (raw.get("status") or "").strip().lower()
            if status != "active":
                continue

            faq_id = (raw.get("id") or "").strip()
            answer = (raw.get("answer") or "").strip()
            category = (raw.get("category") or "").strip()
            source = (raw.get("source") or "").strip()
            updated_at = (raw.get("updated_at") or "").strip()
            priority = int((raw.get("priority") or "999").strip())

            tags_raw = (raw.get("tags") or "").strip()
            tags = [x.strip() for x in tags_raw.split(",") if x.strip()]

            question_variants = (raw.get("question_variants") or "").strip()
            questions = [q.strip() for q in question_variants.split("|") if q.strip()]

            if not faq_id or not answer or not questions:
                continue

            rows.append({
                "id": faq_id,
                "questions": questions,
                "answer": answer,
                "category": category,
                "source": source,
                "tags": tags,
                "status": status,
                "updated_at": updated_at,
                "priority": priority
            })

    rows.sort(key=lambda x: (x["priority"], x["id"]))

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"已生成知识库文件: {OUTPUT_JSON}")
    print(f"共写入 {len(rows)} 条知识")

if __name__ == "__main__":
    main()
