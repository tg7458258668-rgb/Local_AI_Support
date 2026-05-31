from __future__ import annotations

from typing import Any


class UnderstandPlanAdapter:
    PRONOUN_TERMS = ("这个", "那个", "那款", "它", "换成")
    PRICE_TRACK_TERMS = ("多少钱", "报价", "价格", "要不要轨道")
    QUOTE_INTENTS = {"quote_inquiry", "handoff"}
    QUOTE_STAGES = {"quote", "quote_prepare", "quote_ready"}
    RISK_SENSITIVE_LEVELS = {"medium", "high", "blocked"}

    def build(
        self,
        message: str,
        intent_plan: dict | None = None,
        sales_plan: dict | None = None,
        context_plan: dict | None = None,
        conversation_state: dict | None = None,
        risk_plan: dict | None = None,
    ) -> dict:
        raw_message = str(message or "")
        intent = dict(intent_plan or {})
        sales = dict(sales_plan or {})
        context = dict(context_plan or {})
        state = dict(conversation_state or {})
        risk = dict(risk_plan or {})

        resolved_query = self._first_non_empty(
            context.get("resolved_query"),
            intent.get("resolved_query"),
            context.get("resolved_question"),
            raw_message,
        )

        product_anchors = self._normalize_anchor_list(intent.get("product_anchors"))
        product_anchor = self._first_non_empty(
            product_anchors[0] if product_anchors else "",
            context.get("product_anchor"),
            state.get("product_anchor"),
        )
        if not product_anchors and product_anchor:
            product_anchors = [product_anchor]

        scenario_anchor = self._first_non_empty(
            context.get("scenario_anchor"),
            self._dig(sales, "known_needs", "scenario"),
            state.get("scenario_anchor"),
            self._dig(state, "known_needs", "scenario"),
        )

        is_followup = self._to_bool(
            context.get("is_followup"),
            context.get("contextual_followup"),
            intent.get("contextual_followup"),
        )
        if not is_followup and state.get("product_anchor") and self._contains_any(raw_message, self.PRONOUN_TERMS):
            is_followup = True

        primary_intent = self._first_non_empty(
            intent.get("primary_intent"),
            intent.get("intent"),
            intent.get("name"),
            "fallback",
        )
        confidence = self._first_value(intent.get("confidence"), intent.get("score"))
        needs_quote_tool = bool(intent.get("needs_quote_tool"))
        if not needs_quote_tool:
            needs_quote_tool = bool(sales.get("should_quote"))
        quote_readiness = self._first_value(sales.get("quote_readiness"), state.get("quote_readiness"))
        if not needs_quote_tool and str(quote_readiness or "") in {"ready_for_ref", "ready_for_human_quote"}:
            needs_quote_tool = True

        sales_stage = self._first_non_empty(sales.get("sales_stage"), sales.get("stage"), state.get("stage"))
        merged_known_needs = self._merge_known_needs(state.get("known_needs"), sales.get("known_needs"))
        missing_fields = self._normalize_str_list(self._first_value(sales.get("missing_fields"), state.get("missing_fields"), []))

        risk_level = str(risk.get("risk_level") or "").strip()
        risk_need_human = bool(risk.get("need_human")) if risk else False
        risk_reasons = self._normalize_str_list(risk.get("risk_reasons"))
        matched_keywords = self._normalize_str_list(risk.get("matched_keywords"))
        intent_risk_flags = self._normalize_str_list(intent.get("risk_flags"))
        state_risk_flags = self._normalize_str_list(state.get("risk_flags"))
        if not risk_level and (intent_risk_flags or state_risk_flags):
            risk_level = "high"
        if not risk_reasons:
            risk_reasons = intent_risk_flags or state_risk_flags

        has_state = bool(state)
        state_quote_readiness = self._first_non_empty(state.get("quote_readiness"))
        state_handoff = bool(state.get("human_handoff_required"))

        reason_codes: list[str] = []
        should_bypass = False
        if is_followup:
            should_bypass = True
            reason_codes.append("contextual_followup")
        if primary_intent in self.QUOTE_INTENTS:
            should_bypass = True
            reason_codes.append("quote_intent")
        if sales_stage in self.QUOTE_STAGES:
            should_bypass = True
            reason_codes.append("quote_stage")
        if risk_level in self.RISK_SENSITIVE_LEVELS:
            should_bypass = True
            reason_codes.append("risk_sensitive")
        if state_handoff:
            should_bypass = True
            reason_codes.append("handoff_state")
        if self._contains_any(raw_message, self.PRONOUN_TERMS):
            should_bypass = True
            reason_codes.append("pronoun_reference")
        if self._contains_any(raw_message, self.PRICE_TRACK_TERMS):
            should_bypass = True
            reason_codes.append("price_or_track_question")

        return {
            "context": {
                "is_followup": bool(is_followup),
                "resolved_query": resolved_query,
                "product_anchor": product_anchor,
                "scenario_anchor": scenario_anchor,
                "product_anchors": product_anchors,
                "source": "intent_plan/context_plan/state",
            },
            "intent": {
                "primary_intent": primary_intent,
                "confidence": confidence,
                "needs_quote_tool": bool(needs_quote_tool),
                "risk_flags": intent_risk_flags,
                "source": "intent_plan",
            },
            "sales": {
                "stage": sales_stage,
                "known_needs": merged_known_needs,
                "missing_fields": missing_fields,
                "quote_readiness": quote_readiness if quote_readiness is not None else "",
                "source": "sales_plan/state",
            },
            "risk": {
                "risk_level": risk_level,
                "need_human": bool(risk_need_human),
                "risk_reasons": risk_reasons,
                "matched_keywords": matched_keywords,
            },
            "state_ref": {
                "has_state": has_state,
                "product_anchor": str(state.get("product_anchor") or ""),
                "scenario_anchor": str(state.get("scenario_anchor") or ""),
                "quote_readiness": state_quote_readiness,
                "human_handoff_required": state_handoff,
            },
            "cache_hints": {
                "should_bypass_cache": bool(should_bypass),
                "reason_codes": list(dict.fromkeys(reason_codes)),
            },
        }

    @staticmethod
    def _first_value(*values):
        for value in values:
            if value is not None:
                return value
        return None

    @staticmethod
    def _first_non_empty(*values) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _normalize_anchor_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _normalize_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _merge_known_needs(state_known: Any, sales_known: Any) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if isinstance(state_known, dict):
            merged.update(state_known)
        if isinstance(sales_known, dict):
            merged.update(sales_known)
        return merged

    @staticmethod
    def _to_bool(*values) -> bool:
        for value in values:
            if isinstance(value, bool):
                return value
        return False

    @staticmethod
    def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
        raw = str(text or "")
        return any(term in raw for term in terms)

    @staticmethod
    def _dig(payload: dict, key: str, sub_key: str) -> str:
        if isinstance(payload.get(key), dict):
            return str(payload[key].get(sub_key) or "").strip()
        return ""
