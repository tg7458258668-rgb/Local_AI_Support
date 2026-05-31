import unittest

from support_app.schemas import ChatRequest, ChatResponse, SourceItem
from support_app.services.answer_pipeline import AnswerPipeline


class FakeLegacyChatService:
    def _answer_current(self, request):
        return ChatResponse(
            answer="参考报价需要人工确认。",
            route="quote_draft",
            need_human=True,
            matched_rule="报价必须人工确认",
            faq_top_score=0.2,
            doc_top_score=0.1,
            sources=[SourceItem(type="quote_catalog", source="data/quote_catalog.json")],
            metadata={
                "context_plan": {
                    "used_history": True,
                    "used_memory": False,
                    "history_turn_count": 2,
                }
            },
            conversation_id=request.conversation_id,
        )


class FakeLegacyFAQChatService:
    def _answer_current(self, request):
        return ChatResponse(
            answer="电池保修为3个月。",
            route="faq",
            need_human=False,
            faq_top_score=0.92,
            doc_top_score=0.1,
            sources=[SourceItem(type="faq", source="data/faq.json", question="电池保修多久？")],
            metadata={
                "risk_plan": {"risk_level": "low"},
                "context_plan": {"used_history": False, "used_memory": False, "history_turn_count": 0},
            },
            conversation_id=request.conversation_id,
        )


class FakeLegacyRiskyAnswerChatService:
    def __init__(self, answer: str, route: str, need_human: bool, risk_level: str):
        self._answer = answer
        self._route = route
        self._need_human = need_human
        self._risk_level = risk_level

    def _answer_current(self, request):
        return ChatResponse(
            answer=self._answer,
            route=self._route,
            need_human=self._need_human,
            faq_top_score=0.0,
            doc_top_score=0.0,
            sources=[],
            metadata={
                "risk_plan": {"risk_level": self._risk_level},
                "context_plan": {"used_history": False, "used_memory": False, "history_turn_count": 0},
            },
            conversation_id=request.conversation_id,
        )


class FakeRiskPolicyService:
    def precheck(self, message, state=None):
        if "最低价" in message:
            return {
                "risk_level": "blocked",
                "need_human": True,
                "route": "handoff",
                "safe_answer": "需要人工确认",
                "risk_reasons": ["命中 blocked 商业风险词"],
                "allowed_answer_scope": "仅可引导转人工",
                "matched_keywords": ["最低价"],
            }
        return {
            "risk_level": "low",
            "need_human": False,
            "route": "answer",
            "safe_answer": "",
            "risk_reasons": ["未命中风险词，按低风险处理"],
            "allowed_answer_scope": "可按知识库正常回答。",
            "matched_keywords": [],
        }


class BrokenRiskPolicyService:
    def precheck(self, message, state=None):
        raise RuntimeError("risk service down")


class FakePostRuleCheckService:
    def check(self, route, answer, risk_plan=None, quote_readiness=None, metadata=None):
        risk_level = (risk_plan or {}).get("risk_level", "")
        if "保证现货" in answer:
            return {
                "passed": False,
                "blocked": True,
                "need_rewrite": True,
                "need_human": True,
                "safe_answer": "需要人工确认",
                "warnings": [],
                "matched_terms": ["保证现货"],
                "checked_items": ["blocked_terms_check"],
            }
        if risk_level in {"medium", "high"} and "销售确认" not in answer and "人工确认" not in answer:
            return {
                "passed": False,
                "blocked": False,
                "need_rewrite": True,
                "need_human": True,
                "safe_answer": answer + "\n需要销售确认",
                "warnings": ["missing_risk_disclaimer"],
                "matched_terms": [],
                "checked_items": ["risk_disclaimer_check"],
            }
        return {
            "passed": True,
            "blocked": False,
            "need_rewrite": False,
            "need_human": False,
            "safe_answer": None,
            "warnings": [],
            "matched_terms": [],
            "checked_items": ["all_checks_passed"],
        }


class BrokenPostRuleCheckService:
    def check(self, route, answer, risk_plan=None, quote_readiness=None, metadata=None):
        raise RuntimeError("post rule check down")


class BadSafeAnswer:
    def __str__(self):
        raise RuntimeError("cannot stringify safe answer")


class BrokenEnforcePostRuleCheckService:
    def check(self, route, answer, risk_plan=None, quote_readiness=None, metadata=None):
        return {
            "passed": False,
            "blocked": True,
            "need_rewrite": True,
            "need_human": True,
            "safe_answer": BadSafeAnswer(),
            "warnings": [],
            "matched_terms": ["保证现货"],
            "checked_items": ["blocked_terms_check"],
        }


class FakeLegacyAlreadyEnforcedChatService:
    def _answer_current(self, request):
        return ChatResponse(
            answer="这个问题涉及具体配置或商务确认，我可以先帮您整理需求，具体价格、库存或交付时间需要由销售同事进一步确认。",
            route="quote_draft",
            need_human=True,
            faq_top_score=0.0,
            doc_top_score=0.0,
            sources=[],
            metadata={
                "post_rule_check": {
                    "passed": False,
                    "blocked": True,
                    "need_rewrite": True,
                    "need_human": True,
                    "safe_answer": "这个问题涉及具体配置或商务确认，我可以先帮您整理需求，具体价格、库存或交付时间需要由销售同事进一步确认。",
                    "warnings": [],
                    "matched_terms": ["保证现货"],
                    "checked_items": ["blocked_terms_check"],
                },
                "post_rule_enforce_applied": True,
                "original_answer": "我们保证现货，明天就能发。",
                "original_need_human": False,
                "original_route": "quote_draft",
                "enforce_reason": "post_rule_blocked",
                "context_plan": {"used_history": False, "used_memory": False, "history_turn_count": 0},
            },
            conversation_id=request.conversation_id,
        )


class FakeUnderstandPlanAdapter:
    def build(self, message, intent_plan=None, sales_plan=None, context_plan=None, conversation_state=None, risk_plan=None):
        return {
            "context": {
                "is_followup": False,
                "resolved_query": str(message or ""),
                "product_anchor": "GRA",
                "scenario_anchor": "group_live",
                "product_anchors": ["GRA"],
                "source": "intent_plan/context_plan/state",
            },
            "intent": {
                "primary_intent": str((intent_plan or {}).get("primary_intent") or (intent_plan or {}).get("intent") or "fallback"),
                "confidence": (intent_plan or {}).get("confidence"),
                "needs_quote_tool": bool((intent_plan or {}).get("needs_quote_tool")),
                "risk_flags": [],
                "source": "intent_plan",
            },
            "sales": {
                "stage": str((sales_plan or {}).get("sales_stage") or ""),
                "known_needs": (sales_plan or {}).get("known_needs", {}),
                "missing_fields": (sales_plan or {}).get("missing_fields", []),
                "quote_readiness": (sales_plan or {}).get("quote_readiness", ""),
                "source": "sales_plan/state",
            },
            "risk": {
                "risk_level": str((risk_plan or {}).get("risk_level") or ""),
                "need_human": bool((risk_plan or {}).get("need_human")),
                "risk_reasons": (risk_plan or {}).get("risk_reasons", []),
                "matched_keywords": (risk_plan or {}).get("matched_keywords", []),
            },
            "state_ref": {
                "has_state": bool(conversation_state),
                "product_anchor": str((conversation_state or {}).get("product_anchor") or ""),
                "scenario_anchor": str((conversation_state or {}).get("scenario_anchor") or ""),
                "quote_readiness": str((conversation_state or {}).get("quote_readiness") or ""),
                "human_handoff_required": bool((conversation_state or {}).get("human_handoff_required")),
            },
            "cache_hints": {"should_bypass_cache": False, "reason_codes": []},
        }


class BrokenUnderstandPlanAdapter:
    def build(self, message, intent_plan=None, sales_plan=None, context_plan=None, conversation_state=None, risk_plan=None):
        raise RuntimeError("understand adapter down")


class BrokenCachePolicyMetadataService:
    def build(
        self,
        message,
        understand_plan=None,
        context_plan=None,
        risk_plan=None,
        risk_precheck=None,
        conversation_state_after=None,
        current_retrieval_bypass_cache=None,
    ):
        raise RuntimeError("cache policy metadata down")


class FakeLegacyMetadataRichChatService:
    def _answer_current(self, request):
        return ChatResponse(
            answer="推荐先看 GRA 团播方案。",
            route="quote_draft",
            need_human=False,
            faq_top_score=0.0,
            doc_top_score=0.0,
            sources=[],
            metadata={
                "intent_plan": {"intent": "quote_inquiry", "confidence": 0.88, "needs_quote_tool": True},
                "sales_plan": {
                    "sales_stage": "recommend",
                    "known_needs": {"scenario": "group_live", "live_room_area": "30"},
                    "missing_fields": ["budget"],
                    "quote_readiness": "partial",
                },
                "context_plan": {"resolved_query": "GRA 团播方案 报价", "is_followup": True},
                "risk_plan": {"risk_level": "medium", "need_human": False, "risk_reasons": ["价格敏感"], "matched_keywords": ["报价"]},
                "conversation_state_after": {
                    "product_anchor": "GRA",
                    "scenario_anchor": "group_live",
                    "quote_readiness": "partial",
                    "human_handoff_required": False,
                },
            },
            conversation_id=request.conversation_id,
        )


class AnswerPipelineTests(unittest.TestCase):
    def test_pipeline_preserves_chat_response_and_adds_quality_metadata(self):
        request = ChatRequest(message="EXT 加 6 米轨道多少钱", conversation_id="s1")

        response = AnswerPipeline(
            FakeLegacyChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertEqual(response.route, "quote_draft")
        self.assertEqual(response.matched_rule, "报价必须人工确认")
        self.assertTrue(response.need_human)
        self.assertIn("request_id", response.metadata)
        self.assertIn("risk_precheck", response.metadata)
        self.assertIn("post_rule_check", response.metadata)
        self.assertIn("understand_plan", response.metadata)
        self.assertIn("cache_policy_metadata", response.metadata)
        self.assertEqual(response.metadata["risk_precheck"]["risk_level"], "low")
        self.assertFalse(response.metadata["risk_precheck"]["need_human"])
        self.assertEqual(response.metadata["risk_precheck"]["matched_keywords"], [])
        self.assertIn("risk_reasons", response.metadata["risk_precheck"])
        self.assertEqual(response.metadata["intent_plan"]["intent"], "quote_price")
        self.assertEqual(response.metadata["intent_plan"]["route_policy"], "quote_draft")
        self.assertIn("EXT", response.metadata["product_anchors"])
        self.assertIn("多少钱", response.metadata["action_terms"])
        self.assertIn("decision_trace", response.metadata)
        self.assertIn("QuoteIntentDetector", response.metadata["used_tools"])
        self.assertIn("QuoteTool", response.metadata["used_tools"])
        self.assertIn("quote_requires_review", response.metadata["quality_flags"])
        self.assertTrue(response.metadata["need_human_review"])

    def test_price_commitment_question_adds_high_or_blocked_risk_precheck(self):
        request = ChatRequest(message="最低价多少？", conversation_id="s2")

        response = AnswerPipeline(
            FakeLegacyChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertIn(response.metadata["risk_precheck"]["risk_level"], {"high", "blocked"})
        self.assertEqual(response.route, "quote_draft")
        self.assertTrue(response.need_human)

    def test_metadata_only_risk_precheck_does_not_change_route_or_need_human(self):
        request = ChatRequest(message="电池保修多久？", conversation_id="s3")

        response = AnswerPipeline(
            FakeLegacyChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertEqual(response.route, "quote_draft")
        self.assertTrue(response.need_human)
        self.assertIn("risk_precheck", response.metadata)
        self.assertIn("understand_plan", response.metadata)

    def test_risk_precheck_failure_does_not_break_pipeline_and_writes_error(self):
        request = ChatRequest(message="最低价多少？", conversation_id="s4")

        response = AnswerPipeline(
            FakeLegacyChatService(),
            risk_policy_service=BrokenRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertEqual(response.route, "quote_draft")
        self.assertTrue(response.need_human)
        self.assertIn("risk_precheck_error", response.metadata)
        self.assertIn("risk_precheck", response.metadata)
        self.assertIn(response.metadata["risk_precheck"]["risk_level"], {"high", "blocked"})

    def test_observation_mode_adds_post_rule_check_for_normal_answer(self):
        request = ChatRequest(message="电池保修多久？", conversation_id="s5")

        response = AnswerPipeline(
            FakeLegacyFAQChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertIn("post_rule_check", response.metadata)
        self.assertTrue(response.metadata["post_rule_check"]["passed"])
        self.assertFalse(response.metadata["post_rule_enforce_applied"])
        self.assertEqual(response.answer, "电池保修为3个月。")
        self.assertEqual(response.route, "faq")
        self.assertFalse(response.need_human)

    def test_medium_high_risk_needs_rewrite_but_answer_not_changed(self):
        request = ChatRequest(message="给我报价", conversation_id="s6")
        original_answer = "这套大概5万元。"

        response = AnswerPipeline(
            FakeLegacyRiskyAnswerChatService(original_answer, "quote_draft", False, "medium"),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertIn("post_rule_check", response.metadata)
        self.assertTrue(response.metadata["post_rule_check"]["need_rewrite"])
        self.assertFalse(response.metadata["post_rule_check"]["blocked"])
        self.assertFalse(response.metadata["post_rule_enforce_applied"])
        self.assertEqual(response.answer, original_answer)
        self.assertEqual(response.route, "quote_draft")
        self.assertFalse(response.need_human)

    def test_blocked_term_detected_is_observation_only_in_pipeline(self):
        request = ChatRequest(message="库存怎么样", conversation_id="s7")
        original_answer = "我们保证现货，明天就能发。"

        response = AnswerPipeline(
            FakeLegacyRiskyAnswerChatService(original_answer, "quote_draft", False, "high"),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
        ).answer(request)

        self.assertTrue(response.metadata["post_rule_check"]["blocked"])
        self.assertFalse(response.metadata["post_rule_enforce_applied"])
        self.assertEqual(response.answer, original_answer)
        self.assertFalse(response.need_human)
        self.assertEqual(response.route, "quote_draft")

    def test_post_rule_check_error_does_not_break_pipeline(self):
        request = ChatRequest(message="电池保修多久？", conversation_id="s8")

        response = AnswerPipeline(
            FakeLegacyFAQChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=BrokenPostRuleCheckService(),
        ).answer(request)

        self.assertEqual(response.route, "faq")
        self.assertFalse(response.need_human)
        self.assertIn("post_rule_check_error", response.metadata)

    def test_pipeline_keeps_chatservice_enforced_response_unchanged(self):
        request = ChatRequest(message="库存怎么样", conversation_id="s9")

        response = AnswerPipeline(
            FakeLegacyAlreadyEnforcedChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=BrokenEnforcePostRuleCheckService(),
        ).answer(request)

        self.assertEqual(
            response.answer,
            "这个问题涉及具体配置或商务确认，我可以先帮您整理需求，具体价格、库存或交付时间需要由销售同事进一步确认。",
        )
        self.assertTrue(response.need_human)
        self.assertEqual(response.route, "quote_draft")
        self.assertTrue(response.metadata["post_rule_enforce_applied"])
        self.assertEqual(response.metadata["original_answer"], "我们保证现货，明天就能发。")
        self.assertEqual(response.metadata["enforce_reason"], "post_rule_blocked")

    def test_understand_plan_metadata_contains_six_blocks(self):
        request = ChatRequest(message="给我推荐方案", conversation_id="s10")
        original_answer = "推荐先看 GRA 团播方案。"

        response = AnswerPipeline(
            FakeLegacyMetadataRichChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
            understand_plan_adapter=FakeUnderstandPlanAdapter(),
        ).answer(request)

        self.assertEqual(response.answer, original_answer)
        self.assertEqual(response.route, "quote_draft")
        self.assertFalse(response.need_human)
        self.assertIn("understand_plan", response.metadata)
        plan = response.metadata["understand_plan"]
        self.assertIn("context", plan)
        self.assertIn("intent", plan)
        self.assertIn("sales", plan)
        self.assertIn("risk", plan)
        self.assertIn("state_ref", plan)
        self.assertIn("cache_hints", plan)
        self.assertIn("cache_policy_metadata", response.metadata)

    def test_understand_plan_maps_intent_sales_state_and_risk(self):
        response = AnswerPipeline(
            FakeLegacyMetadataRichChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
            understand_plan_adapter=FakeUnderstandPlanAdapter(),
        ).answer(ChatRequest(message="报价", conversation_id="s11"))

        plan = response.metadata["understand_plan"]
        self.assertEqual(plan["intent"]["primary_intent"], response.metadata["intent_plan"]["intent"])
        self.assertEqual(plan["sales"]["known_needs"]["scenario"], "group_live")
        self.assertTrue(plan["state_ref"]["has_state"])
        self.assertEqual(plan["risk"]["risk_level"], "medium")

    def test_understand_plan_adapter_error_does_not_break_pipeline(self):
        request = ChatRequest(message="给我推荐方案", conversation_id="s12")
        original_answer = "推荐先看 GRA 团播方案。"

        response = AnswerPipeline(
            FakeLegacyMetadataRichChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
            understand_plan_adapter=BrokenUnderstandPlanAdapter(),
        ).answer(request)

        self.assertEqual(response.answer, original_answer)
        self.assertEqual(response.route, "quote_draft")
        self.assertFalse(response.need_human)
        self.assertIn("understand_plan_error", response.metadata)

    def test_cache_policy_metadata_observation_does_not_change_behavior(self):
        request = ChatRequest(message="那要不要轨道", conversation_id="s13")
        original_answer = "推荐先看 GRA 团播方案。"

        response = AnswerPipeline(
            FakeLegacyMetadataRichChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
            understand_plan_adapter=FakeUnderstandPlanAdapter(),
        ).answer(request)

        self.assertEqual(response.answer, original_answer)
        self.assertEqual(response.route, "quote_draft")
        self.assertFalse(response.need_human)
        self.assertIn("cache_policy_metadata", response.metadata)
        self.assertFalse(response.metadata["cache_policy_metadata"]["allow_final_answer_cache"])

    def test_cache_policy_metadata_would_change_current_behavior_when_mismatch(self):
        class FakeLegacyWithBypassFlag:
            def _answer_current(self, request):
                return ChatResponse(
                    answer="推荐先看 GRA 团播方案。",
                    route="quote_draft",
                    need_human=False,
                    metadata={
                        "context_plan": {"bypass_cache": False},
                        "risk_plan": {"risk_level": "high"},
                    },
                )

        response = AnswerPipeline(
            FakeLegacyWithBypassFlag(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
            understand_plan_adapter=FakeUnderstandPlanAdapter(),
        ).answer(ChatRequest(message="报价", conversation_id="s14"))

        self.assertIn("cache_policy_metadata", response.metadata)
        meta = response.metadata["cache_policy_metadata"]
        self.assertTrue(meta["should_bypass_cache"])
        self.assertTrue(meta["would_change_current_behavior"])
        self.assertEqual(meta["current_retrieval_bypass_cache"], False)
        self.assertEqual(response.route, "quote_draft")
        self.assertFalse(response.need_human)

    def test_cache_policy_metadata_error_does_not_break_pipeline(self):
        response = AnswerPipeline(
            FakeLegacyMetadataRichChatService(),
            risk_policy_service=FakeRiskPolicyService(),
            post_rule_check_service=FakePostRuleCheckService(),
            understand_plan_adapter=FakeUnderstandPlanAdapter(),
            cache_policy_metadata_service=BrokenCachePolicyMetadataService(),
        ).answer(ChatRequest(message="报价", conversation_id="s15"))

        self.assertEqual(response.answer, "推荐先看 GRA 团播方案。")
        self.assertEqual(response.route, "quote_draft")
        self.assertFalse(response.need_human)
        self.assertIn("cache_policy_metadata_error", response.metadata)


if __name__ == "__main__":
    unittest.main()
