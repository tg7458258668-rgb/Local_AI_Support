from __future__ import annotations

import re
from typing import Any


class PostRuleCheckService:
    BLOCKED_TERMS = [
        "保证交付",
        "保证有货",
        "保证现货",
        "一定能发货",
        "最低价就是",
        "可以确认合同",
        "合同可以确认",
        "一定能到",
        "肯定有库存",
    ]
    DISCLAIMER_TERMS = [
        "人工确认",
        "销售确认",
        "同事确认",
        "以销售确认为准",
        "最终以合同为准",
        "最终以销售为准",
        "需要销售",
        "需要人工",
        "需人工确认",
        "需销售确认",
    ]
    HANDOFF_TERMS = [
        "人工",
        "销售",
        "同事",
        "转接",
        "确认",
    ]
    SAFE_FALLBACK_ANSWER = (
        "这个问题涉及具体配置或商务确认，我可以先帮您整理需求，具体价格、库存或交付时间需要由销售同事进一步确认。"
    )

    def check(
        self,
        route: str,
        answer: str,
        risk_plan: dict | None = None,
        quote_readiness: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        route = str(route or "").strip()
        answer = str(answer or "")
        risk_plan = risk_plan if isinstance(risk_plan, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        risk_level = str(risk_plan.get("risk_level", "") or "").strip().lower()

        warnings: list[str] = []
        matched_terms: list[str] = []
        checked_items: list[str] = []
        blocked = False
        need_rewrite = False
        need_human = False
        safe_answer: str | None = None

        checked_items.append("non_empty_answer")
        if not answer.strip():
            need_rewrite = True
            safe_answer = self.SAFE_FALLBACK_ANSWER
            checked_items.append("empty_answer_failed")
            return self._build_result(
                passed=False,
                blocked=False,
                need_rewrite=True,
                need_human=True,
                safe_answer=safe_answer,
                warnings=["empty_answer"],
                matched_terms=[],
                checked_items=checked_items,
            )

        checked_items.append("blocked_terms_check")
        blocked_hits = [term for term in self.BLOCKED_TERMS if term in answer]
        if blocked_hits:
            blocked = True
            need_rewrite = True
            need_human = True
            matched_terms.extend(blocked_hits)
            safe_answer = self.SAFE_FALLBACK_ANSWER

        checked_items.append("risk_disclaimer_check")
        has_disclaimer = self._contains_any(answer, self.DISCLAIMER_TERMS)
        if risk_level in {"medium", "high", "blocked"} and not has_disclaimer:
            need_rewrite = True
            need_human = True
            warnings.append("missing_risk_disclaimer")
            safe_answer = self._append_safety_hint(answer)

        checked_items.append("price_number_source_check")
        has_price_number = self._has_price_number(answer)
        source_ready = self._has_price_source(metadata)
        if (risk_level in {"medium", "high"} or route == "quote_inquiry") and has_price_number and not source_ready:
            warnings.append("price_number_without_source")
            need_human = True

        checked_items.append("handoff_route_check")
        if route == "handoff" and not self._contains_any(answer, self.HANDOFF_TERMS):
            need_rewrite = True
            need_human = True
            warnings.append("handoff_message_missing_human_guidance")
            safe_answer = self.SAFE_FALLBACK_ANSWER

        checked_items.append("quote_draft_disclaimer_check")
        if (route == "quote_draft" or bool(quote_readiness)) and not has_disclaimer:
            need_rewrite = True
            need_human = True
            warnings.append("quote_draft_missing_final_confirmation")
            safe_answer = self._append_safety_hint(answer)

        passed = not need_rewrite and not blocked
        return self._build_result(
            passed=passed,
            blocked=blocked,
            need_rewrite=need_rewrite,
            need_human=need_human,
            safe_answer=safe_answer,
            warnings=warnings,
            matched_terms=matched_terms,
            checked_items=checked_items,
        )

    def _append_safety_hint(self, answer: str) -> str:
        base = answer.strip()
        if not base:
            return self.SAFE_FALLBACK_ANSWER
        if self.SAFE_FALLBACK_ANSWER in base:
            return base
        return f"{base}\n{self.SAFE_FALLBACK_ANSWER}"

    @staticmethod
    def _contains_any(text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _has_price_number(text: str) -> bool:
        patterns = [
            r"[¥￥]\s*\d[\d,]*(?:\.\d+)?",
            r"\d[\d,]*(?:\.\d+)?\s*元",
            r"\d[\d,]*(?:\.\d+)?\s*万元",
            r"\d[\d,]*(?:\.\d+)?\s*万",
        ]
        return any(re.search(pattern, text) for pattern in patterns)

    @staticmethod
    def _has_price_source(metadata: dict[str, Any]) -> bool:
        source_ids = metadata.get("source_ids")
        if isinstance(source_ids, list) and len(source_ids) > 0:
            return True
        quote_source = metadata.get("quote_source")
        if isinstance(quote_source, str) and quote_source.strip():
            return True
        quote_sources = metadata.get("quote_sources")
        if isinstance(quote_sources, list) and len(quote_sources) > 0:
            return True
        sources = metadata.get("sources")
        if isinstance(sources, list) and len(sources) > 0:
            return True
        return False

    @staticmethod
    def _build_result(
        passed: bool,
        blocked: bool,
        need_rewrite: bool,
        need_human: bool,
        safe_answer: str | None,
        warnings: list[str],
        matched_terms: list[str],
        checked_items: list[str],
    ) -> dict:
        return {
            "passed": bool(passed),
            "blocked": bool(blocked),
            "need_rewrite": bool(need_rewrite),
            "need_human": bool(need_human),
            "safe_answer": safe_answer,
            "warnings": list(dict.fromkeys(warnings)),
            "matched_terms": list(dict.fromkeys(matched_terms)),
            "checked_items": list(dict.fromkeys(checked_items)),
        }
