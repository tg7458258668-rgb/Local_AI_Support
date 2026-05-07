import json
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document

BASE_DIR = Path.home() / "ai-cs-mvp"
RAW_DIR = BASE_DIR / "data" / "docs_raw"
PARSED_DIR = BASE_DIR / "data" / "docs_parsed"
PARSED_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_EXTS = {".txt", ".md", ".docx", ".pdf"}


def read_txt(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def read_docx(file_path: Path) -> str:
    doc = Document(file_path)
    lines = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def read_pdf(file_path: Path) -> str:
    doc = fitz.open(str(file_path))
    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"[第{page_num}页]\n{text}")
    return "\n\n".join(pages)


def extract_text(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in {".txt", ".md"}:
        return read_txt(file_path)
    if ext == ".docx":
        return read_docx(file_path)
    if ext == ".pdf":
        return read_pdf(file_path)
    raise ValueError(f"不支持的文件类型: {ext}")


def main():
    files = [p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    if not files:
        print("docs_raw 目录里没有可处理的文档。")
        return

    for file_path in files:
        print(f"正在解析: {file_path.name}")
        text = extract_text(file_path)

        out = {
            "doc_name": file_path.stem,
            "source_file": file_path.name,
            "file_type": file_path.suffix.lower().lstrip("."),
            "text": text,
        }

        out_path = PARSED_DIR / f"{file_path.stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        print(f"已生成解析文件: {out_path}")

    print("文档解析完成。")


if __name__ == "__main__":
    main()