from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from support_app.schemas import ChatRequest, ChatResponse
from support_app.services.cache_policy_metadata_service import CachePolicyMetadataService
from support_app.services.conversation_state_store import ConversationStateStore
from support_app.services.intent_service import IntentService
from support_app.services.post_rule_check_service import PostRuleCheckService
from support_app.services.risk_policy_service import RiskPolicyService
from support_app.services.understand_plan_adapter import UnderstandPlanAdapter


@dataclass
class AnswerContext:
    query: str
    session_id: str
    history: list[dict[str, Any]]
    customer_memory: dict[str, Any] | None
    model_config: dict[str, Any]
    debug: bool
    request_id: str
    intent_plan: dict[str, Any] = field(default_factory=dict)
    risk_precheck: dict[str, Any] = field(default_factory=dict)
    risk_precheck_error: str = ""


@dataclass
class ToolResult:
    name: str
    ok: bool = True
    route: str = ""
    confidence: float = 0.0
    missing_fields: list[str] = field(default_factory=list)
    quality_flags: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class MemoryTool:
    name = "MemoryTool"

    def summarize(self, response: ChatResponse) -> ToolResult:
        metadata = response.metadata or {}
        context_plan = metadata.get("context_plan") if isinstance(metadata.get("context_plan"), dict) else {}
        used = bool(response.memory) or bool(context_plan.get("used_history"))
        return ToolResult(
            name=self.name,
            ok=True,
            route=response.route,
            confidence=1.0 if used else 0.0,
            data={
                "used_memory": bool(response.memory),
                "used_history": bool(context_plan.get("used_history")),
                "history_turn_count": context_plan.get("history_turn_count", 0),
            },
        )


class KnowledgeTool:
    name = "KnowledgeTool"

    def summarize(self, response: ChatResponse) -> ToolResult:
        used = response.route in {"faq", "doc", "learned_correction"}
        flags: list[dict[str, Any]] = []
        if response.route == "fallback" and not response.sources:
            flags.append({
                "type": "knowledge_not_found",
                "label": "知识未命中",
                "severity": "warning",
            })
        return ToolResult(
            name=self.name,
            ok=True,
            route=response.route,
            confidence=max(float(response.faq_top_score or 0), float(response.doc_top_score or 0)),
            quality_flags=flags,
            data={"used": used, "source_count": len(response.sources)},
        )


class QuoteIntentDetector:
    name = "QuoteIntentDetector"
    QUOTE_WORDS = ("报价", "价格", "多少钱", "费用", "预算", "优惠", "采购", "轨道")

    def detect(self, query: str, response: ChatResponse, intent_plan: dict[str, Any] | None = None) -> ToolResult:
        intent_plan = intent_plan or {}
        has_intent_plan = bool(intent_plan.get("intent"))
        quote_like = bool(intent_plan.get("needs_quote_tool")) if has_intent_plan else any(word in query for word in self.QUOTE_WORDS)
        missing_fields: list[str] = []
        if quote_like and not any(token in query.upper() for token in ("GRA", "MINI", "AIR", "EXT", "PRO", "U-MOCO", "UMOCO")):
            missing_fields.append("产品型号")
        if quote_like and "轨道" in query and "米" not in query:
            missing_fields.append("轨道长度")
        return ToolResult(
            name=self.name,
            ok=True,
            route="quote_draft" if quote_like else response.route,
            confidence=float(intent_plan.get("confidence") or 0.86) if quote_like else 0.0,
            missing_fields=missing_fields,
            data={"quote_like": quote_like, "intent": intent_plan.get("intent", "")},
        )


class QuoteTool:
    name = "QuoteTool"

    def summarize(self, response: ChatResponse) -> ToolResult:
        metadata = response.metadata or {}
        draft = metadata.get("quote_draft") if isinstance(metadata.get("quote_draft"), dict) else {}
        used = response.route == "quote_draft"
        flags: list[dict[str, Any]] = []
        if used:
            flags.append({
                "type": "quote_requires_review",
                "label": "报价需人工复核",
                "severity": "warning",
            })
        return ToolResult(
            name=self.name,
            ok=True,
            route=response.route,
            confidence=1.0 if used else 0.0,
            quality_flags=flags,
            next_actions=[{
                "type": "review_quote",
                "label": "复核报价规则和交付口径",
                "target": "quote_rules",
            }] if used else [],
            data={
                "used": used,
                "quote_item_count": len(draft.get("quote_items", []) or []),
                "missing_fields": (draft.get("configuration_quote") or {}).get("missing_questions", []),
            },
        )


class SafetyTool:
    name = "SafetyTool"
    COMMITMENT_WORDS = ("一定", "保证", "最低价", "三天内", "直接签", "肯定够用", "免费", "库存")

    def review(self, query: str, response: ChatResponse) -> ToolResult:
        text = f"{query}\n{response.answer}"
        flags: list[dict[str, Any]] = []
        if response.need_human:
            flags.append({
                "type": "need_human_review",
                "label": "需要人工确认",
                "severity": "warning",
            })
        if any(word in text for word in self.COMMITMENT_WORDS):
            flags.append({
                "type": "commercial_commitment_risk",
                "label": "商业承诺风险",
                "severity": "high",
            })
        return ToolResult(
            name=self.name,
            ok=True,
            route=response.route,
            confidence=1.0,
            quality_flags=flags,
            next_actions=[{
                "type": "manual_review",
                "label": "人工确认价格、交期、合同或服务范围",
                "target": "human",
            }] if response.need_human else [],
        )


class AnswerPipeline:
    def __init__(
        self,
        legacy_chat_service: Any,
        risk_policy_service: RiskPolicyService | None = None,
        post_rule_check_service: PostRuleCheckService | None = None,
        conversation_state_store: ConversationStateStore | None = None,
        understand_plan_adapter: UnderstandPlanAdapter | None = None,
        cache_policy_metadata_service: CachePolicyMetadataService | None = None,
    ):
        self.legacy_chat_service = legacy_chat_service
        self.intent_service = IntentService(getattr(legacy_chat_service, "ollama", None))
        legacy_risk = getattr(legacy_chat_service, "risk_policy_service", None)
        self.risk_policy_service = risk_policy_service or legacy_risk or RiskPolicyService()
        legacy_post_rule_check = getattr(legacy_chat_service, "post_rule_check_service", None)
        self.post_rule_check_service = post_rule_check_service or legacy_post_rule_check or PostRuleCheckService()
        legacy_state_store = getattr(legacy_chat_service, "conversation_state_store", None)
        self.conversation_state_store = conversation_state_store or legacy_state_store or ConversationStateStore()
        legacy_understand_adapter = getattr(legacy_chat_service, "understand_plan_adapter", None)
        self.understand_plan_adapter = understand_plan_adapter or legacy_understand_adapter or UnderstandPlanAdapter()
        legacy_cache_policy_metadata = getattr(legacy_chat_service, "cache_policy_metadata_service", None)
        self.cache_policy_metadata_service = (
            cache_policy_metadata_service or legacy_cache_policy_metadata or CachePolicyMetadataService()
        )
        self.memory_tool = MemoryTool()
        self.knowledge_tool = KnowledgeTool()
        self.quote_intent_detector = QuoteIntentDetector()
        self.quote_tool = QuoteTool()
        self.safety_tool = SafetyTool()

    def answer(self, request: ChatRequest) -> ChatResponse:
        context = self._build_context(request)
        try:
            context.risk_precheck = self.risk_policy_service.precheck(request.message, state=None)
        except Exception as exc:
            context.risk_precheck_error = f"{type(exc).__name__}: {exc}"
            context.risk_precheck = RiskPolicyService().precheck(request.message, state=None)
        intent_context = self._intent_context(request)
        context.history = intent_context.get("history", [])
        intent_result = self.intent_service.classify(request.message, intent_context)
        context.intent_plan = intent_result.to_metadata()
        request_metadata = {
            **(request.metadata or {}),
            "request_id": context.request_id,
            "risk_precheck": context.risk_precheck,
            **({"risk_precheck_error": context.risk_precheck_error} if context.risk_precheck_error else {}),
            "intent_plan": context.intent_plan,
            "intent_confidence": context.intent_plan["confidence"],
            "intent_reason": context.intent_plan["reason"],
            "scenario_terms": context.intent_plan["scenario_terms"],
            "action_terms": context.intent_plan["action_terms"],
            "product_anchors": context.intent_plan["product_anchors"],
        }
        try:
            if not isinstance(request_metadata.get("understand_plan"), dict):
                provisional_state = request_metadata.get("conversation_state_before") if isinstance(request_metadata.get("conversation_state_before"), dict) else {}
                request_metadata["understand_plan"] = self.understand_plan_adapter.build(
                    message=context.query,
                    intent_plan=request_metadata.get("intent_plan"),
                    sales_plan=request_metadata.get("sales_plan"),
                    context_plan=request_metadata.get("context_plan"),
                    conversation_state=provisional_state,
                    risk_plan=request_metadata.get("risk_plan") or request_metadata.get("risk_precheck"),
                )
            if not isinstance(request_metadata.get("cache_policy_metadata"), dict):
                context_plan = request_metadata.get("context_plan") if isinstance(request_metadata.get("context_plan"), dict) else {}
                current_bypass = context_plan.get("bypass_cache") if isinstance(context_plan.get("bypass_cache"), bool) else None
                request_metadata["cache_policy_metadata"] = self.cache_policy_metadata_service.build(
                    message=context.query,
                    understand_plan=request_metadata.get("understand_plan"),
                    context_plan=context_plan,
                    risk_plan=request_metadata.get("risk_plan"),
                    risk_precheck=request_metadata.get("risk_precheck"),
                    conversation_state_after=request_metadata.get("conversation_state_after")
                    if isinstance(request_metadata.get("conversation_state_after"), dict)
                    else request_metadata.get("conversation_state_before"),
                    current_retrieval_bypass_cache=current_bypass,
                )
        except Exception as exc:
            request_metadata["cache_policy_metadata_error"] = f"{type(exc).__name__}: {exc}"
        request.metadata = request_metadata
        response = self.legacy_chat_service._answer_current(request)
        self._enrich_response(response, context)
        return response

    def _intent_context(self, request: ChatRequest) -> dict[str, Any]:
        history_service = getattr(self.legacy_chat_service, "conversation_history_service", None)
        history = []
        product_anchors = []
        if history_service and not self._is_transient_test_request(request):
            try:
                history = history_service.recent_for_request(request)
                product_anchors = history_service.product_anchors(history)
            except Exception:
                history = []
                product_anchors = []
        last = history[-1] if history else {}
        last_message = str(last.get("message", "") or "")
        last_answer = str(last.get("answer", "") or "")
        return {
            "conversation_id": request.conversation_id or "",
            "channel": request.channel,
            "user_id": request.user_id or "",
            "metadata": request.metadata or {},
            "history": history,
            "last_route": str(last.get("route", "") or ""),
            "last_message": last_message,
            "last_answer": last_answer,
            "history_product_anchors": product_anchors,
            "history_anchor_summary": self._history_anchor_summary(last_message, last_answer, product_anchors),
        }

    @staticmethod
    def _is_transient_test_request(request: ChatRequest) -> bool:
        metadata = request.metadata or {}
        if bool(metadata.get("model_compare")):
            return True
        if bool(metadata.get("transient_test")):
            return True
        if bool(metadata.get("shadow")):
            return True
        compare_role = str(
            metadata.get("compare_role")
            or metadata.get("model_compare_role")
            or ""
        ).strip().lower()
        return compare_role in {"primary", "shadow"}

    @staticmethod
    def _history_anchor_summary(last_message: str, last_answer: str, product_anchors: list[str]) -> str:
        bits = []
        if product_anchors:
            bits.append("产品锚点：" + "、".join(product_anchors[:6]))
        if last_message:
            bits.append("上一问：" + last_message[:80])
        if last_answer:
            bits.append("上一答：" + last_answer.replace("\n", " ")[:120])
        return "；".join(bits)

    def _build_context(self, request: ChatRequest) -> AnswerContext:
        metadata = request.metadata or {}
        override = metadata.get("model_override") if isinstance(metadata.get("model_override"), dict) else {}
        model_config = {
            "chat_model": override.get("chat_model", ""),
            "embed_model": override.get("embed_model", ""),
            "override_used": bool(override),
        }
        return AnswerContext(
            query=request.message.strip(),
            session_id=request.conversation_id or "",
            history=[],
            customer_memory=None,
            model_config=model_config,
            debug=bool(metadata.get("test_page") or metadata.get("debug")),
            request_id=str(metadata.get("request_id") or uuid.uuid4()),
        )

    def _enrich_response(self, response: ChatResponse, context: AnswerContext) -> None:
        metadata = dict(response.metadata or {})
        intent_plan = context.intent_plan or metadata.get("intent_plan") or {}
        post_rule_check = metadata.get("post_rule_check")
        if not isinstance(post_rule_check, dict):
            try:
                quote_readiness = metadata.get("quote_readiness")
                if not quote_readiness and isinstance(metadata.get("sales_plan"), dict):
                    quote_readiness = metadata["sales_plan"].get("quote_readiness")
                post_rule_check = self.post_rule_check_service.check(
                    route=response.route,
                    answer=response.answer,
                    risk_plan=metadata.get("risk_plan") or metadata.get("risk_precheck"),
                    quote_readiness=quote_readiness,
                    metadata=metadata,
                )
                metadata["post_rule_check"] = post_rule_check if isinstance(post_rule_check, dict) else {}
            except Exception as exc:
                metadata["post_rule_check_error"] = f"{type(exc).__name__}: {exc}"
        metadata["post_rule_enforce_applied"] = bool(metadata.get("post_rule_enforce_applied", False))
        tool_results = [
            self.memory_tool.summarize(response),
            self.quote_intent_detector.detect(context.query, response, intent_plan),
            self.knowledge_tool.summarize(response),
            self.quote_tool.summarize(response),
            self.safety_tool.review(context.query, response),
        ]
        used_tools = [
            item.name
            for item in tool_results
            if item.confidence > 0 or item.quality_flags or item.next_actions or item.data.get("used")
        ]
        quality_flag_details = self._dedupe_dicts([flag for item in tool_results for flag in item.quality_flags], "type")
        next_action_details = self._dedupe_dicts([action for item in tool_results for action in item.next_actions], "type")
        quality_flags = [str(item.get("type") or item.get("label") or "") for item in quality_flag_details if item]
        next_actions = [str(item.get("type") or item.get("label") or "") for item in next_action_details if item]
        tool_decision_trace = [
            {
                "step": item.name,
                "ok": item.ok,
                "route": item.route,
                "confidence": item.confidence,
                "missing_fields": item.missing_fields,
            }
            for item in tool_results
        ]
        sales_trace = metadata.get("sales_decision_trace") if isinstance(metadata.get("sales_decision_trace"), list) else []
        decision_trace = [*sales_trace, *tool_decision_trace]
        metadata.update({
            "request_id": context.request_id,
            "risk_precheck": context.risk_precheck,
            **({"risk_precheck_error": context.risk_precheck_error} if context.risk_precheck_error else {}),
            "intent_plan": intent_plan,
            "intent_confidence": intent_plan.get("confidence", metadata.get("intent_confidence", 0)),
            "intent_reason": intent_plan.get("reason", metadata.get("intent_reason", "")),
            "scenario_terms": intent_plan.get("scenario_terms", metadata.get("scenario_terms", [])),
            "action_terms": intent_plan.get("action_terms", metadata.get("action_terms", [])),
            "product_anchors": intent_plan.get("product_anchors", metadata.get("product_anchors", [])),
            "decision_trace": decision_trace,
            "tool_decision_trace": tool_decision_trace,
            "used_tools": used_tools,
            "quality_flags": quality_flags,
            "quality_flag_details": quality_flag_details,
            "next_actions": next_actions,
            "next_action_details": next_action_details,
            "need_human_review": bool(response.need_human),
        })
        try:
            conversation_state = metadata.get("conversation_state_after")
            if not isinstance(conversation_state, dict):
                conversation_state = metadata.get("conversation_state_before") if isinstance(metadata.get("conversation_state_before"), dict) else {}
            understand_plan = self.understand_plan_adapter.build(
                message=context.query,
                intent_plan=metadata.get("intent_plan"),
                sales_plan=metadata.get("sales_plan"),
                context_plan=metadata.get("context_plan"),
                conversation_state=conversation_state,
                risk_plan=metadata.get("risk_plan") or metadata.get("risk_precheck"),
            )
            if isinstance(understand_plan, dict):
                metadata["understand_plan"] = understand_plan
        except Exception as exc:
            metadata["understand_plan_error"] = f"{type(exc).__name__}: {exc}"
        try:
            context_plan = metadata.get("context_plan") if isinstance(metadata.get("context_plan"), dict) else {}
            current_retrieval_bypass_cache = None
            if isinstance(metadata.get("current_retrieval_bypass_cache"), bool):
                current_retrieval_bypass_cache = metadata.get("current_retrieval_bypass_cache")
            elif isinstance(context_plan.get("bypass_cache"), bool):
                current_retrieval_bypass_cache = context_plan.get("bypass_cache")
            cache_policy_metadata = self.cache_policy_metadata_service.build(
                message=context.query,
                understand_plan=metadata.get("understand_plan"),
                context_plan=context_plan,
                risk_plan=metadata.get("risk_plan"),
                risk_precheck=metadata.get("risk_precheck"),
                conversation_state_after=metadata.get("conversation_state_after"),
                current_retrieval_bypass_cache=current_retrieval_bypass_cache,
            )
            if isinstance(cache_policy_metadata, dict):
                metadata["cache_policy_metadata"] = cache_policy_metadata
        except Exception as exc:
            metadata["cache_policy_metadata_error"] = f"{type(exc).__name__}: {exc}"
        response.metadata = metadata

    @staticmethod
    def _dedupe_dicts(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        seen = set()
        rows = []
        for item in items:
            value = str(item.get(key, "") or "")
            if value and value in seen:
                continue
            if value:
                seen.add(value)
            rows.append(item)
        return rows
