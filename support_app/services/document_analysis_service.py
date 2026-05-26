from __future__ import annotations

import json
import re
from typing import Any

from support_app.services.ollama_client import OllamaClient


class DocumentAnalysisService:
    MODEL_TEXT_LIMIT = 9000

    PRODUCT_PATTERNS = [
        r"U-?MOCO(?:\s+[A-Z0-9-]+){0,3}",
        r"\b(?:GRA|MINI|EXT|AIR|PRO|FreeD|Stream Deck|U-MOCO OS)\b",
    ]
    PRICE_RE = re.compile(r"(?:¥|￥)\s*[\d,]+(?:\.\d+)?|(?:\d+(?:,\d{3})+|\d{4,})\s*元")

    def __init__(self, ollama: OllamaClient | None = None):
        self.ollama = ollama

    def analyze(
        self,
        *,
        doc_name: str,
        text: str,
        category: str = "",
        quote_info: dict | None = None,
        extraction_method: str = "",
    ) -> dict:
        clean_text = self.clean_text(text)
        quote_info = quote_info or {}
        analysis = self._analyze_with_ollama(doc_name, clean_text, category, quote_info)
        if not analysis:
            analysis = self._heuristic_analysis(doc_name, clean_text, category, quote_info)
            analysis["analysis_method"] = "heuristic"
        else:
            analysis = self._normalize_analysis(analysis, doc_name, clean_text, category, quote_info)
            analysis["analysis_method"] = "ollama"

        if not analysis.get("semantic_sections") or self._sections_too_thin(analysis.get("semantic_sections", []), clean_text):
            analysis["semantic_sections"] = self._build_semantic_sections(clean_text, quote_info, analysis)
        analysis["clean_text"] = clean_text
        analysis["diagnostics"] = self._diagnostics(clean_text, analysis, extraction_method)
        return analysis

    def clean_text(self, text: str) -> str:
        normalized = str(text or "").replace("\u200e", "").replace("\ufeff", "")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        lines: list[str] = []
        seen_counts: dict[str, int] = {}
        last = ""
        for raw in normalized.splitlines():
            line = raw.strip()
            if not line:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            if re.fullmatch(r"\[OCR\s+page_\d+\.(?:png|jpg|jpeg)\]", line, re.IGNORECASE):
                continue
            if re.fullmatch(r"1st Art Company in CA", line, re.IGNORECASE):
                continue
            if re.fullmatch(r"H?U-?MOCO\.?", line, re.IGNORECASE):
                continue
            if re.fullmatch(r"[A-Z]\.", line):
                continue
            if re.fullmatch(r"[-_·•\s]*\d{1,3}[-_·•\s]*", line):
                continue
            if re.fullmatch(r"(?:U-?MOCO|M0C0|UMOCO|www\.[\w.-]+){1,3}", line, re.IGNORECASE):
                continue
            if line == last:
                continue
            key = re.sub(r"\s+", "", line).lower()
            seen_counts[key] = seen_counts.get(key, 0) + 1
            if seen_counts[key] > 3 and len(key) < 80:
                continue
            lines.append(line)
            last = line
        clean = "\n".join(lines).strip()
        clean = re.sub(r"\n{3,}", "\n\n", clean)
        return clean

    def _analyze_with_ollama(self, doc_name: str, text: str, category: str, quote_info: dict) -> dict:
        if not self.ollama:
            return {}
        prompt = f"""
你是企业知识库文档分析器。请只输出 JSON，不要解释。
目标：把文档整理成可检索的知识单元，避免把报价、产品参数、售后条款混在一起。

JSON 字段：
doc_type: 产品资料/报价资料/售后政策/项目说明/其他
summary: 80字以内摘要
products: 产品或型号数组
scenarios: 适用场景数组
key_parameters: 关键参数数组
price_items: 报价项数组，每项可含 item/product/amount/note
warranty_terms: 售后或保修条款数组
restrictions: 限制条件数组
key_points: 关键点数组
missing_fields: 需要人工确认或文档缺失字段数组
semantic_sections: 数组，每项含 section_title/page_range/text/topics/entities/semantic_summary/price_fields/quote_items

文档名：{doc_name}
人工分类：{category}
已识别报价线索：{json.dumps(quote_info, ensure_ascii=False)}
文档内容：
{text[:self.MODEL_TEXT_LIMIT]}
"""
        try:
            response = self.ollama.generate(prompt)
        except Exception:
            return {}
        raw = response.get("response", response) if isinstance(response, dict) else response
        return self._parse_json(str(raw or ""))

    def _heuristic_analysis(self, doc_name: str, text: str, category: str, quote_info: dict) -> dict:
        doc_type = category.strip() or self._guess_doc_type(doc_name, text)
        products = self._extract_products(f"{doc_name}\n{text}")
        topics = self._topics_for(text, doc_type)
        scenarios = self._extract_scenarios(text)
        price_items = self._extract_price_items(text, quote_info)
        warranty_terms = self._matching_lines(text, ("保修", "质保", "售后", "维修", "更换", "不保"))
        key_parameters = self._matching_lines(text, ("参数", "臂展", "负载", "速度", "精度", "轨道", "FreeD", "跟焦", "电源", "控制", "直播"))
        restrictions = self._matching_lines(text, ("不包含", "不支持", "需确认", "人工确认", "以合同", "不保", "不在保修", "范围", "另计", "选配"))
        key_points = list(dict.fromkeys((key_parameters + warranty_terms + restrictions)[:10]))
        summary_parts = [doc_type]
        if products:
            summary_parts.append("涉及 " + "、".join(products[:5]))
        if scenarios:
            summary_parts.append("场景包括 " + "、".join(scenarios[:4]))
        summary = "；".join(summary_parts) + "。"
        analysis = {
            "doc_type": doc_type,
            "summary": summary,
            "products": products,
            "scenarios": scenarios,
            "topics": topics,
            "key_parameters": key_parameters[:20],
            "price_items": price_items[:40],
            "warranty_terms": warranty_terms[:20],
            "restrictions": restrictions[:20],
            "key_points": key_points,
            "missing_fields": self._missing_fields(doc_type, text, price_items, warranty_terms),
        }
        analysis["semantic_sections"] = self._build_semantic_sections(text, quote_info, analysis)
        return analysis

    def _normalize_analysis(self, analysis: dict, doc_name: str, text: str, category: str, quote_info: dict) -> dict:
        doc_type = str(analysis.get("doc_type") or category or self._guess_doc_type(doc_name, text))
        normalized = {
            "doc_type": doc_type,
            "summary": str(analysis.get("summary") or "")[:300],
            "products": self._as_list(analysis.get("products")) or self._extract_products(f"{doc_name}\n{text}"),
            "scenarios": self._as_list(analysis.get("scenarios")) or self._extract_scenarios(text),
            "topics": self._as_list(analysis.get("topics")) or self._topics_for(text, doc_type),
            "key_parameters": self._as_list(analysis.get("key_parameters")),
            "price_items": self._as_list(analysis.get("price_items")) or self._extract_price_items(text, quote_info),
            "warranty_terms": self._as_list(analysis.get("warranty_terms")),
            "restrictions": self._as_list(analysis.get("restrictions")),
            "key_points": self._as_list(analysis.get("key_points")),
            "missing_fields": self._as_list(analysis.get("missing_fields")),
            "semantic_sections": self._normalize_sections(analysis.get("semantic_sections"), quote_info),
        }
        if not normalized["summary"]:
            normalized["summary"] = self._heuristic_analysis(doc_name, text, category, quote_info)["summary"]
        return normalized

    def _build_semantic_sections(self, text: str, quote_info: dict, analysis: dict) -> list[dict]:
        pages = self._split_pages(text)
        sections: list[dict] = []
        for page_label, body in pages:
            for title, part in self._split_heading_blocks(body):
                if len(part.strip()) < 12:
                    continue
                section_topics = self._topics_for(part, analysis.get("doc_type", ""))
                if not section_topics:
                    section_topics = analysis.get("topics", [])[:2]
                section_title = title or self._infer_section_title(part, section_topics, page_label)
                entities = self._extract_products(part)
                page_range = page_label or ""
                for chunk_text in self._split_long_text(part):
                    price_like = self._has_price(chunk_text) or "报价" in section_topics
                    sections.append({
                        "section_title": section_title,
                        "page_range": page_range,
                        "text": chunk_text,
                        "topics": section_topics,
                        "entities": entities,
                        "semantic_summary": self._summarize_section(section_title, chunk_text, section_topics),
                        "price_fields": quote_info.get("price_fields", {}) if price_like else {},
                        "quote_items": self._section_quote_items(chunk_text, quote_info) if price_like else [],
                    })
        if sections:
            return sections
        return [{
            "section_title": "正文",
            "page_range": "",
            "text": text[:1200],
            "topics": analysis.get("topics", []),
            "entities": analysis.get("products", []),
            "semantic_summary": analysis.get("summary", ""),
            "price_fields": quote_info.get("price_fields", {}) if self._has_price(text) else {},
            "quote_items": quote_info.get("quote_items", []) if self._has_price(text) else [],
        }]

    def _split_pages(self, text: str) -> list[tuple[str, str]]:
        matches = list(re.finditer(r"\[第(\d+)页(?:\s*OCR)?\]", text))
        if not matches:
            return [("", text)]
        pages = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                pages.append((f"第{match.group(1)}页", body))
        return pages or [("", text)]

    def _split_heading_blocks(self, text: str) -> list[tuple[str, str]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        blocks: list[tuple[str, list[str]]] = []
        current_title = ""
        current: list[str] = []
        for line in lines:
            is_heading = len(line) <= 32 and (
                re.match(r"^\d+(?:\.\d+)*\s+", line)
                or line.endswith(("介绍", "参数", "配置", "报价", "价格", "保修", "售后", "场景", "方案"))
            )
            if is_heading and current:
                blocks.append((current_title, current))
                current = []
                current_title = line
            elif is_heading:
                current_title = line
            else:
                current.append(line)
        if current:
            blocks.append((current_title, current))
        if not blocks and text.strip():
            blocks.append(("", lines))
        return [(title, "\n".join(body)) for title, body in blocks]

    def _split_long_text(self, text: str, limit: int = 900) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        chunks: list[str] = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 <= limit:
                current = f"{current}\n{line}".strip()
                continue
            if len(current) >= 12:
                chunks.append(current)
            current = line
        if len(current) >= 12:
            chunks.append(current)
        if not chunks and len(text.strip()) >= 12:
            chunks.append(text.strip()[:limit])
        return chunks

    def _normalize_sections(self, sections: Any, quote_info: dict) -> list[dict]:
        items = []
        for item in self._as_list(sections):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if len(text) < 12:
                continue
            topics = self._as_list(item.get("topics"))
            price_like = self._has_price(text) or "报价" in topics
            items.append({
                "section_title": str(item.get("section_title") or item.get("title") or "正文")[:80],
                "page_range": str(item.get("page_range") or ""),
                "text": text,
                "topics": topics,
                "entities": self._as_list(item.get("entities")),
                "semantic_summary": str(item.get("semantic_summary") or "")[:300],
                "price_fields": item.get("price_fields") if price_like and isinstance(item.get("price_fields"), dict) else (quote_info.get("price_fields", {}) if price_like else {}),
                "quote_items": self._as_list(item.get("quote_items")) if price_like else [],
            })
        return items

    @staticmethod
    def _sections_too_thin(sections: list[dict], source_text: str) -> bool:
        if not sections:
            return True
        source_len = len(str(source_text or "").strip())
        section_len = sum(len(str(item.get("text", "")).strip()) for item in sections if isinstance(item, dict))
        if source_len < 1200:
            return False
        return section_len < max(800, int(source_len * 0.25))

    def _diagnostics(self, text: str, analysis: dict, extraction_method: str) -> dict:
        sections = analysis.get("semantic_sections") or []
        price_items = analysis.get("price_items") or []
        products = analysis.get("products") or []
        missing = list(analysis.get("missing_fields") or [])
        warnings = []
        if len(text) < 300:
            warnings.append("提取文字较少，可能是扫描版或图片型文档。")
        if not sections:
            warnings.append("未识别到明确章节，已使用普通切块。")
        if "报价" in str(analysis.get("doc_type", "")) and not price_items:
            warnings.append("未识别到明确价格项，请人工检查表格价格。")
        if "售后" in str(analysis.get("doc_type", "")) and not analysis.get("warranty_terms"):
            warnings.append("未识别到保修/售后条款。")
        return {
            "text_char_count": len(text),
            "section_count": len(sections),
            "product_count": len(products),
            "price_item_count": len(price_items),
            "missing_field_count": len(missing),
            "extraction_method": extraction_method,
            "warnings": warnings,
        }

    def _topics_for(self, text: str, doc_type: str = "") -> list[str]:
        haystack = f"{doc_type} {text}"
        mapping = [
            ("报价", ("报价", "价格", "多少钱", "合计", "单价", "优惠", "¥", "￥")),
            ("售后", ("售后", "保修", "质保", "维修", "退换", "不保")),
            ("配置", ("配置", "标配", "选配", "包含", "不包含", "FreeD", "轨道", "控制器")),
            ("参数", ("参数", "臂展", "负载", "速度", "精度", "尺寸", "电源")),
            ("场景", ("场景", "适用", "团播", "直播", "影视", "广告", "电商", "虚拟")),
            ("产品", ("产品", "型号", "机械臂", "系统", "U-MOCO", "GRA", "MINI")),
        ]
        return [topic for topic, keywords in mapping if any(keyword in haystack for keyword in keywords)]

    def _extract_products(self, text: str) -> list[str]:
        found: list[str] = []
        for pattern in self.PRODUCT_PATTERNS:
            found.extend(match.group(0).strip() for match in re.finditer(pattern, text, flags=re.IGNORECASE))
        clean = []
        for item in found:
            item = re.sub(r"\s+", " ", item).strip(" -_，。；:：")
            if len(item) >= 2 and item.upper() not in {"PRO"}:
                clean.append(item)
        return list(dict.fromkeys(clean))[:20]

    def _extract_scenarios(self, text: str) -> list[str]:
        scenarios = []
        for word in ("团播", "直播", "影视", "广告", "电商", "虚拟拍摄", "电视台", "音乐", "体育", "教育", "访谈"):
            if word in text:
                scenarios.append(word)
        return scenarios

    def _extract_price_items(self, text: str, quote_info: dict) -> list[dict]:
        items: list[dict] = []
        for line in quote_info.get("quote_items", []) or []:
            amount = self.PRICE_RE.search(str(line))
            items.append({"item": str(line)[:120], "amount": amount.group(0).replace(" ", "") if amount else "", "source": "quote_line"})
        for line in text.splitlines():
            if not self._has_price(line):
                continue
            amount = self.PRICE_RE.search(line)
            items.append({"item": line.strip()[:120], "amount": amount.group(0).replace(" ", "") if amount else "", "source": "text"})
        unique = []
        seen = set()
        for item in items:
            key = f"{item.get('item')}|{item.get('amount')}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _matching_lines(self, text: str, keywords: tuple[str, ...]) -> list[str]:
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if 8 <= len(line) <= 180 and any(keyword in line for keyword in keywords):
                lines.append(line)
        return list(dict.fromkeys(lines))[:25]

    def _missing_fields(self, doc_type: str, text: str, price_items: list, warranty_terms: list) -> list[str]:
        missing = []
        if "报价" in doc_type and not price_items:
            missing.append("价格项")
        if "售后" in doc_type and not warranty_terms:
            missing.append("保修期限")
        if any(word in text for word in ("FreeD", "轨道", "选配")) and "标配" not in text:
            missing.append("标配/选配边界")
        return missing

    def _infer_section_title(self, text: str, topics: list[str], page_label: str) -> str:
        products = self._extract_products(text)
        prefix = products[0] if products else ""
        topic = topics[0] if topics else "正文"
        if prefix:
            return f"{prefix}｜{topic}"
        if page_label:
            return f"{page_label}｜{topic}"
        return topic

    def _summarize_section(self, title: str, text: str, topics: list[str]) -> str:
        first = re.split(r"[。！？.!?]\s*", re.sub(r"\s+", " ", text).strip())[0]
        if len(first) > 90:
            first = first[:90]
        return f"{title}：{first}" if title and first else first

    def _section_quote_items(self, text: str, quote_info: dict) -> list:
        section_lines = [line.strip() for line in text.splitlines() if self._has_price(line)]
        if section_lines:
            return section_lines[:20]
        return (quote_info.get("quote_items") or [])[:10]

    def _guess_doc_type(self, name: str, text: str) -> str:
        combined = f"{name} {text}"
        if any(keyword in combined for keyword in ("保修", "质保", "售后", "维修政策")):
            return "售后政策"
        if any(keyword in combined for keyword in ("报价", "优惠价", "总价", "单价", "合计", "¥", "￥")):
            return "报价资料"
        if any(keyword in combined for keyword in ("产品", "系统", "机械臂", "参数", "功能", "配置")):
            return "产品资料"
        return "其他"

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if not text:
            return {}
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if match:
            text = match.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _has_price(self, text: str) -> bool:
        return bool(self.PRICE_RE.search(str(text or ""))) or any(token in str(text or "") for token in ("报价", "总价", "单价", "优惠价", "合计"))
