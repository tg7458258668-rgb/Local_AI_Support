from __future__ import annotations

from typing import Any


class CachePolicyMetadataService:
    PRONOUN_TERMS = ("这个", "那个", "那款", "它", "换成")
    PRICE_TRACK_TERMS = ("多少钱", "报价", "价格", "要不要轨道")
    QUOTE_INTENTS = {"quote_inquiry", "handoff", "quote_price"}
    QUOTE_STAGES = {"quote", "quote_prepare", "quote_ready"}
    RISK_LEVELS = {"medium", "high", "blocked"}

    def build(
        self,
        message: str,
        understand_plan: dict | None = None,
        context_plan: dict | None = None,
        risk_plan: dict | None = None,
        risk_precheck: dict | None = None,
        conversation_state_after: dict | None = None,
        current_retrieval_bypass_cache: bool | None = None,
    ) -> dict[str, Any]:
        understand = understand_plan if isinstance(understand_plan, dict) else {}
        context = context_plan if isinstance(context_plan, dict) else {}
        risk = risk_plan if isinstance(risk_plan, dict) else {}
        precheck = risk_precheck if isinstance(risk_precheck, dict) else {}
        state_after = conversation_state_after if isinstance(conversation_state_after, dict) else {}
        text = str(message or "")

        should_bypass_cache = False
        reason_codes: list[str] = []
        source_fields_used: list[str] = []

        if self._dig_bool(understand, "cache_hints", "should_bypass_cache"):
            should_bypass_cache = True
            reason_codes.append("understand_cache_hint")
            source_fields_used.append("understand_plan.cache_hints")

        if self._dig_bool(understand, "context", "is_followup"):
            should_bypass_cache = True
            reason_codes.append("contextual_followup")
            source_fields_used.append("understand_plan.context.is_followup")

        primary_intent = self._dig_str(understand, "intent", "primary_intent")
        if primary_intent in self.QUOTE_INTENTS:
            should_bypass_cache = True
            reason_codes.append("quote_intent")
            source_fields_used.append("understand_plan.intent.primary_intent")

        sales_stage = self._dig_str(understand, "sales", "stage")
        if sales_stage in self.QUOTE_STAGES:
            should_bypass_cache = True
            reason_codes.append("quote_stage")
            source_fields_used.append("understand_plan.sales.stage")

        understand_risk_level = self._dig_str(understand, "risk", "risk_level")
        if understand_risk_level in self.RISK_LEVELS:
            should_bypass_cache = True
            reason_codes.append("risk_sensitive")
            source_fields_used.append("understand_plan.risk.risk_level")

        risk_level = str(risk.get("risk_level") or "").strip().lower()
        if risk_level in self.RISK_LEVELS:
            should_bypass_cache = True
            reason_codes.append("risk_sensitive")
            source_fields_used.append("risk_plan.risk_level")

        precheck_level = str(precheck.get("risk_level") or "").strip().lower()
        if precheck_level in self.RISK_LEVELS:
            should_bypass_cache = True
            reason_codes.append("risk_sensitive")
            source_fields_used.append("risk_precheck.risk_level")

        if bool(state_after.get("human_handoff_required")):
            should_bypass_cache = True
            reason_codes.append("handoff_state")
            source_fields_used.append("conversation_state_after.human_handoff_required")

        if self._contains_any(text, self.PRONOUN_TERMS):
            should_bypass_cache = True
            reason_codes.append("pronoun_reference")
            source_fields_used.append("message")

        if self._contains_any(text, self.PRICE_TRACK_TERMS):
            should_bypass_cache = True
            reason_codes.append("price_or_track_question")
            source_fields_used.append("message")

        observed_current = current_retrieval_bypass_cache
        if observed_current is None and isinstance(context.get("bypass_cache"), bool):
            observed_current = context.get("bypass_cache")
            source_fields_used.append("context_plan.bypass_cache")

        would_change = False
        if isinstance(observed_current, bool) and observed_current != should_bypass_cache:
            would_change = True

        return {
            "should_bypass_cache": bool(should_bypass_cache),
            "allow_final_answer_cache": False,
            "reason_codes": list(dict.fromkeys(reason_codes)),
            "source_fields_used": list(dict.fromkeys(source_fields_used)),
            "current_retrieval_bypass_cache": observed_current if isinstance(observed_current, bool) else None,
            "would_change_current_behavior": bool(would_change),
        }

    @staticmethod
    def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
        raw = str(text or "")
        return any(term in raw for term in terms)

    @staticmethod
    def _dig_bool(payload: dict, key: str, sub_key: str) -> bool:
        if isinstance(payload.get(key), dict):
            value = payload[key].get(sub_key)
            return bool(value) if isinstance(value, bool) else False
        return False

    @staticmethod
    def _dig_str(payload: dict, key: str, sub_key: str) -> str:
        if isinstance(payload.get(key), dict):
            return str(payload[key].get(sub_key) or "").strip()
        return ""
