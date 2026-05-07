import time
import uuid
from typing import Literal

from support_app.repositories.rule_repository import RuleRepository
from support_app.schemas import ChatRequest, ChatResponse, SourceItem, TimingInfo
from support_app.services.audit_service import AuditService
from support_app.services.customer_memory_service import CustomerMemoryService
from support_app.services.ollama_client import OllamaClient
from support_app.services.prompt_builder import build_docs_prompt, build_faq_prompt, build_handoff_answer
from support_app.services.quote_service import QuoteService
from support_app.services.retrieval_service import RetrievalCandidate, RetrievalService
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
    ):
        self.settings = settings
        self.ollama = ollama
        self.retrieval_service = retrieval_service
        self.rule_repo = rule_repo
        self.memory_service = memory_service
        self.audit_service = audit_service
        self.quote_service = quote_service

    def answer(self, request: ChatRequest) -> ChatResponse:
        start = time.perf_counter()
        timings = TimingInfo()
        user_query = request.message.strip()
        request_id = str(uuid.uuid4())

        faq_hits = []
        doc_hits = []
        faq_candidates: list[RetrievalCandidate] = []
        doc_candidates: list[RetrievalCandidate] = []
        matched_rule = None
        memory = None
        faq_top_score = 0.0
        doc_top_score = 0.0

        try:
            t = time.perf_counter()
            memory = self.memory_service.load_for_request(request)
            memory_context = self.memory_service.render_prompt_block(memory)
            timings.memory_ms = self._elapsed(t)

            t = time.perf_counter()
            matched_rule = self.rule_repo.match(user_query)
            timings.rule_match_ms = self._elapsed(t)
            if self._requires_handoff(user_query):
                answer = build_handoff_answer(user_query, matched_rule)
                t = time.perf_counter()
                memory = self.memory_service.update_from_turn(request, answer, "handoff")
                timings.memory_ms += self._elapsed(t)
                timings.total_ms = self._elapsed(start)
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
                    metadata=request.metadata,
                )
                self._audit(request_id, request, response)
                return response
            if (
                matched_rule
                and str(matched_rule.get("action", "")) in ("manual_required", "block_commitment")
                and not self._is_reference_quote_lookup(user_query, matched_rule)
            ):
                answer = build_handoff_answer(user_query, matched_rule)
                t = time.perf_counter()
                memory = self.memory_service.update_from_turn(request, answer, "handoff")
                timings.memory_ms += self._elapsed(t)
                timings.total_ms = self._elapsed(start)
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
                    metadata=request.metadata,
                )
                self._audit(request_id, request, response)
                return response

            t = time.perf_counter()
            retrieval = self.retrieval_service.retrieve(user_query, request.channel, request.user_id)
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

            if self.quote_service.is_quote_request(user_query):
                t = time.perf_counter()
                quote_result = self.quote_service.draft(request, memory, doc_candidates)
                timings.route_decision_ms = self._elapsed(t)
                sources = self._format_sources(doc_candidates, "doc")
                t = time.perf_counter()
                memory = self.memory_service.update_from_turn(request, quote_result["answer"], "quote_draft")
                timings.memory_ms += self._elapsed(t)
                timings.total_ms = self._elapsed(start)
                metadata = dict(request.metadata or {})
                metadata["quote_draft"] = quote_result["draft"]
                response = ChatResponse(
                    answer=quote_result["answer"],
                    route="quote_draft",
                    need_human=True,
                    hint="这是报价草案，正式价格、优惠、交付和合同需人工确认",
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
            )
            timings.route_decision_ms = self._elapsed(t)

            sources: list[SourceItem] = []
            if route in ("faq", "doc") and prompt:
                t = time.perf_counter()
                answer = self.ollama.generate(prompt)
                timings.answer_generation_ms = self._elapsed(t)

                t = time.perf_counter()
                candidates = faq_candidates if source_type == "faq" else doc_candidates
                sources = self._format_sources(candidates, source_type)
                timings.source_format_ms = self._elapsed(t)
            elif route == "faq":
                sources = self._format_sources(faq_candidates, "faq")
            elif route == "doc":
                sources = self._format_sources(doc_candidates, "doc")

            t = time.perf_counter()
            memory = self.memory_service.update_from_turn(request, answer, route)
            timings.memory_ms += self._elapsed(t)

            timings.total_ms = self._elapsed(start)
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
                metadata=request.metadata,
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
                metadata=request.metadata,
            )
            self._audit(request_id, request, response)
            return response

    def _route(
        self,
        user_query: str,
        matched_rule: dict | None,
        faq_hits,
        doc_hits,
        faq_top_score: float,
        doc_top_score: float,
        memory_context: str = "",
    ) -> tuple[Literal["faq", "doc", "handoff", "fallback"], list, Literal["faq", "doc"] | None, str | None, str, bool, str]:
        route: Literal["faq", "doc", "handoff", "fallback"] = "fallback"
        selected_hits = []
        source_type: Literal["faq", "doc"] | None = None
        prompt = None
        answer = "我暂时无法根据现有文档确认，建议人工进一步确认。"
        need_human = False
        hint = "当前未触发人工接管提示"

        if matched_rule:
            need_human = True
            hint = "本回答建议人工进一步确认"
            action = str(matched_rule.get("action", ""))
            if self._is_reference_quote_lookup(user_query, matched_rule) and doc_hits and doc_top_score >= self.settings.doc_score_threshold:
                route = "doc"
                selected_hits = doc_hits
                source_type = "doc"
                answer = self._direct_price_answer(user_query, doc_hits[0]) or answer
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
            if faq_top_score >= self.settings.faq_direct_answer_threshold:
                answer = self._direct_faq_answer(faq_hits[0])
            else:
                prompt = build_faq_prompt(user_query, faq_hits, memory_context)
        elif doc_hits and doc_top_score >= self.settings.doc_score_threshold:
            route = "doc"
            selected_hits = doc_hits
            source_type = "doc"
            answer = self._direct_price_answer(user_query, doc_hits[0]) or answer
            prompt = None if answer != "我暂时无法根据现有文档确认，建议人工进一步确认。" else build_docs_prompt(user_query, doc_hits, memory_context)
        elif faq_hits and faq_top_score >= self.settings.faq_score_threshold:
            route = "faq"
            selected_hits = faq_hits
            source_type = "faq"
            prompt = build_faq_prompt(user_query, faq_hits, memory_context)

        return route, selected_hits, source_type, prompt, answer, need_human, hint

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
    def _is_reference_quote_lookup(user_query: str, matched_rule: dict | None) -> bool:
        if not matched_rule:
            return False
        rule_text = f"{matched_rule.get('rule_name', '')} {matched_rule.get('category', '')} {matched_rule.get('note', '')}"
        if "报价" not in rule_text and "价格" not in rule_text:
            return False
        return any(keyword in user_query for keyword in ("报价", "价格", "多少钱", "优惠价", "总价", "包含", "费用"))

    @staticmethod
    def _requires_handoff(user_query: str) -> bool:
        return any(keyword in user_query for keyword in ("合同", "签约", "交付时间", "交期", "保证", "承诺"))

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
        try:
            self.audit_service.record({
                "request_id": request_id,
                "channel": request.channel,
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "route": response.route,
                "faq_top_score": response.faq_top_score,
                "doc_top_score": response.doc_top_score,
                "cache_hit": response.timings.retrieval_cache_hit,
                "total_ms": response.timings.total_ms,
                "message": request.message[:200],
            })
        except Exception:
            pass

    @staticmethod
    def _elapsed(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 1)
