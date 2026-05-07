import json
import re
from pathlib import Path

BASE_DIR = Path.home() / "ai-cs-mvp"
ANALYSIS_DIR = BASE_DIR / "data" / "docs_analysis"
OUTPUT_PATH = BASE_DIR / "data" / "docs_chunks" / "docs_chunks.json"


def split_into_sections(text: str):
    lines = text.splitlines()
    sections = []
    current_title = "未命名章节"
    current_content = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("## "):
            if current_content:
                sections.append({
                    "section": current_title,
                    "content": "\n".join(current_content).strip()
                })
            current_title = stripped.replace("## ", "", 1).strip()
            current_content = []
        elif stripped.startswith("# "):
            continue
        else:
            current_content.append(stripped)

    if current_content:
        sections.append({
            "section": current_title,
            "content": "\n".join(current_content).strip()
        })

    return sections


def split_sentences(text: str):
    text = text.strip()
    if not text:
        return []

    text = re.sub(r"\s+", " ", text)

    parts = re.split(r"(?<=[。！？])\s*", text)
    parts = [p.strip() for p in parts if p.strip()]

    final_parts = []
    for part in parts:
        subparts = re.split(r"(?=\d+\.)", part)
        subparts = [s.strip() for s in subparts if s.strip()]
        final_parts.extend(subparts)

    return final_parts


def chunk_text(text: str):
    return split_sentences(text)


def main():
    all_chunks = []

    files = sorted(
    p for p in ANALYSIS_DIR.glob("*.json")
    if p.name != "duplicate_report.json"
)
    if not files:
        print("docs_analysis 目录里没有可处理的文件。")
        return

    for file_path in files:
        data = json.load(open(file_path, "r", encoding="utf-8"))
        doc_name = data["doc_name"]
        raw_text = data["text"]
        doc_type = data.get("doc_type", "其他")
        source_file = data.get("source_file", "")
        summary = data.get("summary", "")
        key_points = data.get("key_points", [])
        missing_fields = data.get("missing_fields", [])

        sections = split_into_sections(raw_text)
        if not sections:
            sections = [{"section": "全文", "content": raw_text}]

        chunk_index = 1
        for section in sections:
            section_name = section["section"]
            section_chunks = chunk_text(section["content"])

            for chunk in section_chunks:
                cleaned = chunk.strip()

                # 过滤太短的 chunk
                if len(cleaned) < 12:
                    continue

                # 过滤纯标题型 chunk，例如“以下情况不属于标准保修范围：”
                if cleaned.endswith("：") and len(cleaned) < 30:
                    continue

                all_chunks.append({
                    "id": f"{doc_name}_chunk_{chunk_index:03d}",
                    "doc_name": doc_name,
                    "section": section_name,
                    "category": doc_type,
                    "source": source_file,
                    "summary": summary,
                    "key_points": key_points,
                    "missing_fields": missing_fields,
                    "text": cleaned,
                    "updated_at": "2026-05-02",
                    "priority": 1
                })
                chunk_index += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"已生成文档切块文件: {OUTPUT_PATH}")
    print(f"共写入 {len(all_chunks)} 个文档片段")


if __name__ == "__main__":
    main()