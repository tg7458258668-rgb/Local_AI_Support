import hashlib
import json
import time
import uuid
from typing import Literal

from support_app.repositories.rule_repository import RuleRepository
from support_app.schemas import ChatRequest, ChatResponse, SourceItem, TimingInfo
from support_app.services.audit_service import AuditService
from support_app.services.answer_pipeline import AnswerPipeline
from support_app.services.behavior_config_service import BehaviorConfigService
from support_app.services.conversation_history_service import ConversationHistoryService
from support_app.services.customer_memory_service import CustomerMemoryService
from support_app.services.knowledge_gap_service import KnowledgeGapService
from support_app.services.learning_service import LearningService
from support_app.services.ollama_client import OllamaClient
from support_app.services.prompt_builder import build_docs_prompt, build_faq_prompt, build_handoff_answer
from support_app.services.quote_service import QuoteService
from support_app.services.retrieval_service import RetrievalCandidate, RetrievalService
from support_app.services.sales_strategy_service import SalesStrategyService
from support_app.settings import Settings


class ChatService:
    def __init__(
        self,
        settings: Settings,
        ollama: OllamaClient,
        retrieval_service: RetrievalService,
        rule_repo: RuleRepository,
        memory_service: CustomerMemoryService,
        audit_service: AuditService,
        quote_service: QuoteService,
        learning_service: LearningService,
        knowledge_gap_service: KnowledgeGapService,
        behavior_config_service: BehaviorConfigService,
        conversation_history_service: ConversationHistoryService | None = None,
    ):
        self.settings = settings
        self.ollama = ollama
        self.retrieval_service = retrieval_service
        self.rule_repo = rule_repo
        self.memory_service = memory_service
        self.audit_service = audit_service
        self.quote_service = quote_service
        self.learning_service = learning_service
        self.knowledge_gap_service = knowledge_gap_service
        self.behavior_config_service = behavior_config_service
        self.conversation_history_service = conversation_history_service
        self.sales_strategy_service = SalesStrategyService(self.behavior_config_service.sales_strategy_policy())

    def answer(self, request: ChatRequest) -> ChatResponse:
        return AnswerPipeline(self).answer(request)

    def _answer_current(self, request: ChatRequest) -> ChatResponse:
        start = time.perf_counter()
        timings = TimingInfo()
        user_query = request.message.strip()
        request_id = str((request.metadata or {}).get("request_id") or uuid.uuid4())
        transient_request = self._is_transient_test_request(request)
        model_runtime = self._resolve_chat_model_runtime(request)
        chat_model_name = str(model_runtime.get("actual_chat_model") or self.ollama.current_chat_model())

        faq_hits = []
        doc_hits = []
        faq_candidates: list[RetrievalCandidate] = []
        doc_candidates: list[RetrievalCandidate] = []
        matched_rule = None
        memory = None
        faq_top_score = 0.0
        doc_top_score = 0.0
        base_metadata = self._base_metadata(request, model_runtime=model_runtime, transient_request=transient_request)
        self._attach_state_before(request, base_metadata)
        risk_plan = self._risk_precheck(request, base_metadata)
        if self._is_blocked_risk_handoff(risk_plan):
            timings.total_ms = self._elapsed(start)
            metadata = dict(base_metadata)
            metadata["risk_precheck"] = risk_plan
            metadata["risk_plan"] = risk_plan
            self._append_decision_trace(metadata, "risk_blocked_handoff")
            metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                user_query,
                "handoff",
                0,
                0,
                memory,
                metadata,
                True,
            )
            response = ChatResponse(
                answer=str(risk_plan.get("safe_answer") or "这个问题涉及商业承诺，需要人工同事进一步确认。"),
                route="handoff",
                need_human=True,
                hint="本回答建议人工进一步确认",
                matched_rule="RiskPolicyService",
                faq_top_score=0,
                doc_top_score=0,
                sources=[],
                retrieval_debug=[],
                memory=memory,
                timings=timings,
                channel=request.channel,
                conversation_id=request.conversation_id,
                user_id=request.user_id,
                metadata=metadata,
            )
            self._audit(request_id, request, response)
            return response

        try:
            def _persist_memory(answer_text: str, route_name: str) -> dict | None:
                nonlocal memory
                if transient_request:
                    return memory
                t0 = time.perf_counter()
                memory = self.memory_service.update_from_turn(request, answer_text, route_name)
                timings.memory_ms += self._elapsed(t0)
                return memory

            if transient_request:
                memory = None
                history = []
            else:
                t = time.perf_counter()
                memory = self.memory_service.load_for_request(request)
                timings.memory_ms = self._elapsed(t)

                t = time.perf_counter()
                history = self.conversation_history_service.recent_for_request(request) if self.conversation_history_service else []
                timings.history_ms = self._elapsed(t)

            t = time.perf_counter()
            context_plan = self._build_context_plan(user_query, request, memory, history)
            timings.context_plan_ms = self._elapsed(t)
            sales_plan = self.sales_strategy_service.plan(user_query, self._intent_plan(request), context_plan, memory, history)
            context_plan = self._context_plan_with_sales(request, context_plan, sales_plan)
            memory_for_context = self._memory_with_context(memory, context_plan)
            context_blocks = [
                self.memory_service.render_prompt_block(memory_for_context),
                self.conversation_history_service.prompt_block(history) if self.conversation_history_service else "",
            ]
            memory_context = "\n\n".join(block for block in context_blocks if block)
            base_metadata.update({
                "context_plan": self._public_context_plan(context_plan),
                "conversation_context": self.conversation_history_service.debug_summary(history) if self.conversation_history_service else [],
            })
            self._apply_sales_metadata(base_metadata, sales_plan)
            self._apply_cache_policy_enforce(request, context_plan, base_metadata)

            identity_answer = self._identity_answer(user_query)
            if identity_answer:
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["identity_intent"] = True
                metadata["context_plan"]["fast_path"] = "identity"
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "identity",
                    0,
                    0,
                    memory,
                    metadata,
                    False,
                )
                response = ChatResponse(
                    answer=identity_answer,
                    route="identity",
                    need_human=False,
                    hint="身份和寒暄问题已直接回答",
                    matched_rule=None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            memory_recall_answer = self._memory_recall_answer(user_query, memory)
            if memory_recall_answer:
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "memory_recall",
                    0,
                    0,
                    memory,
                    metadata,
                    False,
                )
                response = ChatResponse(
                    answer=memory_recall_answer,
                    route="memory_recall",
                    need_human=False,
                    hint="已根据客户记忆回答",
                    matched_rule=None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            learning = self.learning_service.maybe_learn_from_request(request)
            if learning.get("detected"):
                if learning.get("saved"):
                    memory = _persist_memory(learning["message"], "learned_correction")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["learning"] = learning
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    request.message,
                    "learned_correction",
                    0,
                    0,
                    memory,
                    metadata,
                    False,
                )
                response = ChatResponse(
                    answer=learning.get("message") or "我还需要你补充正确说法或适用范围，才能把这条修正写入学习库。",
                    route="learned_correction",
                    need_human=False,
                    hint="测试页纠错学习已处理" if learning.get("saved") else "纠错内容不足，暂未写入学习库",
                    matched_rule=None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            t = time.perf_counter()
            matched_rule = self.rule_repo.match(user_query)
            timings.rule_match_ms = self._elapsed(t)
            if self._requires_handoff(user_query) or self._intent_is(request, "handoff") or sales_plan.sales_stage == "handoff":
                answer = build_handoff_answer(user_query, matched_rule)
                memory = _persist_memory(answer, "handoff")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "handoff",
                    0,
                    0,
                    memory,
                    metadata,
                    True,
                )
                response = ChatResponse(
                    answer=answer,
                    route="handoff",
                    need_human=True,
                    hint="本回答建议人工进一步确认",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response
            if (
                matched_rule
                and str(matched_rule.get("action", "")) in ("manual_required", "block_commitment")
                and not self._is_reference_quote_lookup(user_query, matched_rule)
            ):
                answer = build_handoff_answer(user_query, matched_rule)
                memory = _persist_memory(answer, "handoff")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "handoff",
                    0,
                    0,
                    memory,
                    metadata,
                    True,
                )
                response = ChatResponse(
                    answer=answer,
                    route="handoff",
                    need_human=True,
                    hint="本回答建议人工进一步确认",
                    matched_rule=matched_rule["rule_name"],
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            if (
                context_plan["contextual_query"]
                and not context_plan["anchors"]
                and not self._has_explicit_product_anchor(user_query)
                and not sales_plan.should_direct_answer
            ):
                answer = "我需要先确认你说的是哪一款或上一轮哪个方案。你可以补一句型号，比如 GRA、MINI、AIR、EXT 或 PRO。"
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "fallback",
                    0,
                    0,
                    memory,
                    metadata,
                    False,
                )
                response = ChatResponse(
                    answer=answer,
                    route="fallback",
                    need_human=False,
                    hint="追问缺少可用上下文，已要求确认型号",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            if self._should_use_sales_quote(request, user_query, sales_plan, context_plan):
                quote_request = self._request_for_intent(request)
                t = time.perf_counter()
                quote_result = self.quote_service.draft(quote_request, memory_for_context, [])
                timings.route_decision_ms = self._elapsed(t)
                if sales_plan.sales_stage == "recommend" and not sales_plan.should_quote and self._intent_is(request, "quote_price"):
                    quote_result["answer"] = self._render_quote_not_ready_answer(sales_plan, quote_result.get("draft", {}))
                memory = _persist_memory(quote_result["answer"], "quote_draft")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["quote_draft"] = quote_result["draft"]
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "quote_draft",
                    0,
                    0,
                    memory,
                    metadata,
                    bool(sales_plan.should_quote or self._intent_is(request, "quote_price")),
                )
                response = ChatResponse(
                    answer=quote_result["answer"],
                    route="quote_draft",
                    need_human=bool(sales_plan.should_quote or self._intent_is(request, "quote_price")),
                    hint="已按销售策略生成参考方向，正式价格和交付安排需人工确认" if not sales_plan.should_quote else "已按结构化报价规则库生成推荐，正式价格和交付安排需人工确认",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=self._quote_sources(quote_result["draft"]),
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            if self._intent_is(request, "clarify"):
                answer = self._intent_clarify_answer(request)
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "fallback",
                    0,
                    0,
                    memory,
                    metadata,
                    False,
                )
                response = ChatResponse(
                    answer=answer,
                    route="fallback",
                    need_human=False,
                    hint="已识别到场景或产品词，但缺少明确动作，先澄清需求",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=[],
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            if self._intent_needs_quote(request, user_query) and not sales_plan.should_direct_answer:
                quote_request = self._request_for_intent(request)
                t = time.perf_counter()
                quote_result = self.quote_service.draft(quote_request, memory_for_context, [])
                timings.route_decision_ms = self._elapsed(t)
                if sales_plan.sales_stage == "recommend" and not sales_plan.should_quote and self._intent_is(request, "quote_price"):
                    quote_result["answer"] = self._render_quote_not_ready_answer(sales_plan, quote_result.get("draft", {}))
                memory = _persist_memory(quote_result["answer"], "quote_draft")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["quote_draft"] = quote_result["draft"]
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "quote_draft",
                    0,
                    0,
                    memory,
                    metadata,
                    True,
                )
                response = ChatResponse(
                    answer=quote_result["answer"],
                    route="quote_draft",
                    need_human=bool(sales_plan.should_quote or self._intent_is(request, "quote_price")),
                    hint="已按销售策略生成参考方向，正式价格和交付安排需人工确认" if not sales_plan.should_quote else "已按结构化报价规则库生成推荐，正式价格和交付安排需人工确认",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=0,
                    doc_top_score=0,
                    sources=self._quote_sources(quote_result["draft"]),
                    retrieval_debug=[],
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            t = time.perf_counter()
            retrieval = self.retrieval_service.retrieve(
                context_plan["effective_query"],
                request.channel,
                request.user_id,
                cache_context=context_plan["cache_context"],
                bypass_cache=context_plan["bypass_cache"],
            )
            retrieval_ms = self._elapsed(t)
            faq_hits = retrieval.faq_hits
            doc_hits = retrieval.doc_hits
            faq_candidates = retrieval.faq_candidates
            doc_candidates = retrieval.doc_candidates
            faq_top_score = retrieval.faq_top_score
            doc_top_score = retrieval.doc_top_score
            timings.faq_retrieval_ms = retrieval_ms
            timings.doc_retrieval_ms = 0.0
            timings.retrieval_cache_hit = retrieval.cache_hit

            learned_candidate = self._top_learned_candidate(doc_candidates)
            if (
                learned_candidate
                and learned_candidate.adjusted_score >= self.settings.doc_score_threshold
                and not (faq_hits and faq_top_score >= self.settings.faq_direct_answer_threshold)
                and context_plan["direct_answer_allowed"]
            ):
                answer = self._direct_learned_answer(learned_candidate)
                memory = _persist_memory(answer, "learned_correction")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "learned_correction",
                    faq_top_score,
                    doc_top_score,
                    memory,
                    metadata,
                    False,
                )
                response = ChatResponse(
                    answer=answer,
                    route="learned_correction",
                    need_human=False,
                    hint="已优先使用纠错学习库中的口径",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=faq_top_score,
                    doc_top_score=doc_top_score,
                    sources=self._format_sources([learned_candidate], "doc"),
                    retrieval_debug=self._debug_candidates(faq_candidates, doc_candidates),
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            if self._intent_needs_quote(request, user_query) and not sales_plan.should_direct_answer:
                quote_request = self._request_for_intent(request)
                t = time.perf_counter()
                quote_result = self.quote_service.draft(quote_request, memory_for_context, doc_candidates)
                timings.route_decision_ms = self._elapsed(t)
                if sales_plan.sales_stage == "recommend" and not sales_plan.should_quote and self._intent_is(request, "quote_price"):
                    quote_result["answer"] = self._render_quote_not_ready_answer(sales_plan, quote_result.get("draft", {}))
                sources = self._format_sources(doc_candidates, "doc")
                memory = _persist_memory(quote_result["answer"], "quote_draft")
                timings.total_ms = self._elapsed(start)
                metadata = dict(base_metadata)
                metadata["quote_draft"] = quote_result["draft"]
                metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                    user_query,
                    "quote_draft",
                    faq_top_score,
                    doc_top_score,
                    memory,
                    metadata,
                    True,
                )
                response = ChatResponse(
                    answer=quote_result["answer"],
                    route="quote_draft",
                    need_human=bool(sales_plan.should_quote or self._intent_is(request, "quote_price")),
                    hint="已按销售策略生成参考方向，正式价格、优惠、交付和合同需人工确认" if not sales_plan.should_quote else "这是报价草案，正式价格、优惠、交付和合同需人工确认",
                    matched_rule=matched_rule["rule_name"] if matched_rule else None,
                    faq_top_score=faq_top_score,
                    doc_top_score=doc_top_score,
                    sources=sources,
                    retrieval_debug=self._debug_candidates(faq_candidates, doc_candidates),
                    memory=memory,
                    timings=timings,
                    channel=request.channel,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id,
                    metadata=metadata,
                )
                self._audit(request_id, request, response)
                return response

            t = time.perf_counter()
            route, selected_hits, source_type, prompt, answer, need_human, hint = self._route(
                user_query=user_query,
                matched_rule=matched_rule,
                faq_hits=faq_hits,
                doc_hits=doc_hits,
                faq_top_score=faq_top_score,
                doc_top_score=doc_top_score,
                memory_context=memory_context,
                context_plan=context_plan,
            )
            timings.route_decision_ms = self._elapsed(t)

            if route == "doc" and doc_candidates and self._is_learned_candidate(doc_candidates[0]):
                route = "learned_correction"
                answer = self._direct_learned_answer(doc_candidates[0])
                prompt = None

            sources: list[SourceItem] = []
            if route in ("faq", "doc") and prompt:
                t = time.perf_counter()
                answer = self.ollama.generate(prompt, model=chat_model_name)
                timings.answer_generation_ms = self._elapsed(t)
                self._mark_generation_metadata(base_metadata, timings.answer_generation_ms)

                t = time.perf_counter()
                candidates = faq_candidates if source_type == "faq" else doc_candidates
                sources = self._format_sources(candidates, source_type)
                timings.source_format_ms = self._elapsed(t)
            elif route == "faq":
                sources = self._format_sources(faq_candidates, "faq")
            elif route == "doc":
                sources = self._format_sources(doc_candidates, "doc")
            elif route == "learned_correction":
                sources = self._format_sources(doc_candidates, "doc")

            memory = _persist_memory(answer, route)

            timings.total_ms = self._elapsed(start)
            metadata = dict(base_metadata)
            metadata["knowledge_gaps"] = self.knowledge_gap_service.analyze(
                user_query,
                route,
                faq_top_score,
                doc_top_score,
                memory,
                metadata,
                need_human,
            )
            answer = self._answer_with_active_gap_prompt(answer, route, metadata)
            response = ChatResponse(
                answer=answer,
                route=route,
                need_human=need_human,
                hint=hint,
                matched_rule=matched_rule["rule_name"] if matched_rule else None,
                faq_top_score=faq_top_score,
                doc_top_score=doc_top_score,
                sources=sources,
                retrieval_debug=self._debug_candidates(faq_candidates, doc_candidates),
                memory=memory,
                timings=timings,
                channel=request.channel,
                conversation_id=request.conversation_id,
                user_id=request.user_id,
                metadata=metadata,
            )
            self._audit(request_id, request, response)
            return response
        except Exception as exc:
            timings.total_ms = self._elapsed(start)
            response = ChatResponse(
                answer=f"系统报错：{type(exc).__name__}: {exc}",
                route="error",
                need_human=bool(matched_rule),
                hint="本回答建议人工进一步确认" if matched_rule else "系统异常",
                matched_rule=matched_rule["rule_name"] if matched_rule else None,
                faq_top_score=faq_top_score,
                doc_top_score=doc_top_score,
                retrieval_debug=self._debug_candidates(faq_candidates, doc_candidates),
                memory=memory,
                timings=timings,
                channel=request.channel,
                conversation_id=request.conversation_id,
                user_id=request.user_id,
                metadata=base_metadata,
            )
            self._audit(request_id, request, response)
            return response

    def _build_context_plan(self, user_query: str, request: ChatRequest, memory: dict | None, history: list[dict]) -> dict:
        text = str(user_query or "").strip()
        intent_plan = self._intent_plan(request)
        policy = self.behavior_config_service.memory_policy()
        previous_words = policy.get("previous_context_words") or ["上次", "之前", "刚才", "前面", "上一轮", "那个", "这款"]
        contextual_words = list(dict.fromkeys([
            *previous_words,
            *(
                self.behavior_config_service.sales_strategy_policy().get("contextual_followup_words", [])
                if hasattr(self.behavior_config_service, "sales_strategy_policy")
                else []
            ),
            "继续",
            "那",
            "上面",
            "刚刚",
            "它",
            "这个",
            "这种",
            "该款",
            "这套",
            "这个方案",
            "要不要轨道",
            "还有轨道",
        ]))
        has_explicit_anchor = self._has_explicit_product_anchor(text)
        short_price_followup = any(word in text for word in ("多少钱", "价格", "费用", "报价")) and not has_explicit_anchor and len(text) <= 18
        short_history_turn = bool(history) and len(text) <= 28 and not self._intent_is(request, "identity", "handoff", "correction_learning")
        contextual_query = any(word in text for word in contextual_words) or short_price_followup or short_history_turn or bool(intent_plan.get("contextual_followup"))
        history_anchors = self.conversation_history_service.product_anchors(history) if self.conversation_history_service else []
        memory_products = [str(item).strip() for item in (memory or {}).get("products", []) if str(item).strip()]
        intent_anchors = [str(item).strip() for item in intent_plan.get("product_anchors", []) if str(item).strip()] if isinstance(intent_plan.get("product_anchors"), list) else []
        anchors = list(dict.fromkeys([*intent_anchors, *history_anchors, *memory_products]))[:8]
        anchor_text = " ".join(anchors)
        effective_query = str(intent_plan.get("resolved_query") or "").strip() or text
        if contextual_query and anchor_text:
            effective_query = f"{effective_query} 上下文产品:{anchor_text}"
        history_hash = self.conversation_history_service.fingerprint(history) if self.conversation_history_service else ""
        memory_hash = self._memory_fingerprint(memory)
        reason = "独立明确问题，可使用上下文范围内缓存"
        cache_policy = "context_scoped"
        if not request.conversation_id:
            reason = "无会话 ID，本轮没有最近对话上下文"
            cache_policy = "no_history_context"
        if contextual_query:
            reason = intent_plan.get("reason") or "问题引用了最近上下文，已绕过检索缓存"
            cache_policy = "bypass_contextual"
            if not anchors:
                reason = "问题像追问，但最近上下文里没有明确产品锚点"
        return {
            "used_history": bool(history),
            "used_memory": bool(memory),
            "contextual_query": contextual_query,
            "cache_policy": cache_policy,
            "reason": reason,
            "history_turn_count": len(history),
            "history_hash": history_hash,
            "memory_hash": memory_hash,
            "anchors": anchors,
            "effective_query": effective_query,
            "cache_context": f"conversation={request.conversation_id or ''}|history={history_hash}|memory={memory_hash}|contextual={int(contextual_query)}",
            "bypass_cache": contextual_query,
            "direct_answer_allowed": not contextual_query,
        }

    @staticmethod
    def _context_plan_with_sales(request: ChatRequest, context_plan: dict, sales_plan) -> dict:
        intent_plan = ChatService._intent_plan(request)
        plan = dict(context_plan)
        product_anchors = [
            str(item).strip()
            for item in intent_plan.get("product_anchors", [])
            if str(item).strip()
        ] if isinstance(intent_plan.get("product_anchors"), list) else []
        product_anchors.extend(str(item).strip() for item in plan.get("anchors", []) if str(item).strip())
        known = sales_plan.known_needs or {}
        if isinstance(known.get("product_anchors"), list):
            product_anchors.extend(str(item).strip() for item in known["product_anchors"] if str(item).strip())
        product_anchors = list(dict.fromkeys(product_anchors))[:8]
        sales_stage = str(sales_plan.sales_stage or "")
        intent = str(intent_plan.get("intent", "") or "")
        cache_parts = [
            plan.get("cache_context", ""),
            f"intent={intent}",
            f"stage={sales_stage}",
            f"anchors={','.join(product_anchors)}",
        ]
        plan["cache_context"] = "|".join(part for part in cache_parts if part)
        plan["cache_policy"] = plan.get("cache_policy") or "context_scoped"
        plan["sales_stage"] = sales_stage
        plan["intent"] = intent
        plan["product_anchors"] = product_anchors
        if sales_stage in {"recommend", "quote_ready"} and bool(intent_plan.get("contextual_followup")):
            plan["bypass_cache"] = True
            plan["cache_policy"] = "bypass_contextual"
        return plan

    @staticmethod
    def _public_context_plan(context_plan: dict) -> dict:
        return {
            "used_history": bool(context_plan.get("used_history")),
            "used_memory": bool(context_plan.get("used_memory")),
            "contextual_query": bool(context_plan.get("contextual_query")),
            "cache_policy": context_plan.get("cache_policy", ""),
            "reason": context_plan.get("reason", ""),
            "history_turn_count": int(context_plan.get("history_turn_count") or 0),
            "anchors": context_plan.get("anchors", []),
            "product_anchors": context_plan.get("product_anchors", []),
            "sales_stage": context_plan.get("sales_stage", ""),
            "intent": context_plan.get("intent", ""),
            "direct_answer_allowed": bool(context_plan.get("direct_answer_allowed", True)),
        }

    @staticmethod
    def _apply_sales_metadata(metadata: dict, sales_plan) -> None:
        plan = sales_plan.to_metadata()
        metadata["sales_plan"] = plan
        metadata["sales_stage"] = plan["sales_stage"]
        metadata["known_needs"] = plan["known_needs"]
        metadata["missing_fields"] = plan["missing_fields"]
        metadata["route_reason"] = plan["route_reason"]
        metadata["cache_policy"] = (metadata.get("context_plan") or {}).get("cache_policy", "")
        metadata["recommendation_basis"] = plan["recommendation_basis"]
        metadata["quote_readiness"] = plan["quote_readiness"]
        metadata["sales_decision_trace"] = plan["decision_trace"]
        metadata["soft_question"] = plan["soft_question"]
        metadata["recommendation_goal"] = plan["recommendation_goal"]

    @staticmethod
    def _memory_with_context(memory: dict | None, context_plan: dict) -> dict | None:
        anchors = [str(item).strip() for item in context_plan.get("anchors", []) if str(item).strip()]
        if not anchors:
            return memory
        merged = dict(memory or {})
        products = [str(item).strip() for item in merged.get("products", []) if str(item).strip()]
        merged["products"] = list(dict.fromkeys([*products, *anchors]))
        return merged

    @staticmethod
    def _has_explicit_product_anchor(text: str) -> bool:
        upper = str(text or "").upper()
        return any(token in upper for token in ("GRA", "MINI", "AIR", "EXT", "PRO", "U-MOCO", "UMOCO"))

    @staticmethod
    def _memory_fingerprint(memory: dict | None) -> str:
        if not memory:
            return ""
        selected = {
            key: memory.get(key)
            for key in (
                "products",
                "preferences",
                "scenario",
                "budget",
                "project_time",
                "concerns",
                "track_preference",
                "updated_at",
            )
        }
        raw = json.dumps(selected, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _route(
        self,
        user_query: str,
        matched_rule: dict | None,
        faq_hits,
        doc_hits,
        faq_top_score: float,
        doc_top_score: float,
        memory_context: str = "",
        context_plan: dict | None = None,
    ) -> tuple[Literal["faq", "doc", "handoff", "fallback"], list, Literal["faq", "doc"] | None, str | None, str, bool, str]:
        route: Literal["faq", "doc", "handoff", "fallback"] = "fallback"
        selected_hits = []
        source_type: Literal["faq", "doc"] | None = None
        prompt = None
        answer = "我暂时无法根据现有文档确认，建议人工进一步确认。"
        need_human = False
        hint = "当前未触发人工接管提示"
        context_plan = context_plan or {}
        direct_answer_allowed = bool(context_plan.get("direct_answer_allowed", True))

        if matched_rule:
            need_human = True
            hint = "本回答建议人工进一步确认"
            action = str(matched_rule.get("action", ""))
            if self._is_reference_quote_lookup(user_query, matched_rule) and doc_hits and doc_top_score >= self.settings.doc_score_threshold:
                route = "doc"
                selected_hits = doc_hits
                source_type = "doc"
                answer = self._direct_price_answer(user_query, doc_hits[0]) if direct_answer_allowed else ""
                answer = answer or "我暂时无法根据现有文档确认，建议人工进一步确认。"
                prompt = None if answer != "我暂时无法根据现有文档确认，建议人工进一步确认。" else build_docs_prompt(user_query, doc_hits, memory_context)
                hint = "已按知识库报价单回答，正式报价仍建议人工复核"
            elif action in ("manual_required", "block_commitment"):
                route = "handoff"
                answer = build_handoff_answer(user_query, matched_rule)
            elif faq_hits:
                route = "faq"
                selected_hits = faq_hits
                source_type = "faq"
                prompt = build_faq_prompt(user_query, faq_hits, memory_context)
            else:
                route = "handoff"
                answer = build_handoff_answer(user_query, matched_rule)
        elif (
            faq_hits
            and faq_top_score >= self.settings.faq_score_threshold
            and faq_top_score >= doc_top_score + self.settings.faq_doc_margin
        ):
            route = "faq"
            selected_hits = faq_hits
            source_type = "faq"
            if direct_answer_allowed and faq_top_score >= self.settings.faq_direct_answer_threshold:
                answer = self._direct_faq_answer(faq_hits[0])
            else:
                prompt = build_faq_prompt(user_query, faq_hits, memory_context)
        elif doc_hits and doc_top_score >= self.settings.doc_score_threshold:
            route = "doc"
            selected_hits = doc_hits
            source_type = "doc"
            answer = self._direct_price_answer(user_query, doc_hits[0]) if direct_answer_allowed else ""
            answer = answer or "我暂时无法根据现有文档确认，建议人工进一步确认。"
            prompt = None if answer != "我暂时无法根据现有文档确认，建议人工进一步确认。" else build_docs_prompt(user_query, doc_hits, memory_context)
        elif faq_hits and faq_top_score >= self.settings.faq_score_threshold:
            route = "faq"
            selected_hits = faq_hits
            source_type = "faq"
            prompt = build_faq_prompt(user_query, faq_hits, memory_context)

        return route, selected_hits, source_type, prompt, answer, need_human, hint

    @staticmethod
    def _identity_answer(user_query: str) -> str | None:
        text = user_query.strip()
        compact = "".join(text.lower().split())
        normalized = compact.rstrip("？?！!。.")
        identity_exact = {
            "你是谁",
            "你是誰",
            "你叫什么",
            "你叫啥",
            "你是什么",
            "你是干嘛的",
            "你能做什么",
            "你有什么用",
            "你是谁呀",
            "你是谁啊",
            "你是客服吗",
            "你是机器人吗",
            "你是ai吗",
            "你是umoco客服吗",
            "你是u-moco客服吗",
            "你是umoco专业客服吗",
            "你是u-moco专业客服吗",
        }
        greeting_exact = {
            "你好",
            "您好",
            "hi",
            "hello",
            "在吗",
            "在不在",
            "哈喽",
        }
        confirmation_prefixes = (
            "你是u-moco",
            "你是umoco",
            "你就是u-moco",
            "你就是umoco",
        )
        if normalized in identity_exact or normalized in greeting_exact or normalized.startswith(confirmation_prefixes):
            return (
                "你好，我是 U-MOCO 本地 AI 客服，可以帮你解答产品、报价、方案配置、售后政策和知识库资料问题。"
                "如果涉及优惠价、合同、交付时间或特殊定制，我会先给参考建议，并提示人工同事复核。"
            )
        return None

    @staticmethod
    def _format_sources(candidates: list[RetrievalCandidate], source_type: Literal["faq", "doc"] | None) -> list[SourceItem]:
        sources = []
        for item in candidates:
            payload = item.payload or {}
            if source_type == "faq":
                sources.append(SourceItem(
                    type="faq",
                    question=payload.get("question", ""),
                    source=payload.get("source", ""),
                    category=payload.get("category", ""),
                    score=item.score,
                    adjusted_score=item.adjusted_score,
                    reason=item.reason,
                ))
            elif source_type == "doc":
                sources.append(SourceItem(
                    type="doc",
                    doc_name=payload.get("doc_name", ""),
                    section=payload.get("section", ""),
                    source=payload.get("source", ""),
                    category=payload.get("category", ""),
                    score=item.score,
                    adjusted_score=item.adjusted_score,
                    reason=item.reason,
                ))
        return sources

    @staticmethod
    def _direct_faq_answer(hit) -> str:
        payload = hit.payload or {}
        answer = str(payload.get("answer", "")).strip()
        if not answer:
            return "我暂时无法根据现有文档确认，建议人工进一步确认。"
        return answer

    @staticmethod
    def _direct_price_answer(user_query: str, hit) -> str:
        payload = hit.payload or {}
        price_fields = payload.get("price_fields") or {}
        if not isinstance(price_fields, dict) or not price_fields:
            return ""
        asks_for_amount = (
            any(keyword in user_query for keyword in ("价格", "多少钱", "费用", "优惠价", "总价"))
            or "报价多少" in user_query
            or "报价是多少" in user_query
        )
        if not asks_for_amount:
            return ""
        if "优惠" in user_query and price_fields.get("优惠价"):
            label = "优惠价"
            amount = price_fields["优惠价"]
        elif price_fields.get("总价（含税13%）"):
            label = "总价（含税13%）"
            amount = price_fields["总价（含税13%）"]
        elif price_fields.get("总价"):
            label = "总价"
            amount = price_fields["总价"]
        elif price_fields.get("优惠价"):
            label = "优惠价"
            amount = price_fields["优惠价"]
        else:
            return ""
        doc_name = str(payload.get("doc_name") or payload.get("source") or "该报价单")
        clean_name = doc_name.rsplit("_20", 1)[0].replace("_", " ")
        return f"{clean_name} 的{label}是 {amount}。"

    @staticmethod
    def _is_learned_candidate(candidate: RetrievalCandidate) -> bool:
        return candidate.payload.get("doc_type") == "学习知识" or candidate.payload.get("source") == "learned_correction"

    @classmethod
    def _top_learned_candidate(cls, candidates: list[RetrievalCandidate]) -> RetrievalCandidate | None:
        learned = [item for item in candidates if cls._is_learned_candidate(item)]
        return learned[0] if learned else None

    @staticmethod
    def _direct_learned_answer(candidate: RetrievalCandidate) -> str:
        payload = candidate.payload or {}
        text = str(payload.get("text", "") or "")
        fact = ""
        for line in text.splitlines():
            if line.startswith("纠错学习："):
                fact = line.removeprefix("纠错学习：").strip()
                break
        fact = fact or text.strip()
        return fact or "我暂时无法根据现有文档确认，建议人工进一步确认。"

    def _answer_with_active_gap_prompt(self, answer: str, route: str, metadata: dict) -> str:
        if route != "fallback" or not (metadata or {}).get("test_page"):
            return answer
        if not self.behavior_config_service.fallback_policy().get("active_gap_prompt_on_test_page", True):
            return answer
        gaps = metadata.get("knowledge_gaps") or {}
        docs = [str(item).strip() for item in gaps.get("needed_documents", []) if str(item).strip()]
        questions = [str(item).strip() for item in gaps.get("suggested_questions", []) if str(item).strip()]
        template = self.behavior_config_service.fallback_gap_template()
        if docs and template:
            answer = template.format(needed_document=docs[0])
        else:
            answer = "我现在还不能确认这个问题，因为知识库里没有命中足够可靠的资料。"
        if questions:
            answer += f"\n如果你要我继续追问客户，我建议先问：{questions[0]}"
        return answer

    @staticmethod
    def _render_quote_not_ready_answer(sales_plan, draft: dict) -> str:
        known = sales_plan.known_needs or {}
        config = draft.get("configuration_quote") if isinstance(draft.get("configuration_quote"), dict) else {}
        modules = config.get("modules", []) if isinstance(config.get("modules"), list) else []
        package = config.get("package") if isinstance(config.get("package"), dict) else {}
        core = next((item for item in modules if item.get("module_type") == "core_arm"), {})
        required = [
            str(item.get("name", "")).strip()
            for item in modules
            if item.get("role") == "required" and str(item.get("name", "")).strip()
        ][:5]
        recommended = [
            str(item.get("name", "")).strip()
            for item in modules
            if item.get("role") != "required" and str(item.get("name", "")).strip()
        ][:4]
        facts = []
        if known.get("scenario") == "group_live":
            facts.append("团播/直播间")
        elif known.get("scenario") == "film_pro":
            facts.append("影视/TVC/拍摄")
        elif known.get("scenario") == "broadcast":
            facts.append("广电/演播室")
        if known.get("live_room_area"):
            facts.append(f"{known['live_room_area']} 平")
        if known.get("camera_count"):
            facts.append(f"{known['camera_count']} 个机位")
        if known.get("track_preference"):
            facts.append(str(known["track_preference"]))
        package_name = package.get("name") or "对应场景方案"
        core_name = core.get("name") or (config.get("recommended_arm") or {}).get("name") or "U-MOCO 机械臂"
        lines = [
            f"可以先给你一个参考配置方向：按{('、'.join(facts) if facts else '当前信息')}看，先以 {package_name} 的 {core_name} 作为候选核心来核。",
            "大概会围绕机械臂本体、控制软件、镜头/现场控制和必要交付培训来拆；如果要横移、环绕或大范围走位，轨道和轨道电机会单独作为选配核算。",
        ]
        if required:
            lines.append(f"当前参考配置里会优先看：{'、'.join(required)}。")
        if recommended:
            lines.append(f"可选项再按现场需要加，比如 {'、'.join(recommended)}。")
        missing = [str(item) for item in sales_plan.missing_fields if str(item)]
        if missing:
            labels = {
                "budget": "预算区间",
                "live_room_area": "直播间面积/走位范围",
                "camera_count": "相机或机位数量",
                "track_preference": "是否需要轨道",
                "camera_payload": "相机镜头负载",
                "freed_required": "是否需要 FreeD/XR",
                "delivery_urgency": "期望交付时间",
                "scenario": "使用场景",
            }
            lines.append("要把价格收得更准，还差：" + "、".join(labels.get(item, item) for item in missing[:4]) + "。")
        if sales_plan.soft_question:
            lines.append(sales_plan.soft_question)
        lines.append("以上只能作为参考配置口径，正式价格、优惠、合同和交付安排需要人工同事按最终配置确认。")
        return "\n".join(lines)

    def _memory_recall_answer(self, user_query: str, memory: dict | None) -> str:
        if not memory:
            return ""
        text = str(user_query or "")
        policy = self.behavior_config_service.memory_policy()
        previous_words = policy.get("previous_context_words") or ["上次", "之前", "刚才", "前面", "上一轮"]
        recall_words = policy.get("product_recall_words") or ["什么机械臂", "哪个机械臂", "聊的什么", "是什么产品", "什么产品"]
        if not any(word in text for word in previous_words):
            return ""
        if not any(word in text for word in recall_words):
            return ""
        products = [str(item).strip() for item in memory.get("products", []) if str(item).strip()]
        if not products:
            return "我这里还没有记录到你上次关注的具体机械臂型号。你可以补一句型号，我会记到客户画像里。"
        recent = products[-1]
        template = self.behavior_config_service.memory_recall_template()
        return template.format(product=recent) if template else f"你上次记录里关注的是 {recent}。"

    def _base_metadata(self, request: ChatRequest, model_runtime: dict | None = None, transient_request: bool = False) -> dict:
        metadata = dict(request.metadata or {})
        metadata["behavior_rules_hit"] = []
        metadata["memory_policy"] = self.behavior_config_service.memory_policy()
        runtime = model_runtime or self._resolve_chat_model_runtime(request)
        configured_chat_model = str(runtime.get("configured_chat_model") or self.ollama.current_chat_model())
        requested_chat_model = str(runtime.get("requested_chat_model") or "")
        actual_chat_model = str(runtime.get("actual_chat_model") or configured_chat_model)
        embed_model = str(runtime.get("embed_model") or self.ollama.current_embed_model())
        metadata["models"] = {
            "chat_model": actual_chat_model,
            "configured_chat_model": configured_chat_model,
            "requested_chat_model": requested_chat_model,
            "actual_chat_model": actual_chat_model,
            "embed_model": embed_model,
            "override_used": bool(runtime.get("override_used")),
            "override_rejected": bool(runtime.get("override_rejected")),
            "override_rejected_reason": str(runtime.get("override_rejected_reason") or ""),
            "generation_called": False,
            "generation_ms": 0.0,
        }
        if transient_request:
            self._apply_persistence_skip_metadata(metadata, "model_compare")
        return metadata

    def _risk_precheck(self, request: ChatRequest, metadata: dict) -> dict | None:
        service = getattr(self, "risk_policy_service", None)
        if not service:
            return None
        try:
            risk_plan = service.precheck(request.message, state=None)
            if isinstance(risk_plan, dict):
                metadata["risk_precheck"] = risk_plan
                metadata["risk_plan"] = risk_plan
                return risk_plan
            return None
        except Exception as exc:
            metadata["risk_precheck_error"] = f"{type(exc).__name__}: {exc}"
            return None

    @staticmethod
    def _is_blocked_risk_handoff(risk_plan: dict | None) -> bool:
        if not isinstance(risk_plan, dict):
            return False
        level = str(risk_plan.get("risk_level", "") or "")
        route = str(risk_plan.get("route", "") or "")
        return level == "blocked" and route == "handoff"

    @staticmethod
    def _append_decision_trace(metadata: dict, decision: str) -> None:
        trace = metadata.get("decision_trace")
        if not isinstance(trace, list):
            trace = []
        trace.append(decision)
        metadata["decision_trace"] = trace
        sales_trace = metadata.get("sales_decision_trace")
        if not isinstance(sales_trace, list):
            sales_trace = []
        sales_trace.append(decision)
        metadata["sales_decision_trace"] = sales_trace

    @staticmethod
    def _intent_plan(request: ChatRequest) -> dict:
        metadata = request.metadata or {}
        plan = metadata.get("intent_plan")
        return plan if isinstance(plan, dict) else {}

    @classmethod
    def _intent_is(cls, request: ChatRequest, *intents: str) -> bool:
        plan = cls._intent_plan(request)
        return str(plan.get("intent", "")) in set(intents)

    def _intent_needs_quote(self, request: ChatRequest, user_query: str) -> bool:
        plan = self._intent_plan(request)
        if plan.get("intent"):
            return bool(plan.get("needs_quote_tool"))
        return self.quote_service.is_quote_request(user_query)

    def _should_use_sales_quote(self, request: ChatRequest, user_query: str, sales_plan, context_plan: dict) -> bool:
        if sales_plan.should_direct_answer or sales_plan.sales_stage == "handoff":
            return False
        if sales_plan.sales_stage not in {"recommend", "quote_ready"}:
            return False
        if self._intent_needs_quote(request, user_query):
            return True
        known = sales_plan.known_needs or {}
        has_sales_context = bool(known.get("scenario") or known.get("product_anchors") or context_plan.get("anchors"))
        return bool(context_plan.get("contextual_query") and has_sales_context)

    @classmethod
    def _request_for_intent(cls, request: ChatRequest) -> ChatRequest:
        plan = cls._intent_plan(request)
        if not plan.get("contextual_followup"):
            return request
        message = str(request.message or "").strip()
        additions: list[str] = []
        upper_message = message.upper()
        anchors = [
            str(item).strip()
            for item in plan.get("product_anchors", [])
            if str(item).strip()
        ] if isinstance(plan.get("product_anchors"), list) else []
        missing_anchors = [
            item
            for item in anchors
            if item.upper() not in upper_message
        ]
        if missing_anchors:
            additions.append("上下文产品:" + "、".join(missing_anchors[:4]))
        scenario_terms = [
            str(item).strip()
            for item in plan.get("scenario_terms", [])
            if str(item).strip()
        ] if isinstance(plan.get("scenario_terms"), list) else []
        missing_scenarios = [
            item
            for item in scenario_terms
            if item not in message
        ]
        if missing_scenarios:
            additions.append("上下文场景:" + "、".join(missing_scenarios[:3]))
        if not additions:
            return request
        quote_message = f"{message} {' '.join(additions)}".strip()
        try:
            if hasattr(request, "model_copy"):
                return request.model_copy(update={"message": quote_message})
            return request.copy(update={"message": quote_message})
        except Exception:
            data = request.model_dump() if hasattr(request, "model_dump") else request.dict()
            data["message"] = quote_message
            return ChatRequest(**data)

    @classmethod
    def _intent_clarify_answer(cls, request: ChatRequest) -> str:
        plan = cls._intent_plan(request)
        scenario = "、".join(str(item) for item in plan.get("scenario_terms", []) if str(item)) or "这个方向"
        products = "、".join(str(item) for item in plan.get("product_anchors", []) if str(item))
        subject = f"{scenario} / {products}" if products else scenario
        return f"我看到你提到了{subject}。你是想了解它的适用场景、核心配置、价格口径，还是想让我帮你写一份可发客户的方案？"

    def _chat_model_override(self, request: ChatRequest) -> str | None:
        runtime = self._resolve_chat_model_runtime(request)
        if runtime.get("override_used"):
            return str(runtime.get("actual_chat_model") or "").strip() or None
        return None

    def _resolve_chat_model_runtime(self, request: ChatRequest) -> dict:
        configured_chat_model = str(self.ollama.current_chat_model() or "").strip()
        embed_model = str(self.ollama.current_embed_model() or "").strip()
        metadata = request.metadata or {}
        requested_chat_model = ""
        override_rejected = False
        override_rejected_reason = ""
        actual_chat_model = configured_chat_model
        metadata = request.metadata or {}
        if not metadata.get("test_page"):
            return {
                "configured_chat_model": configured_chat_model,
                "requested_chat_model": requested_chat_model,
                "actual_chat_model": actual_chat_model,
                "embed_model": embed_model,
                "override_used": False,
                "override_rejected": False,
                "override_rejected_reason": "",
            }
        override = metadata.get("model_override")
        if not isinstance(override, dict):
            return {
                "configured_chat_model": configured_chat_model,
                "requested_chat_model": requested_chat_model,
                "actual_chat_model": actual_chat_model,
                "embed_model": embed_model,
                "override_used": False,
                "override_rejected": False,
                "override_rejected_reason": "",
            }
        requested_chat_model = str(override.get("chat_model", "") or "").strip()
        if requested_chat_model:
            requested_lower = requested_chat_model.lower()
            embed_lower = embed_model.lower()
            if requested_lower == embed_lower:
                override_rejected = True
                override_rejected_reason = "requested_model_equals_embed_model"
            elif any(token in requested_lower for token in ("bge", "embed", "embedding")):
                override_rejected = True
                override_rejected_reason = "requested_model_looks_like_embedding_model"
            else:
                actual_chat_model = requested_chat_model
        return {
            "configured_chat_model": configured_chat_model,
            "requested_chat_model": requested_chat_model,
            "actual_chat_model": actual_chat_model,
            "embed_model": embed_model,
            "override_used": bool(requested_chat_model and not override_rejected),
            "override_rejected": override_rejected,
            "override_rejected_reason": override_rejected_reason,
        }

    @staticmethod
    def _is_reference_quote_lookup(user_query: str, matched_rule: dict | None) -> bool:
        if not matched_rule:
            return False
        rule_text = f"{matched_rule.get('rule_name', '')} {matched_rule.get('category', '')} {matched_rule.get('note', '')}"
        if "报价" not in rule_text and "价格" not in rule_text:
            return False
        return any(keyword in user_query for keyword in ("报价", "价格", "多少钱", "优惠价", "总价", "包含", "费用"))

    @staticmethod
    def _requires_handoff(user_query: str) -> bool:
        return any(keyword in user_query for keyword in ("合同", "签约", "交付时间", "交期", "保证", "承诺", "最低价", "一定", "三天", "免费", "库存"))

    @staticmethod
    def _quote_sources(draft: dict) -> list[SourceItem]:
        sources = []
        for source in draft.get("sources", []) or []:
            if source:
                sources.append(SourceItem(
                    type="quote_catalog",
                    source=str(source),
                    category="报价规则库",
                    reason="本轮报价推荐来自结构化报价规则库，不使用 OCR 报价单自动推价。",
                ))
        if not sources:
            sources.append(SourceItem(
                type="quote_catalog",
                source="data/quote_catalog.json",
                category="报价规则库",
                reason="本轮报价推荐来自结构化报价规则库，不使用 OCR 报价单自动推价。",
            ))
        return sources[:3]

    @staticmethod
    def _debug_candidates(faq_candidates: list[RetrievalCandidate], doc_candidates: list[RetrievalCandidate]) -> list[dict]:
        rows = []
        for item in [*faq_candidates[:5], *doc_candidates[:5]]:
            rows.append({
                "type": item.source_type,
                "score": item.score,
                "adjusted_score": item.adjusted_score,
                "reason": item.reason,
                "category": item.payload.get("category", ""),
                "source": item.payload.get("source", ""),
                "title": item.payload.get("question") or item.payload.get("doc_name") or "",
            })
        return rows

    def _audit(self, request_id: str, request: ChatRequest, response: ChatResponse) -> None:
        self._apply_post_rule_check_before_persist(response)
        self._observe_conversation_state(request, response)
        metadata = dict(response.metadata or {})
        try:
            if self.conversation_history_service and not self._is_transient_test_request(request):
                self.conversation_history_service.append_turn(request, response)
            elif self._is_transient_test_request(request):
                self._apply_persistence_skip_metadata(metadata, "model_compare")
                response.metadata = metadata
        except Exception as exc:
            metadata["conversation_history_error"] = f"{type(exc).__name__}: {exc}"
            response.metadata = metadata
        try:
            self.audit_service.record({
                "request_id": request_id,
                "channel": request.channel,
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "route": response.route,
                "answer": str(response.answer or "")[:700],
                "need_human": bool(response.need_human),
                "matched_rule": response.matched_rule,
                "faq_top_score": response.faq_top_score,
                "doc_top_score": response.doc_top_score,
                "cache_hit": response.timings.retrieval_cache_hit,
                "total_ms": response.timings.total_ms,
                "message": request.message[:200],
                "metadata": self._jsonable(response.metadata or {}),
                "sources": self._jsonable([item.model_dump() for item in response.sources[:5]]),
                "retrieval_debug": self._jsonable(response.retrieval_debug[:10]),
            })
        except Exception as exc:
            metadata = dict(response.metadata or {})
            metadata["audit_record_error"] = f"{type(exc).__name__}: {exc}"
            response.metadata = metadata

    def _apply_post_rule_check_before_persist(self, response: ChatResponse) -> None:
        metadata = dict(response.metadata or {})
        original_answer = response.answer
        original_need_human = bool(response.need_human)
        original_route = response.route
        metadata["post_rule_enforce_applied"] = bool(metadata.get("post_rule_enforce_applied", False))
        post_rule_check = metadata.get("post_rule_check") if isinstance(metadata.get("post_rule_check"), dict) else None
        service = getattr(self, "post_rule_check_service", None)

        if post_rule_check is None and service:
            quote_readiness = metadata.get("quote_readiness")
            if not quote_readiness and isinstance(metadata.get("sales_plan"), dict):
                quote_readiness = metadata["sales_plan"].get("quote_readiness")
            try:
                check_result = service.check(
                    route=response.route,
                    answer=response.answer,
                    risk_plan=metadata.get("risk_plan") or metadata.get("risk_precheck"),
                    quote_readiness=quote_readiness,
                    metadata=metadata,
                )
                post_rule_check = check_result if isinstance(check_result, dict) else {}
            except Exception as exc:
                metadata["post_rule_check_error"] = f"{type(exc).__name__}: {exc}"
                post_rule_check = {}
        if post_rule_check is not None:
            metadata["post_rule_check"] = post_rule_check

        try:
            post_check = metadata.get("post_rule_check") if isinstance(metadata.get("post_rule_check"), dict) else {}
            blocked = bool(post_check.get("blocked"))
            safe_answer_raw = post_check.get("safe_answer")
            safe_answer_text = str(safe_answer_raw).strip() if safe_answer_raw is not None else ""
            if blocked and safe_answer_text:
                response.answer = safe_answer_text
                response.need_human = True
                metadata["post_rule_enforce_applied"] = True
                metadata.setdefault("original_answer", original_answer)
                metadata.setdefault("original_need_human", original_need_human)
                metadata.setdefault("original_route", original_route)
                metadata["enforce_reason"] = "post_rule_blocked"
        except Exception as exc:
            response.answer = original_answer
            response.need_human = original_need_human
            metadata["post_rule_enforce_applied"] = False
            metadata["post_rule_enforce_error"] = f"{type(exc).__name__}: {exc}"
        response.metadata = metadata

    def _attach_state_before(self, request: ChatRequest, metadata: dict) -> None:
        if self._is_transient_test_request(request):
            metadata["conversation_state_before"] = {}
            self._apply_persistence_skip_metadata(metadata, "model_compare")
            return
        try:
            store = getattr(self, "conversation_state_store", None)
            if not store:
                metadata["conversation_state_before"] = {}
                return
            state = store.get_state(
                conversation_id=str(request.conversation_id or ""),
                channel=str(request.channel or "default"),
            )
            metadata["conversation_state_before"] = state if isinstance(state, dict) else {}
        except Exception as exc:
            metadata["conversation_state_before"] = {}
            metadata["conversation_state_error"] = f"{type(exc).__name__}: {exc}"

    def _observe_conversation_state(self, request: ChatRequest, response: ChatResponse) -> None:
        metadata = dict(response.metadata or {})
        before = metadata.get("conversation_state_before")
        if not isinstance(before, dict):
            before = {}
            metadata["conversation_state_before"] = before
        if self._is_transient_test_request(request):
            metadata["conversation_state_after"] = before
            self._apply_persistence_skip_metadata(metadata, "model_compare")
            response.metadata = metadata
            return
        store = getattr(self, "conversation_state_store", None)
        if not store:
            metadata["conversation_state_after"] = before
            response.metadata = metadata
            return
        if not str(request.conversation_id or "").strip():
            metadata["conversation_state_after"] = before
            response.metadata = metadata
            return
        try:
            updates = self._state_updates_from_response(response, metadata)
            after = store.update_state(
                conversation_id=str(request.conversation_id or ""),
                state_updates=updates,
                channel=str(request.channel or "default"),
            )
            metadata["conversation_state_after"] = after if isinstance(after, dict) else before
        except Exception as exc:
            metadata["conversation_state_after"] = before
            metadata["conversation_state_update_error"] = f"{type(exc).__name__}: {exc}"
        response.metadata = metadata

    @staticmethod
    def _state_updates_from_response(response: ChatResponse, metadata: dict) -> dict[str, object]:
        intent_plan = metadata.get("intent_plan") if isinstance(metadata.get("intent_plan"), dict) else {}
        sales_plan = metadata.get("sales_plan") if isinstance(metadata.get("sales_plan"), dict) else {}
        risk_plan = metadata.get("risk_plan") if isinstance(metadata.get("risk_plan"), dict) else {}
        risk_precheck = metadata.get("risk_precheck") if isinstance(metadata.get("risk_precheck"), dict) else {}
        context_plan = metadata.get("context_plan") if isinstance(metadata.get("context_plan"), dict) else {}

        updates: dict[str, object] = {
            "last_assistant_route": response.route,
            "human_handoff_required": bool(response.need_human or response.route == "handoff"),
        }

        intent = str(intent_plan.get("intent") or intent_plan.get("primary_intent") or "").strip()
        if intent:
            updates["last_user_intent"] = intent

        stage = str(sales_plan.get("sales_stage") or sales_plan.get("stage") or "").strip()
        if stage:
            updates["stage"] = stage

        known_needs = sales_plan.get("known_needs")
        if isinstance(known_needs, dict):
            updates["known_needs"] = known_needs

        missing_fields = sales_plan.get("missing_fields")
        if isinstance(missing_fields, list):
            updates["missing_fields"] = missing_fields

        quote_readiness = sales_plan.get("quote_readiness")
        if quote_readiness not in (None, "", []):
            updates["quote_readiness"] = quote_readiness

        risk_reasons = risk_plan.get("risk_reasons") if isinstance(risk_plan.get("risk_reasons"), list) else []
        if not risk_reasons:
            risk_reasons = risk_precheck.get("risk_reasons") if isinstance(risk_precheck.get("risk_reasons"), list) else []
        if risk_reasons:
            updates["risk_flags"] = [str(item) for item in risk_reasons if str(item)]

        if updates.get("human_handoff_required"):
            reason = next((str(item) for item in risk_reasons if str(item)), "")
            if reason:
                updates["last_need_human_reason"] = reason

        product_anchors = intent_plan.get("product_anchors") if isinstance(intent_plan.get("product_anchors"), list) else []
        if product_anchors:
            first_anchor = str(product_anchors[0]).strip()
            if first_anchor:
                updates["product_anchor"] = first_anchor
        elif isinstance(context_plan.get("product_anchor"), str) and context_plan.get("product_anchor").strip():
            updates["product_anchor"] = context_plan.get("product_anchor").strip()

        scenario_anchor = ""
        if isinstance(known_needs, dict):
            scenario_anchor = str(known_needs.get("scenario") or "").strip()
        if not scenario_anchor and isinstance(context_plan.get("scenario_anchor"), str):
            scenario_anchor = context_plan.get("scenario_anchor").strip()
        if scenario_anchor:
            updates["scenario_anchor"] = scenario_anchor

        if response.route in {"quote_draft", "doc", "faq"}:
            preview = str(response.answer or "").strip().replace("\n", " ")
            if preview:
                updates["last_recommendation"] = preview[:120]

        return updates

    @staticmethod
    def _apply_cache_policy_enforce(request: ChatRequest, context_plan: dict, metadata: dict) -> None:
        original_bypass_cache = bool(context_plan.get("bypass_cache"))
        metadata["cache_policy_enforce_mode"] = "minimal"
        metadata["original_bypass_cache"] = original_bypass_cache
        metadata["final_bypass_cache"] = original_bypass_cache
        metadata["cache_policy_enforce_applied"] = False
        metadata["cache_policy_enforce_reason_codes"] = []

        try:
            raw_policy = (request.metadata or {}).get("cache_policy_metadata")
            if not isinstance(raw_policy, dict):
                metadata["cache_policy_enforce_skipped_reason"] = "no_cache_policy_metadata"
                return
            reason_codes = raw_policy.get("reason_codes")
            if not isinstance(reason_codes, list):
                metadata["cache_policy_enforce_skipped_reason"] = "no_reason_codes"
                return
            allowed = {"contextual_followup", "risk_sensitive", "handoff_state", "pronoun_reference", "price_or_track_question"}
            enforce_reason_codes = [str(item) for item in reason_codes if str(item) in allowed]
            if not enforce_reason_codes:
                metadata["cache_policy_enforce_skipped_reason"] = "no_enforce_reason_codes"
                return
            final_bypass_cache = bool(original_bypass_cache or bool(enforce_reason_codes))
            context_plan["bypass_cache"] = final_bypass_cache
            metadata["cache_policy_enforce_applied"] = True
            metadata["cache_policy_enforce_reason_codes"] = list(dict.fromkeys(enforce_reason_codes))
            metadata["final_bypass_cache"] = final_bypass_cache
        except Exception as exc:
            context_plan["bypass_cache"] = original_bypass_cache
            metadata["cache_policy_enforce_applied"] = False
            metadata["cache_policy_enforce_reason_codes"] = []
            metadata["final_bypass_cache"] = original_bypass_cache
            metadata["cache_policy_enforce_error"] = f"{type(exc).__name__}: {exc}"

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
    def _apply_persistence_skip_metadata(metadata: dict, reason: str) -> None:
        metadata["transient_test"] = True
        metadata["persistence_skipped"] = True
        metadata["persistence_skip_reason"] = reason

    @staticmethod
    def _mark_generation_metadata(metadata: dict, generation_ms: float) -> None:
        models = metadata.get("models")
        if not isinstance(models, dict):
            return
        models["generation_called"] = True
        models["generation_ms"] = float(generation_ms or 0.0)

    @staticmethod
    def _elapsed(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 1)

    @staticmethod
    def _jsonable(value):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
