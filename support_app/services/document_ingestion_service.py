from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import requests
from docx import Document

from support_app.repositories.document_repository import DocumentRepository
from support_app.services.ollama_client import OllamaClient
from support_app.services.retrieval_service import RetrievalService
from support_app.settings import Settings


TEXT_EXTS = {".txt", ".md", ".docx", ".pdf", ".pages"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_EXTS = TEXT_EXTS | IMAGE_EXTS


class DocumentIngestionService:
    def __init__(
        self,
        settings: Settings,
        document_repo: DocumentRepository,
        ollama: OllamaClient,
        retrieval_service: RetrievalService,
    ):
        self.settings = settings
        self.document_repo = document_repo
        self.ollama = ollama
        self.retrieval_service = retrieval_service
        self.raw_dir = settings.data_dir / "docs_raw"
        self.parsed_dir = settings.data_dir / "docs_parsed"
        self.chunks_path = settings.data_dir / "docs_chunks" / "docs_chunks.json"
        self.ocr_helper_source = settings.base_dir / "support_app" / "tools" / "vision_ocr.swift"
        self.ocr_helper_bin = settings.base_dir / "runtime" / "vision_ocr"
        self._last_extract_info: dict = {}

    def upload(self, filename: str, content: bytes, category: str = "", doc_name: str = "") -> dict:
        original_name = self._clean_filename(filename)
        ext = Path(original_name).suffix.lower()
        if ext not in SUPPORTED_EXTS:
            raise ValueError(f"不支持的文件类型: {ext or '(无扩展名)'}")
        if not content:
            raise ValueError("上传文件为空")

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_path.parent.mkdir(parents=True, exist_ok=True)

        stored_name = self._unique_filename(original_name)
        raw_path = self.raw_dir / stored_name
        raw_path.write_bytes(content)

        display_name = self._clean_doc_name(doc_name) or Path(original_name).stem
        doc_key = self._clean_doc_name(f"{display_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}")

        if ext in IMAGE_EXTS:
            return {
                "ok": True,
                "status": "saved_without_ocr",
                "message": "图片已保存，第一版暂未 OCR，不会进入检索。",
                "source_file": stored_name,
                "doc_name": display_name,
                "chunk_count": 0,
                "indexed": False,
            }

        self._last_extract_info = {}
        text = self._extract_text(raw_path, ext)
        if not text.strip():
            if ext in {".pdf", ".pages"}:
                return {
                    "ok": True,
                    "status": "saved_without_text",
                    "message": self._empty_text_message(ext),
                    "source_file": stored_name,
                    "doc_name": display_name,
                    "chunk_count": 0,
                    "indexed": False,
                }
            raise ValueError("文件未提取到可入库的文字内容")

        quote_info = self._extract_quote_info(text, display_name)
        extraction_method = self._last_extract_info.get("method", "text")
        doc_type = category.strip() or quote_info.get("doc_type") or self._guess_doc_type(display_name, text)

        parsed = {
            "doc_name": doc_key,
            "display_name": display_name,
            "source_file": stored_name,
            "file_type": ext.lstrip("."),
            "doc_type": doc_type,
            "extraction_method": extraction_method,
            "text_char_count": len(text),
            "price_fields": quote_info.get("price_fields", {}),
            "quote_items": quote_info.get("quote_items", []),
            "summary": "",
            "key_points": [],
            "missing_fields": [],
            "text": text,
            "updated_at": self._now(),
        }
        parsed_path = self.parsed_dir / f"{doc_key}.json"
        parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

        new_chunks = self._build_chunks(parsed)
        if not new_chunks:
            raise ValueError("文件内容太短，未生成可入库的文档片段")

        all_chunks = [
            item for item in self.document_repo.list()
            if item.get("source") != stored_name
        ]
        all_chunks.extend(new_chunks)
        self.document_repo.save(all_chunks)

        try:
            index_result = self._rebuild_docs_index(all_chunks)
            self.retrieval_service.clear_cache()
        except Exception as exc:
            return {
                "ok": False,
                "status": "index_failed",
                "message": f"文件已保存并切块，但向量入库失败：{type(exc).__name__}: {exc}",
                "source_file": stored_name,
                "doc_name": doc_key,
                "chunk_count": len(new_chunks),
                "indexed": False,
            }

        return {
            "ok": True,
            "status": "indexed",
            "message": f"文件已上传、{self._method_label(extraction_method)}并入库。",
            "source_file": stored_name,
            "doc_name": doc_key,
            "chunk_count": len(new_chunks),
            "extraction_method": extraction_method,
            "text_char_count": len(text),
            "doc_type": doc_type,
            "indexed": True,
            "index": index_result,
        }

    def delete_doc(self, doc_name: str) -> dict:
        target = str(doc_name or "").strip()
        if not target:
            raise ValueError("doc_name 不能为空")
        return self.delete_docs([target])

    def delete_docs(self, doc_names: list[str]) -> dict:
        targets = list(dict.fromkeys(str(name or "").strip() for name in doc_names if str(name or "").strip()))
        if not targets:
            raise ValueError("doc_names 不能为空")

        rows = self.document_repo.list()
        target_set = set(targets)
        deleted_rows = [item for item in rows if item.get("doc_name") in target_set]
        if not deleted_rows:
            raise KeyError(f"未找到文档: {', '.join(targets)}")

        deleted_names = sorted({item.get("doc_name", "") for item in deleted_rows if item.get("doc_name")})
        missing_names = [name for name in targets if name not in deleted_names]
        remaining_rows = [item for item in rows if item.get("doc_name") not in target_set]
        raw_files = sorted({item.get("source", "") for item in deleted_rows if item.get("source")})
        parsed_files = sorted({f"{item.get('doc_name')}.json" for item in deleted_rows if item.get("doc_name")})

        self.document_repo.save(remaining_rows)
        removed_files = []
        for filename in raw_files:
            path = self.raw_dir / filename
            if path.exists() and path.is_file():
                path.unlink()
                removed_files.append(str(path))
        for filename in parsed_files:
            path = self.parsed_dir / filename
            if path.exists() and path.is_file():
                path.unlink()
                removed_files.append(str(path))

        index_result = {"collection": self.settings.doc_collection, "chunk_count": 0, "point_count": 0}
        if remaining_rows:
            index_result = self._rebuild_docs_index(remaining_rows)
        else:
            self._delete_docs_collection()

        self.retrieval_service.clear_cache()
        return {
            "ok": True,
            "deleted_doc_name": deleted_names[0] if len(deleted_names) == 1 else "",
            "deleted_doc_names": deleted_names,
            "missing_doc_names": missing_names,
            "deleted_chunk_count": len(deleted_rows),
            "removed_files": removed_files,
            "remaining_chunk_count": len(remaining_rows),
            "index": index_result,
        }

    def _extract_text(self, path: Path, ext: str) -> str:
        if ext in {".txt", ".md"}:
            return self._read_text(path)
        if ext == ".docx":
            doc = Document(path)
            lines = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
            return "\n".join(lines)
        if ext == ".pdf":
            return self._extract_pdf_text(path)
        if ext == ".pages":
            return self._extract_pages_text(path)
        raise ValueError(f"不支持解析的文件类型: {ext}")

    @staticmethod
    def _empty_text_message(ext: str) -> str:
        if ext == ".pages":
            return "Pages 文件已保存，但未提取到文字；请从 Pages 导出为 PDF 或 DOCX 后再上传。"
        return "PDF 文件已保存，但未提取到文字；如果是扫描版 PDF，需要先 OCR 或导出为可复制文字的 PDF。"

    def _extract_pages_text(self, path: Path) -> str:
        text = self._extract_pages_preview_pdf(path)
        if text.strip():
            self._last_extract_info = {"method": "preview_pdf_text"}
            return text
        text = self._extract_pages_with_textutil(path)
        if text.strip():
            self._last_extract_info = {"method": "textutil"}
            return text
        text = self._extract_pages_preview_ocr(path)
        if text.strip():
            self._last_extract_info = {"method": "pages_preview_ocr"}
        return text

    def _extract_pages_preview_pdf(self, path: Path) -> str:
        if not zipfile.is_zipfile(path):
            return ""
        try:
            with zipfile.ZipFile(path) as pages_zip:
                pdf_names = [
                    name for name in pages_zip.namelist()
                    if name.lower().endswith(".pdf")
                ]
                pdf_names.sort(key=lambda name: (
                    0 if name.lower().endswith("quicklook/preview.pdf") else 1,
                    name.lower(),
                ))
                for pdf_name in pdf_names:
                    text = self._extract_pdf_text_bytes(pages_zip.read(pdf_name))
                    if text.strip():
                        return text
        except (OSError, RuntimeError, zipfile.BadZipFile):
            return ""
        return ""

    @staticmethod
    def _extract_pages_with_textutil(path: Path) -> str:
        textutil = shutil.which("textutil")
        if not textutil:
            return ""
        try:
            result = subprocess.run(
                [textutil, "-convert", "txt", "-stdout", str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _extract_pdf_text(self, path: Path) -> str:
        with fitz.open(str(path)) as doc:
            pages = []
            ocr_used = False
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
                if text:
                    pages.append(f"[第{page_num}页]\n{text}")
                if len(text) < 80 and page.get_images(full=True):
                    ocr_text = self._ocr_pdf_page(page, page_num)
                    if ocr_text and ocr_text not in text:
                        pages.append(f"[第{page_num}页 OCR]\n{ocr_text}")
                        ocr_used = True
            self._last_extract_info = {"method": "pdf_text_ocr" if ocr_used else "pdf_text"}
            return "\n\n".join(pages)

    def _extract_pdf_text_bytes(self, content: bytes) -> str:
        with fitz.open(stream=BytesIO(content), filetype="pdf") as doc:
            return self._extract_text_from_pdf_doc(doc)

    def _extract_pages_preview_ocr(self, path: Path) -> str:
        if not zipfile.is_zipfile(path):
            return ""
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            image_paths = []
            try:
                with zipfile.ZipFile(path) as pages_zip:
                    names = [
                        name for name in pages_zip.namelist()
                        if Path(name).name.lower() in {"preview.jpg", "preview.png", "preview-web.jpg"}
                    ]
                    names.sort(key=lambda name: (
                        0 if Path(name).name.lower() == "preview.jpg" else 1,
                        name.lower(),
                    ))
                    selected_names = [name for name in names if Path(name).name.lower() == "preview.jpg"]
                    if not selected_names:
                        selected_names = names[:1]
                    for name in selected_names:
                        out = tmp / Path(name).name
                        out.write_bytes(pages_zip.read(name))
                        image_paths.append(out)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                return ""
            if not image_paths:
                image_paths = self._quicklook_images(path, tmp)
            return self._ocr_images(image_paths)

    def _quicklook_images(self, path: Path, output_dir: Path) -> list[Path]:
        qlmanage = shutil.which("qlmanage") or "/usr/bin/qlmanage"
        if not Path(qlmanage).exists():
            return []
        try:
            subprocess.run(
                [qlmanage, "-t", "-s", "2200", "-o", str(output_dir), str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        return sorted(output_dir.glob("*.png")) + sorted(output_dir.glob("*.jpg"))

    def _ocr_pdf_page(self, page: fitz.Page, page_num: int) -> str:
        with TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / f"page_{page_num:03d}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            pix.save(str(image_path))
            return self._ocr_images([image_path])

    def _ocr_images(self, image_paths: list[Path]) -> str:
        paths = [path for path in image_paths if path.exists()]
        if not paths:
            return ""
        helper = self._ensure_ocr_helper()
        if not helper:
            return ""
        try:
            result = subprocess.run(
                [str(helper), *[str(path) for path in paths]],
                capture_output=True,
                text=True,
                timeout=max(45, 25 * len(paths)),
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0 and not result.stdout.strip():
            return ""
        return self._clean_ocr_output(result.stdout)

    def _ensure_ocr_helper(self) -> Path | None:
        if not self.ocr_helper_source.exists():
            return None
        self.ocr_helper_bin.parent.mkdir(parents=True, exist_ok=True)
        if (
            self.ocr_helper_bin.exists()
            and self.ocr_helper_bin.stat().st_mtime >= self.ocr_helper_source.stat().st_mtime
        ):
            return self.ocr_helper_bin
        swiftc = shutil.which("swiftc") or "/usr/bin/swiftc"
        if not Path(swiftc).exists():
            return None
        result = subprocess.run(
            [swiftc, str(self.ocr_helper_source), "-O", "-o", str(self.ocr_helper_bin)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            return None
        return self.ocr_helper_bin

    @staticmethod
    def _clean_ocr_output(text: str) -> str:
        blocks = []
        current = []
        current_file = ""
        for line in text.splitlines():
            if line.startswith("###FILE:"):
                if current:
                    blocks.append((current_file, "\n".join(current).strip()))
                    current = []
                current_file = Path(line.removeprefix("###FILE:")).name
                continue
            if line.strip():
                current.append(line.strip())
        if current:
            blocks.append((current_file, "\n".join(current).strip()))
        return "\n\n".join(f"[OCR {name}]\n{body}" if name else body for name, body in blocks if body)

    @staticmethod
    def _extract_text_from_pdf_doc(doc: fitz.Document) -> str:
        pages = []
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append(f"[第{page_num}页]\n{text}")
        return "\n\n".join(pages)

    @staticmethod
    def _read_text(path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    def _build_chunks(self, parsed: dict) -> list[dict]:
        doc_name = parsed["doc_name"]
        category = parsed.get("doc_type", "其他") or "其他"
        source = parsed.get("source_file", "")
        chunks = []
        for index, text in enumerate(self._chunk_text(parsed.get("text", ""), parsed), start=1):
            chunks.append({
                "id": f"{doc_name}_chunk_{index:03d}",
                "doc_name": doc_name,
                "section": "全文",
                "category": category,
                "source": source,
                "summary": parsed.get("summary", ""),
                "key_points": parsed.get("key_points", []),
                "missing_fields": parsed.get("missing_fields", []),
                "doc_type": parsed.get("doc_type", ""),
                "extraction_method": parsed.get("extraction_method", ""),
                "price_fields": parsed.get("price_fields", {}),
                "quote_items": parsed.get("quote_items", []),
                "text": text,
                "updated_at": self._now(),
                "priority": 1,
            })
        return chunks

    def _chunk_text(self, text: str, parsed: dict | None = None) -> list[str]:
        parsed = parsed or {}
        if parsed.get("price_fields") or parsed.get("quote_items"):
            return self._chunk_quote_text(text, parsed)
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        sentences = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s*", normalized) if item.strip()]
        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= 550:
                current = f"{current} {sentence}".strip()
            else:
                if len(current) >= 12:
                    chunks.append(current)
                current = sentence
        if len(current) >= 12:
            chunks.append(current)
        if not chunks and len(normalized) >= 12:
            chunks.append(normalized[:900])
        return chunks

    @staticmethod
    def _chunk_quote_text(text: str, parsed: dict) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        header = f"文档类型：{parsed.get('doc_type', '报价单')}；解析方式：{parsed.get('extraction_method', '')}"
        prices = parsed.get("price_fields", {})
        if prices:
            header += "；价格字段：" + "；".join(f"{key}={value}" for key, value in prices.items())
        chunks = []
        current = header
        for line in lines:
            if len(current) + len(line) <= 700:
                current = f"{current}\n{line}".strip()
            else:
                if len(current) >= 12:
                    chunks.append(current)
                current = f"{header}\n{line}"
        if len(current) >= 12:
            chunks.append(current)
        return chunks

    def _rebuild_docs_index(self, rows: list[dict]) -> dict:
        active_rows = [row for row in rows if str(row.get("text", "")).strip()]
        if not active_rows:
            raise ValueError("没有可入库的文档片段")

        first_vector = self.ollama.embedding(active_rows[0]["text"])
        self._recreate_collection(len(first_vector))

        points = []
        for row in active_rows:
            vector = self.ollama.embedding(row["text"])
            points.append({
                "id": str(uuid.uuid4()),
                "vector": vector,
                "payload": {
                    "chunk_id": row.get("id", ""),
                    "doc_name": row.get("doc_name", ""),
                    "section": row.get("section", ""),
                    "category": row.get("category", ""),
                    "source": row.get("source", ""),
                    "summary": row.get("summary", ""),
                    "key_points": row.get("key_points", []),
                    "missing_fields": row.get("missing_fields", []),
                    "doc_type": row.get("doc_type", ""),
                    "extraction_method": row.get("extraction_method", ""),
                    "price_fields": row.get("price_fields", {}),
                    "quote_items": row.get("quote_items", []),
                    "text": row.get("text", ""),
                    "updated_at": row.get("updated_at", ""),
                    "priority": row.get("priority", 999),
                },
            })

        resp = requests.put(
            f"{self.settings.qdrant_url}/collections/{self.settings.doc_collection}/points",
            json={"points": points},
            timeout=180,
        )
        resp.raise_for_status()
        return {
            "collection": self.settings.doc_collection,
            "chunk_count": len(active_rows),
            "point_count": len(points),
        }

    def _recreate_collection(self, vector_size: int) -> None:
        requests.delete(
            f"{self.settings.qdrant_url}/collections/{self.settings.doc_collection}",
            timeout=30,
        )
        resp = requests.put(
            f"{self.settings.qdrant_url}/collections/{self.settings.doc_collection}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            timeout=30,
        )
        resp.raise_for_status()

    def _delete_docs_collection(self) -> None:
        requests.delete(
            f"{self.settings.qdrant_url}/collections/{self.settings.doc_collection}",
            timeout=30,
        )

    def _unique_filename(self, filename: str) -> str:
        stem = self._clean_doc_name(Path(filename).stem) or "document"
        ext = Path(filename).suffix.lower()
        candidate = f"{stem}{ext}"
        if not (self.raw_dir / candidate).exists():
            return candidate
        return f"{stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"

    @staticmethod
    def _clean_filename(filename: str) -> str:
        name = Path(filename or "upload").name.strip()
        return name or "upload"

    @staticmethod
    def _clean_doc_name(value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"[^\w\u4e00-\u9fa5.-]+", "_", text)
        return text.strip("._-")

    @staticmethod
    def _method_label(method: str) -> str:
        labels = {
            "pdf_text": "文本解析",
            "pdf_text_ocr": "文本+OCR解析",
            "preview_pdf_text": "Pages预览PDF解析",
            "textutil": "Pages文本解析",
            "pages_preview_ocr": "Pages预览图OCR解析",
        }
        return labels.get(method, "解析")

    @staticmethod
    def _guess_doc_type(name: str, text: str) -> str:
        if any(keyword in f"{name} {text}" for keyword in ("报价", "优惠价", "总价", "单价", "合计")):
            return "报价单"
        if any(keyword in f"{name} {text}" for keyword in ("产品", "系统", "机械臂", "参数", "功能")):
            return "产品资料"
        return "其他"

    def _extract_quote_info(self, text: str, display_name: str) -> dict:
        price_fields = {}
        normalized = text.replace("\u200e", "").replace("\ufeff", "")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        price_patterns = [
            ("优惠价", r"优惠价(?:\([^)]*\)|（[^）]*）)?\s*[：:]?\s*([¥￥]\s*[\d,]+(?:\.\d+)?)"),
            ("总价（含税13%）", r"总价(?:（含税13%）|\(含税13%\))?\s*[：:]?\s*([¥￥]\s*[\d,]+(?:\.\d+)?)"),
            ("总价", r"总价\s*[：:]?\s*([¥￥]\s*[\d,]+(?:\.\d+)?)"),
            ("合计", r"合计\s*([¥￥]\s*[\d,]+(?:\.\d+)?)"),
            ("单价", r"单价\s*([¥￥]\s*[\d,]+(?:\.\d+)?)"),
        ]
        for label, pattern in price_patterns:
            match = re.search(pattern, normalized)
            if match:
                price_fields[label] = re.sub(r"\s+", "", match.group(1))
        amounts = re.findall(r"[¥￥]\s*[\d,]+(?:\.\d+)?", normalized)
        if amounts:
            clean_amounts = list(dict.fromkeys(re.sub(r"\s+", "", item) for item in amounts))
            if "优惠价" in normalized and "优惠价" not in price_fields:
                price_fields["优惠价"] = clean_amounts[-1]
            if "总价" in normalized and "总价（含税13%）" not in price_fields:
                price_fields["总价（含税13%）"] = clean_amounts[-2 if "优惠价" in price_fields and len(clean_amounts) >= 2 else -1]
            price_fields.setdefault("全部金额", "、".join(clean_amounts))
        quote_items = [
            line.strip() for line in text.splitlines()
            if any(token in line for token in ("¥", "￥", "报价", "总价", "优惠价", "合计", "单价"))
        ][:30]
        return {
            "doc_type": self._guess_doc_type(display_name, text),
            "price_fields": price_fields,
            "quote_items": quote_items,
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
