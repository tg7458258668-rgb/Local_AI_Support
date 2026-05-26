from __future__ import annotations

import time
import re
from dataclasses import dataclass
from typing import Literal

from support_app.repositories.vector_repository import VectorRepository
from support_app.services.ollama_client import OllamaClient
from support_app.settings import Settings


SourceType = Literal["faq", "doc"]


@dataclass
class RetrievalCandidate:
    source_type: SourceType
    score: float
    adjusted_score: float
    payload: dict
    hit: object
    reason: str


@dataclass
class RetrievalResult:
    faq_hits: list[object]
    doc_hits: list[object]
    faq_candidates: list[RetrievalCandidate]
    doc_candidates: list[RetrievalCandidate]
    faq_top_score: float
    doc_top_score: float
    cache_hit: bool


class RetrievalService:
    CATEGORY_HINTS = {
        "售后": ["售后", "退款", "退货", "换货", "维修", "质保", "保修", "坏了"],
        "报价": ["报价", "价格", "多少钱", "费用", "合同", "优惠"],
        "配置": ["配置", "标配", "选配", "包含", "FreeD", "轨道", "控制器"],
        "产品": ["产品", "功能", "型号", "参数"],
        "发货": ["发货", "物流", "快递", "多久到", "交期"],
    }

    def __init__(self, settings: Settings, ollama: OllamaClient, vector_repo: VectorRepository):
        self.settings = settings
        self.ollama = ollama
        self.vector_repo = vector_repo
        self._cache: dict[tuple[str, str, str], tuple[float, RetrievalResult]] = {}

    def retrieve(
        self,
        query: str,
        channel: str = "api",
        user_id: str | None = None,
        cache_context: str = "",
        bypass_cache: bool = False,
    ) -> RetrievalResult:
        embed_model = self.ollama.current_embed_model()
        cache_key = (query.strip().lower(), channel, user_id or "", embed_model, cache_context or "")
        cached = None if bypass_cache else self._cache.get(cache_key)
        if cached and time.time() - cached[0] <= self.settings.retrieval_cache_ttl_seconds:
            result = cached[1]
            return RetrievalResult(
                faq_hits=result.faq_hits,
                doc_hits=result.doc_hits,
                faq_candidates=result.faq_candidates,
                doc_candidates=result.doc_candidates,
                faq_top_score=result.faq_top_score,
                doc_top_score=result.doc_top_score,
                cache_hit=True,
            )

        vector = self.ollama.embedding(query)
        faq_hits = self.vector_repo.search_faq_by_vector(vector)
        doc_hits = self.vector_repo.search_docs_by_vector(vector)
        faq_candidates = self._rerank(faq_hits, "faq", query)
        doc_candidates = self._rerank(doc_hits, "doc", query)
        result = RetrievalResult(
            faq_hits=[item.hit for item in faq_candidates],
            doc_hits=[item.hit for item in doc_candidates],
            faq_candidates=faq_candidates,
            doc_candidates=doc_candidates,
            faq_top_score=faq_candidates[0].score if faq_candidates else 0.0,
            doc_top_score=doc_candidates[0].score if doc_candidates else 0.0,
            cache_hit=False,
        )
        if not bypass_cache:
            self._cache[cache_key] = (time.time(), result)
            self._trim_cache()
        return result

    def clear_cache(self) -> None:
        self._cache.clear()

    def _rerank(self, hits, source_type: SourceType, query: str) -> list[RetrievalCandidate]:
        candidates = []
        category_hint = self._category_hint(query)
        query_tokens = self._tokens(query)
        for hit in hits:
            payload = hit.payload or {}
            score = float(getattr(hit, "score", 0) or 0)
            text = self._payload_text(payload)
            overlap = len(query_tokens.intersection(self._tokens(text)))
            priority = self._priority(payload.get("priority"))
            category_bonus = 0.04 if category_hint and category_hint in str(payload.get("category", "")) else 0.0
            keyword_bonus = min(overlap * 0.015, 0.09)
            name_bonus = self._name_bonus(query, payload) if source_type == "doc" else 0.0
            semantic_bonus = self._semantic_bonus(query_tokens, payload) if source_type == "doc" else 0.0
            learned_bonus = 0.14 if source_type == "doc" and payload.get("doc_type") == "学习知识" else 0.0
            priority_bonus = max(0, 8 - min(priority, 8)) * 0.004
            adjusted_score = score + category_bonus + keyword_bonus + name_bonus + semantic_bonus + learned_bonus + priority_bonus
            reason = "向量召回"
            if category_bonus:
                reason += f"+分类:{category_hint}"
            if keyword_bonus:
                reason += "+关键词重合"
            if name_bonus:
                reason += "+文件名匹配"
            if semantic_bonus:
                reason += "+语义标签"
            if learned_bonus:
                reason += "+纠错学习"
            candidates.append(RetrievalCandidate(
                source_type=source_type,
                score=score,
                adjusted_score=round(adjusted_score, 4),
                payload=payload,
                hit=hit,
                reason=reason,
            ))
        return sorted(candidates, key=lambda item: item.adjusted_score, reverse=True)

    def _category_hint(self, query: str) -> str:
        for category, keywords in self.CATEGORY_HINTS.items():
            if any(keyword in query for keyword in keywords):
                return category
        return ""

    @staticmethod
    def _payload_text(payload: dict) -> str:
        return " ".join(str(payload.get(key, "")) for key in (
            "question",
            "answer",
            "text",
            "search_text",
            "category",
            "tags",
            "doc_name",
            "source",
            "doc_type",
            "section_title",
            "page_range",
            "semantic_summary",
            "topics",
            "entities",
            "products",
            "scenarios",
            "price_fields",
            "quote_items",
            "price_items",
        ))

    @staticmethod
    def _tokens(text: str) -> set[str]:
        cleaned = str(text or "").lower()
        tokens = set(re.findall(r"[a-z0-9]+", cleaned))
        tokens.update(
            cleaned[i:i + 2]
            for i in range(max(0, len(cleaned) - 1))
            if cleaned[i:i + 2].strip()
        )
        return tokens

    @staticmethod
    def _name_bonus(query: str, payload: dict) -> float:
        target = f"{payload.get('doc_name', '')} {payload.get('source', '')}".lower()
        if not target.strip():
            return 0.0
        query_text = str(query or "").lower()
        parts = set(re.findall(r"[a-z0-9]+", query_text))
        parts.update(
            query_text[i:i + 2]
            for i in range(max(0, len(query_text) - 1))
            if query_text[i:i + 2].strip()
        )
        matches = [
            token for token in parts
            if len(token) >= 2 and token in target
        ]
        return min(len(matches) * 0.025, 0.22)

    @staticmethod
    def _semantic_bonus(query_tokens: set[str], payload: dict) -> float:
        values = []
        for key in ("topics", "entities", "products", "scenarios"):
            value = payload.get(key, [])
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))
        semantic_text = " ".join(values)
        if not semantic_text.strip():
            return 0.0
        matches = query_tokens.intersection(RetrievalService._tokens(semantic_text))
        return min(len(matches) * 0.02, 0.14)

    @staticmethod
    def _priority(value: object) -> int:
        try:
            return max(1, int(value or 999))
        except Exception:
            return 999

    def _trim_cache(self) -> None:
        if len(self._cache) <= 256:
            return
        oldest = sorted(self._cache.items(), key=lambda item: item[1][0])[:64]
        for key, _ in oldest:
            self._cache.pop(key, None)
