from __future__ import annotations

import re
from datetime import datetime

from support_app.repositories.document_repository import DocumentRepository
from support_app.repositories.learned_knowledge_repository import LearnedKnowledgeRepository
from support_app.schemas import ChatRequest
from support_app.services.document_ingestion_service import DocumentIngestionService


class LearningService:
    CORRECTION_HINTS = ("你说错了", "不对", "不是", "正确是", "正确的是", "以后记住", "应该是", "应当是", "记住")

    def __init__(
        self,
        learned_repo: LearnedKnowledgeRepository,
        document_repo: DocumentRepository,
        document_ingestion_service: DocumentIngestionService,
    ):
        self.learned_repo = learned_repo
        self.document_repo = document_repo
        self.document_ingestion_service = document_ingestion_service

    def enabled_for_request(self, request: ChatRequest) -> bool:
        metadata = request.metadata or {}
        if metadata.get("regression_test") or metadata.get("model_compare"):
            return False
        return bool(metadata.get("test_page") is True)

    def maybe_learn_from_request(self, request: ChatRequest) -> dict:
        result = {
            "enabled": self.enabled_for_request(request),
            "detected": False,
            "saved": False,
            "item": None,
            "message": "",
        }
        if not result["enabled"]:
            return result

        text = request.message.strip()
        if not any(hint in text for hint in self.CORRECTION_HINTS):
            return result

        result["detected"] = True
        fact = self._extract_corrected_fact(text)
        if len(fact) < 8:
            result["message"] = "我还需要你补充正确说法或适用范围，才能把这条修正写入学习库。"
            return result

        item = self.learned_repo.add({
            "question_hint": self._question_hint(fact, text),
            "corrected_fact": fact,
            "category": self._category(text),
            "source_message": text[:500],
            "channel": request.channel,
            "user_id": request.user_id or "",
            "conversation_id": request.conversation_id or "",
        })
        index_error = self._sync_item_to_docs(item)
        result.update({
            "saved": True,
            "item": item,
            "indexed": not bool(index_error),
            "index_error": index_error,
            "message": "收到，我已经把这个修正记下来了，后续会按这个口径回答。"
            if not index_error
            else f"收到，我已保存这条修正；向量入库暂时失败，可稍后在后台重建学习库索引：{index_error}",
        })
        return result

    def list(self, q: str = "") -> dict:
        items = self.learned_repo.list(q)
        return {"total": len(items), "items": items[:200]}

    def delete(self, learned_id: str) -> dict:
        deleted = self.learned_repo.delete(learned_id)
        rows = [
            row for row in self.document_repo.list()
            if row.get("learned_id") != learned_id and row.get("doc_name") != learned_id
        ]
        self.document_repo.save(rows)
        reindex = self.document_ingestion_service.reindex_current_docs()
        return {"ok": True, "deleted": deleted, "reindex": reindex}

    def reindex(self) -> dict:
        rows = [
            row for row in self.document_repo.list()
            if row.get("source") != "learned_correction" and row.get("doc_type") != "学习知识"
        ]
        for item in self.learned_repo.list():
            rows.append(self._item_to_doc_row(item))
        self.document_repo.save(rows)
        return {"ok": True, "total": len(self.learned_repo.list()), "reindex": self.document_ingestion_service.reindex_current_docs()}

    def _sync_item_to_docs(self, item: dict) -> str:
        rows = [
            row for row in self.document_repo.list()
            if row.get("learned_id") != item["id"] and row.get("doc_name") != item["id"]
        ]
        rows.append(self._item_to_doc_row(item))
        self.document_repo.save(rows)
        try:
            self.document_ingestion_service.reindex_current_docs()
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return ""

    @staticmethod
    def _item_to_doc_row(item: dict) -> dict:
        text = (
            f"纠错学习：{item.get('corrected_fact', '')}\n"
            f"适用问题：{item.get('question_hint', '')}\n"
            f"来源客户：{item.get('channel', '')}/{item.get('user_id', '')}"
        ).strip()
        return {
            "id": f"{item.get('id')}_chunk_001",
            "doc_name": item.get("id", ""),
            "section": "纠错学习",
            "category": item.get("category", "学习知识") or "学习知识",
            "source": "learned_correction",
            "summary": item.get("question_hint", ""),
            "key_points": [item.get("corrected_fact", "")],
            "missing_fields": [],
            "doc_type": "学习知识",
            "extraction_method": "correction",
            "price_fields": {},
            "quote_items": [],
            "text": text,
            "learned_id": item.get("id", ""),
            "updated_at": item.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "priority": 1,
        }

    @staticmethod
    def _extract_corrected_fact(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        patterns = [
            r"(?:正确是|正确的是|应该是|应当是|以后记住|记住)[：:，,]?\s*(.+)$",
            r"(?:你说错了|不对|不是)[，,。；; ]+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                return match.group(1).strip(" 。；;，,")
        return ""

    @staticmethod
    def _question_hint(fact: str, source: str) -> str:
        for keyword in ("包含", "价格", "报价", "优惠", "配置", "保修", "交付", "FreeD", "跟焦", "轨道"):
            if keyword in fact or keyword in source:
                return keyword
        return fact[:40]

    @staticmethod
    def _category(text: str) -> str:
        if any(word in text for word in ("报价", "价格", "优惠", "预算")):
            return "报价"
        if any(word in text for word in ("配置", "包含", "FreeD", "跟焦", "轨道", "产品")):
            return "产品"
        if any(word in text for word in ("保修", "售后", "维修", "质保")):
            return "售后"
        return "学习知识"
