import tempfile
import unittest
from pathlib import Path

from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.schemas import ChatRequest, ChatResponse
from support_app.services.chat_service import ChatService
from support_app.services.configuration_quote_service import ConfigurationQuoteService
from support_app.services.conversation_history_service import ConversationHistoryService
from support_app.services.conversation_state_store import ConversationStateStore
from support_app.services.quote_catalog_service import QuoteCatalogService
from support_app.services.quote_policy_service import QuotePolicyService
from support_app.services.quote_service import QuoteService
from support_app.services.retrieval_service import RetrievalService
from support_app.services.risk_policy_service import RiskPolicyService
from support_app.services.post_rule_check_service import PostRuleCheckService


class FakeSettings:
    retrieval_cache_ttl_seconds = 300
    faq_score_threshold = 0.5
    doc_score_threshold = 0.5
    faq_direct_answer_threshold = 0.85
    faq_doc_margin = 0.05


class FakeOllama:
    def current_embed_model(self):
        return "embed-test"

    def current_chat_model(self):
        return "chat-test"

    def embedding(self, text):
        return [float(len(text) % 7), 0.2, 0.3]

    def generate(self, prompt, model=None):
        return "生成回答"


class FakeHit:
    def __init__(self, score=0.9, payload=None):
        self.score = score
        self.payload = payload or {}


class FakeVectorRepo:
    def __init__(self):
        self.calls = 0

    def search_faq_by_vector(self, vector):
        self.calls += 1
        return [FakeHit(payload={"question": "价格", "answer": "参考价", "category": "报价"})]

    def search_docs_by_vector(self, vector):
        return []


class FakeMemoryService:
    def load_for_request(self, request):
        return None

    def render_prompt_block(self, memory):
        return ""

    def update_from_turn(self, request, answer, route):
        return None


class FakeRuleRepo:
    def match(self, text):
        return None


class FakeQuoteService:
    def __init__(self):
        self.draft_calls = 0

    def is_quote_request(self, text):
        return "多少钱" in text or "价格" in text

    def draft(self, request, memory, doc_candidates):
        self.draft_calls += 1
        products = (memory or {}).get("products", [])
        if "影视" in request.message:
            answer = "影视版会和团播版重新区分配置口径，GRA + 轨道也要按影视场景重新核价。"
        elif "GRA" in request.message.upper():
            answer = "GRA 适合团播起步方案，适合常见直播间自动运镜；空间更大或负载更高再看 EXT/PRO。"
        else:
            answer = f"报价草案：{products[-1] if products else '未确认型号'}"
        return {
            "answer": answer,
            "draft": {"sources": [], "recommended_products": products},
        }


class FakeRiskyQuoteService(FakeQuoteService):
    def draft(self, request, memory, doc_candidates):
        self.draft_calls += 1
        return {
            "answer": "我们保证现货，明天就能发。",
            "draft": {"sources": [], "recommended_products": []},
        }


class FakeLearningService:
    def maybe_learn_from_request(self, request):
        return {"detected": False}


class FakeKnowledgeGapService:
    def analyze(self, *args, **kwargs):
        return {"gaps": [], "suggested_questions": [], "needed_documents": []}


class FakeBehaviorConfig:
    def memory_policy(self):
        return {
            "previous_context_words": ["上次", "之前", "刚才", "前面", "上一轮", "那个", "这款"],
            "product_recall_words": ["什么机械臂"],
            "previous_product_anchor": True,
        }

    def fallback_policy(self):
        return {"active_gap_prompt_on_test_page": True}

    def sales_strategy_policy(self):
        return {}


class FakeAudit:
    def __init__(self):
        self.records = []

    def record(self, payload):
        self.records.append(payload)


class FakeQuoteArchive:
    def recent_for_customer(self, channel, user_id):
        return []

    def add_for_customer(self, channel, user_id, payload):
        return {"id": "quote_test", **payload}


class FakeObjectStore:
    def __init__(self):
        self.item = {}

    def load_object(self):
        return dict(self.item)

    def save_object(self, item):
        self.item = dict(item)


class FakeListStore:
    def __init__(self):
        self.items = []

    def load_list(self):
        return list(self.items)

    def save_list(self, items):
        self.items = list(items)


class FakePricingCatalog:
    def match_products(self, message):
        return []


class BrokenRiskPolicyService:
    def precheck(self, message, state=None):
        raise RuntimeError("risk precheck crashed")


class BrokenReadConversationStateStore:
    def get_state(self, conversation_id, channel="default"):
        raise RuntimeError("state read failed")

    def update_state(self, conversation_id, state_updates, channel="default"):
        return {}


class BrokenWriteConversationStateStore:
    def get_state(self, conversation_id, channel="default"):
        return {}

    def update_state(self, conversation_id, state_updates, channel="default"):
        raise RuntimeError("state write failed")


class BadReasonCode:
    def __str__(self):
        raise RuntimeError("bad reason code")


class ContextPlanningTests(unittest.TestCase):
    def make_chat(self, history_service=None, quote_service=None, risk_policy_service=None, conversation_state_store=None):
        chat = ChatService(
            settings=FakeSettings(),
            ollama=FakeOllama(),
            retrieval_service=RetrievalService(FakeSettings(), FakeOllama(), FakeVectorRepo()),
            rule_repo=FakeRuleRepo(),
            memory_service=FakeMemoryService(),
            audit_service=FakeAudit(),
            quote_service=quote_service or FakeQuoteService(),
            learning_service=FakeLearningService(),
            knowledge_gap_service=FakeKnowledgeGapService(),
            behavior_config_service=FakeBehaviorConfig(),
            conversation_history_service=history_service,
        )
        if risk_policy_service is not None:
            chat.risk_policy_service = risk_policy_service
        if conversation_state_store is not None:
            chat.conversation_state_store = conversation_state_store
        return chat

    def make_real_quote_service(self):
        policy = QuotePolicyService(FakeObjectStore())
        config_quote = ConfigurationQuoteService(
            QuoteCatalogService(FakeObjectStore()),
            policy,
            FakeListStore(),
        )
        return QuoteService(
            FakePricingCatalog(),
            policy,
            FakeQuoteArchive(),
            configuration_quote_service=config_quote,
        )

    def test_retrieval_cache_is_scoped_by_context(self):
        vector_repo = FakeVectorRepo()
        service = RetrievalService(FakeSettings(), FakeOllama(), vector_repo)

        first = service.retrieve("多少钱", "api", "u1", cache_context="conversation=a")
        second = service.retrieve("多少钱", "api", "u1", cache_context="conversation=a")
        third = service.retrieve("多少钱", "api", "u1", cache_context="conversation=b")

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertFalse(third.cache_hit)
        self.assertEqual(vector_repo.calls, 2)

    def test_retrieval_bypass_cache_for_contextual_query(self):
        vector_repo = FakeVectorRepo()
        service = RetrievalService(FakeSettings(), FakeOllama(), vector_repo)

        service.retrieve("这款多少钱", "api", "u1", cache_context="same", bypass_cache=True)
        result = service.retrieve("这款多少钱", "api", "u1", cache_context="same", bypass_cache=True)

        self.assertFalse(result.cache_hit)
        self.assertEqual(vector_repo.calls, 2)

    def test_followup_without_conversation_context_asks_for_product(self):
        chat = self.make_chat()
        response = chat.answer(ChatRequest(message="这款多少钱", channel="api"))

        self.assertEqual(response.route, "fallback")
        self.assertIn("确认", response.answer)
        self.assertFalse(response.metadata["context_plan"]["used_history"])
        self.assertEqual(response.metadata["context_plan"]["cache_policy"], "bypass_contextual")

    def test_configuration_lookup_does_not_trigger_quote_tool(self):
        quote_service = FakeQuoteService()
        chat = self.make_chat(quote_service=quote_service)

        response = chat.answer(ChatRequest(message="GRA 团播系统有什么配置", channel="api"))

        self.assertNotEqual(response.route, "quote_draft")
        self.assertEqual(quote_service.draft_calls, 0)
        self.assertEqual(response.metadata["intent_plan"]["intent"], "knowledge_lookup")

    def test_short_product_followup_uses_recent_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history)
            conversation_id = "followup_gra"

            first = chat.answer(ChatRequest(message="我们是做团播的给我推荐产品", channel="api", conversation_id=conversation_id))
            self.assertEqual(first.route, "quote_draft")

            response = chat.answer(ChatRequest(message="gra怎么样", channel="api", conversation_id=conversation_id))

            self.assertEqual(response.route, "quote_draft")
            self.assertIn("GRA", response.answer)
            self.assertIn("团播", response.answer)
            self.assertIn("适合", response.answer)
            self.assertNotIn("你可以直接说", response.answer)
            self.assertTrue(response.metadata["intent_plan"]["contextual_followup"])
            self.assertTrue(response.metadata["intent_plan"]["inherited_from_history"])
            self.assertIn("GRA", response.metadata["intent_plan"]["resolved_query"])

    def test_short_gra_followup_does_not_replay_generic_group_live_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history, quote_service=self.make_real_quote_service())
            conversation_id = "followup_gra_real"

            first = chat.answer(ChatRequest(message="我们是做团播的给我推荐产品", channel="api", conversation_id=conversation_id))
            self.assertEqual(first.route, "quote_draft")

            response = chat.answer(ChatRequest(message="gra怎么样", channel="api", conversation_id=conversation_id))

            self.assertEqual(response.route, "quote_draft")
            self.assertIn("接着刚才团播场景说", response.answer)
            self.assertIn("U-MOCO GRA", response.answer)
            self.assertIn("可以重点看", response.answer)
            self.assertNotIn("型号我不会直接拍死", response.answer)
            self.assertNotIn("你提到轨道/走位需求", response.answer)
            self.assertTrue(response.metadata["intent_plan"]["contextual_followup"])

    def test_version_followup_after_price_uses_recent_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history)
            conversation_id = "followup_film"

            first = chat.answer(ChatRequest(message="gra+8米轨道多少钱", channel="api", conversation_id=conversation_id))
            self.assertEqual(first.route, "quote_draft")

            response = chat.answer(ChatRequest(message="影视版本的呢", channel="api", conversation_id=conversation_id))

            self.assertEqual(response.route, "quote_draft")
            self.assertIn("影视版", response.answer)
            self.assertIn("重新", response.answer)
            self.assertNotIn("你可以直接说", response.answer)
            self.assertTrue(response.metadata["intent_plan"]["contextual_followup"])
            self.assertIn("影视版", response.metadata["intent_plan"]["resolved_query"])

    def test_short_product_question_without_history_clarifies_without_menu(self):
        chat = self.make_chat()

        response = chat.answer(ChatRequest(message="gra怎么样", channel="api"))

        self.assertEqual(response.route, "fallback")
        self.assertIn("适用场景", response.answer)
        self.assertIn("配置", response.answer)
        self.assertIn("价格", response.answer)
        self.assertNotIn("你可以直接说", response.answer)

    def test_context_plan_uses_history_product_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history)
            request = ChatRequest(message="GRA 团播系统有什么配置", channel="api", conversation_id="c1")
            fake_response = chat.answer(request)
            history.append_turn(request, fake_response)

            recent = history.recent_for_request(ChatRequest(message="这款多少钱", channel="api", conversation_id="c1"))
            plan = chat._build_context_plan("这款多少钱", ChatRequest(message="这款多少钱", channel="api", conversation_id="c1"), None, recent)

            self.assertTrue(plan["contextual_query"])
            self.assertIn("GRA", plan["anchors"])
            self.assertIn("GRA", plan["effective_query"])
            self.assertTrue(plan["bypass_cache"])

    def test_compare_primary_writes_history_shadow_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            response = ChatResponse(answer="主模型回答", route="quote_draft")
            primary = ChatRequest(
                message="我们是做团播的给我推荐产品",
                channel="api",
                conversation_id="compare1",
                metadata={"model_compare": True, "model_compare_role": "primary", "regression_test": True},
            )
            shadow = ChatRequest(
                message="EXT加6米轨道多少钱",
                channel="api",
                conversation_id="compare1",
                metadata={"model_compare": True, "model_compare_role": "shadow", "regression_test": True},
            )

            history.append_turn(primary, response)
            history.append_turn(shadow, ChatResponse(answer="影子模型回答", route="quote_draft"))
            rows = history.recent_for_request(ChatRequest(message="继续", channel="api", conversation_id="compare1"))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["message"], primary.message)

    def test_track_price_question_quotes_arm_track_and_motor_then_asks_site_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = QuoteCatalogService(JsonFileRepository(Path(tmp) / "quote_catalog.json"))
            policy = QuotePolicyService(JsonFileRepository(Path(tmp) / "quote_policy.json"))
            config_quote = ConfigurationQuoteService(
                catalog,
                policy,
                JsonFileRepository(Path(tmp) / "configuration_quote_feedback.json"),
            )
            quote_service = QuoteService(
                catalog_service=None,
                policy_service=policy,
                archive_service=FakeQuoteArchive(),
                configuration_quote_service=config_quote,
            )

            result = quote_service.draft(
                ChatRequest(message="团播EXT加6米轨道多少钱", channel="api", metadata={"regression_test": True}),
                {"scenario": "团播"},
                [],
            )
            answer = result["answer"]
            quote_items = result["draft"]["quote_items"]
            track_item = next(item for item in quote_items if item["name"] == "影视地面轨道")
            motor_item = next(item for item in quote_items if item["name"] == "轨道电机")

            self.assertIn("U-MOCO EXT 参考价：¥758,000", answer)
            self.assertIn("影视地面轨道：6米，参考小计 ¥93,000", answer)
            self.assertIn("轨道电机：默认随上轨道配置，参考小计 ¥78,000", answer)
            self.assertIn("参考合计约 ¥929,000", answer)
            self.assertIn("直播间层高", answer)
            self.assertIn("上轨道主要是为了横移、环绕、大范围走位", answer)
            self.assertNotIn("是否需要轨道电机", answer)
            self.assertEqual(track_item["quantity"], 6.0)
            self.assertEqual(track_item["reference_total"], "¥93,000")
            self.assertEqual(motor_item["quantity"], 1)
            self.assertEqual(motor_item["unit"], "套")

    def test_standalone_track_price_does_not_default_to_group_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = QuoteCatalogService(JsonFileRepository(Path(tmp) / "quote_catalog.json"))
            policy = QuotePolicyService(JsonFileRepository(Path(tmp) / "quote_policy.json"))
            config_quote = ConfigurationQuoteService(
                catalog,
                policy,
                JsonFileRepository(Path(tmp) / "configuration_quote_feedback.json"),
            )
            quote_service = QuoteService(
                catalog_service=None,
                policy_service=policy,
                archive_service=FakeQuoteArchive(),
                configuration_quote_service=config_quote,
            )

            result = quote_service.draft(
                ChatRequest(message="EXT加12米轨道多少钱", channel="api", metadata={"regression_test": True}),
                None,
                [],
            )

            answer = result["answer"]
            self.assertEqual(result["draft"]["configuration_quote"]["package"]["id"], "film_pro")
            self.assertIn("不会默认按团播来算", answer)
            self.assertIn("团播版、影视版还是广播版", answer)
            self.assertIn("U-MOCO EXT 参考价：¥758,000", answer)
            self.assertIn("影视地面轨道：12米，参考小计 ¥186,000", answer)
            self.assertIn("参考合计约 ¥1,022,000", answer)
            self.assertIn("现场层高", answer)
            self.assertNotIn("团播方案的价值", answer)
            self.assertNotIn("团播直播间", answer)

    def test_group_live_sales_strategy_recommends_without_quote_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history, quote_service=self.make_real_quote_service())

            response = chat.answer(ChatRequest(
                message="我们是做团播的，给我推荐一下你们的产品",
                channel="api",
                conversation_id="sales_group_live",
            ))

            self.assertEqual(response.route, "quote_draft")
            self.assertEqual(response.metadata["sales_stage"], "recommend")
            self.assertEqual(response.metadata["known_needs"]["scenario"], "group_live")
            self.assertIn("live_room_area", response.metadata["missing_fields"])
            self.assertIn("camera_count", response.metadata["missing_fields"])
            self.assertFalse(response.metadata["quote_readiness"]["ready"])
            self.assertIn("U-MOCO GRA", response.answer)
            self.assertIn("直播间面积", response.answer)
            self.assertNotIn("直播间大概多大", response.answer)

    def test_group_live_followup_inherits_needs_for_more_specific_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history, quote_service=self.make_real_quote_service())
            conversation_id = "sales_followup_needs"

            chat.answer(ChatRequest(
                message="我们是做团播的，给我推荐一下你们的产品",
                channel="api",
                conversation_id=conversation_id,
            ))
            response = chat.answer(ChatRequest(
                message="直播间大概30平，两台相机",
                channel="api",
                conversation_id=conversation_id,
            ))

            self.assertEqual(response.route, "quote_draft")
            self.assertEqual(response.metadata["sales_stage"], "recommend")
            self.assertEqual(response.metadata["known_needs"]["scenario"], "group_live")
            self.assertEqual(response.metadata["known_needs"]["live_room_area"], "30")
            self.assertEqual(response.metadata["known_needs"]["camera_count"], "2")
            self.assertNotIn("你是什么场景", response.answer)

    def test_price_followup_not_quote_ready_gives_reference_configuration_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history, quote_service=self.make_real_quote_service())
            conversation_id = "sales_price_followup"

            chat.answer(ChatRequest(
                message="我们是做团播的，给我推荐一下你们的产品",
                channel="api",
                conversation_id=conversation_id,
            ))
            chat.answer(ChatRequest(
                message="直播间大概30平，两台相机",
                channel="api",
                conversation_id=conversation_id,
            ))
            response = chat.answer(ChatRequest(
                message="大概多少钱",
                channel="api",
                conversation_id=conversation_id,
            ))

            self.assertEqual(response.route, "quote_draft")
            self.assertEqual(response.metadata["sales_stage"], "recommend")
            self.assertFalse(response.metadata["quote_readiness"]["ready"])
            self.assertIn("参考配置方向", response.answer)
            self.assertIn("正式价格", response.answer)
            self.assertIn("预算区间", response.answer)

    def test_after_sales_question_is_direct_answer_strategy_not_sales_flow(self):
        chat = self.make_chat()

        response = chat.answer(ChatRequest(message="电池保修多久？", channel="api"))

        self.assertNotEqual(response.route, "quote_draft")
        self.assertEqual(response.metadata["sales_stage"], "direct_answer")
        self.assertTrue(response.metadata["sales_plan"]["should_direct_answer"])

    def test_contract_confirmation_requires_handoff_strategy(self):
        chat = self.make_chat()

        response = chat.answer(ChatRequest(message="合同能直接确认吗？", channel="api"))

        self.assertEqual(response.route, "handoff")
        self.assertTrue(response.need_human)
        self.assertEqual(response.metadata["sales_stage"], "handoff")

    def test_contextual_followups_use_sales_context_and_bypass_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            chat = self.make_chat(history, quote_service=self.make_real_quote_service())
            conversation_id = "sales_contextual_followups"

            chat.answer(ChatRequest(
                message="我们是做团播的，给我推荐一下你们的产品",
                channel="api",
                conversation_id=conversation_id,
            ))
            first = chat.answer(ChatRequest(
                message="这个适合多大直播间？",
                channel="api",
                conversation_id=conversation_id,
            ))
            second = chat.answer(ChatRequest(
                message="那要不要轨道？",
                channel="api",
                conversation_id=conversation_id,
            ))

            self.assertEqual(first.metadata["context_plan"]["cache_policy"], "bypass_contextual")
            self.assertEqual(second.metadata["context_plan"]["cache_policy"], "bypass_contextual")
            self.assertEqual(first.metadata["sales_stage"], "recommend")
            self.assertEqual(second.metadata["sales_stage"], "recommend")

    def test_blocked_contract_question_short_circuits_to_handoff(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())

        response = chat.answer(ChatRequest(message="合同能直接确认吗？", channel="api"))

        self.assertEqual(response.route, "handoff")
        self.assertTrue(response.need_human)
        self.assertIn(response.metadata["risk_plan"]["risk_level"], {"blocked", "high"})
        if response.metadata["risk_plan"]["risk_level"] == "blocked":
            self.assertEqual(response.matched_rule, "RiskPolicyService")
            self.assertIn("risk_blocked_handoff", response.metadata.get("decision_trace", []))

    def test_lowest_price_behavior_follows_risk_level_without_wrong_forcing(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())

        response = chat.answer(ChatRequest(message="最低价多少？", channel="api"))
        risk_level = response.metadata["risk_plan"]["risk_level"]

        self.assertIn(risk_level, {"blocked", "high"})
        if risk_level == "blocked":
            self.assertEqual(response.route, "handoff")
            self.assertTrue(response.need_human)
        else:
            self.assertIn("risk_plan", response.metadata)

    def test_medium_price_question_records_risk_plan_but_does_not_short_circuit(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())

        response = chat.answer(ChatRequest(message="大概多少钱？", channel="api"))

        self.assertIn("risk_precheck", response.metadata)
        self.assertIn("risk_plan", response.metadata)
        self.assertEqual(response.metadata["risk_plan"]["risk_level"], "medium")
        self.assertNotEqual(response.route, "handoff")

    def test_warranty_question_is_not_blocked_by_risk_precheck(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())

        response = chat.answer(ChatRequest(message="电池保修多久？", channel="api"))

        self.assertIn("risk_plan", response.metadata)
        self.assertEqual(response.metadata["risk_plan"]["risk_level"], "low")
        self.assertNotEqual(response.route, "handoff")

    def test_risk_precheck_exception_does_not_break_chat_flow(self):
        chat = self.make_chat(risk_policy_service=BrokenRiskPolicyService())

        response = chat.answer(ChatRequest(message="大概多少钱？", channel="api"))

        self.assertIn("risk_precheck_error", response.metadata)
        self.assertIn(response.route, {"quote_draft", "faq", "doc", "fallback"})

    def test_state_observation_adds_before_and_after_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)

            response = chat.answer(ChatRequest(message="我们是做团播的给我推荐产品", channel="api", conversation_id="state_obs_1"))

            self.assertIn("conversation_state_before", response.metadata)
            self.assertIn("conversation_state_after", response.metadata)

    def test_new_conversation_has_default_state_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)

            response = chat.answer(ChatRequest(message="你好", channel="api", conversation_id="new_state_user"))

            self.assertEqual(response.metadata["conversation_state_before"].get("stage", ""), "")
            self.assertIn("known_needs", response.metadata["conversation_state_before"])

    def test_state_after_tracks_last_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)

            response = chat.answer(ChatRequest(message="电池保修多久？", channel="api", conversation_id="route_state_user"))

            self.assertEqual(response.metadata["conversation_state_after"]["last_assistant_route"], response.route)

    def test_need_human_updates_handoff_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)

            response = chat.answer(ChatRequest(message="合同能直接确认吗？", channel="api", conversation_id="need_human_state_user"))

            self.assertTrue(response.need_human)
            self.assertTrue(response.metadata["conversation_state_after"]["human_handoff_required"])

    def test_sales_known_needs_written_to_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)

            response = chat.answer(ChatRequest(message="我们是做团播的，直播间30平，两台相机", channel="api", conversation_id="known_needs_user"))

            known = response.metadata["conversation_state_after"].get("known_needs", {})
            self.assertIn("scenario", known)
            self.assertEqual(known.get("scenario"), "group_live")
            self.assertEqual(known.get("live_room_area"), "30")
            self.assertEqual(known.get("camera_count"), "2")

    def test_conversation_state_isolation_by_conversation_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)

            first = chat.answer(ChatRequest(message="我们是做团播的给我推荐产品", channel="api", conversation_id="conv_a"))
            second = chat.answer(ChatRequest(message="我们做影视广告，推荐一下", channel="api", conversation_id="conv_b"))

            self.assertNotEqual(
                first.metadata["conversation_state_after"].get("known_needs", {}).get("scenario"),
                second.metadata["conversation_state_after"].get("known_needs", {}).get("scenario"),
            )

    def test_state_read_error_does_not_break_flow_and_sets_metadata(self):
        chat = self.make_chat(
            risk_policy_service=RiskPolicyService(),
            conversation_state_store=BrokenReadConversationStateStore(),
        )

        response = chat.answer(ChatRequest(message="大概多少钱？", channel="api", conversation_id="read_err_user"))

        self.assertIn("conversation_state_error", response.metadata)
        self.assertIn(response.route, {"quote_draft", "faq", "doc", "fallback", "handoff", "identity"})

    def test_state_write_error_does_not_break_flow_and_sets_metadata(self):
        chat = self.make_chat(
            risk_policy_service=RiskPolicyService(),
            conversation_state_store=BrokenWriteConversationStateStore(),
        )

        response = chat.answer(ChatRequest(message="大概多少钱？", channel="api", conversation_id="write_err_user"))

        self.assertIn("conversation_state_update_error", response.metadata)
        self.assertIn(response.route, {"quote_draft", "faq", "doc", "fallback", "handoff", "identity"})

    def test_state_observation_does_not_change_answer_route_or_need_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            conversation_id = "observation_compare_user"
            request = ChatRequest(message="大概多少钱？", channel="api", conversation_id=conversation_id)

            chat_without_state = self.make_chat(risk_policy_service=RiskPolicyService())
            baseline = chat_without_state.answer(request)

            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            chat_with_state = self.make_chat(risk_policy_service=RiskPolicyService(), conversation_state_store=state_store)
            observed = chat_with_state.answer(request)

            self.assertEqual(observed.answer, baseline.answer)
            self.assertEqual(observed.route, baseline.route)
            self.assertEqual(observed.need_human, baseline.need_human)

    def test_cache_policy_enforce_contextual_followup_sets_final_bypass_true(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(
            message="电池保修多久？",
            channel="api",
            metadata={"cache_policy_metadata": {"reason_codes": ["contextual_followup"]}},
        ))

        self.assertTrue(response.metadata["cache_policy_enforce_applied"])
        self.assertTrue(response.metadata["final_bypass_cache"])
        self.assertEqual(response.metadata["cache_policy_enforce_mode"], "minimal")

    def test_cache_policy_enforce_risk_sensitive_sets_final_bypass_true(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(
            message="电池保修多久？",
            channel="api",
            metadata={"cache_policy_metadata": {"reason_codes": ["risk_sensitive"]}},
        ))

        self.assertTrue(response.metadata["cache_policy_enforce_applied"])
        self.assertTrue(response.metadata["final_bypass_cache"])

    def test_cache_policy_enforce_pronoun_reference_sets_final_bypass_true(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(
            message="电池保修多久？",
            channel="api",
            metadata={"cache_policy_metadata": {"reason_codes": ["pronoun_reference"]}},
        ))

        self.assertTrue(response.metadata["cache_policy_enforce_applied"])
        self.assertTrue(response.metadata["final_bypass_cache"])

    def test_cache_policy_quote_intent_only_remains_observation(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(
            message="你好",
            channel="api",
            metadata={"cache_policy_metadata": {"reason_codes": ["quote_intent"]}},
        ))

        self.assertFalse(response.metadata["cache_policy_enforce_applied"])
        self.assertFalse(response.metadata["final_bypass_cache"])
        self.assertEqual(response.metadata["cache_policy_enforce_skipped_reason"], "no_enforce_reason_codes")

    def test_existing_true_bypass_is_not_downgraded(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(
            message="这款多少钱",
            channel="api",
            metadata={"cache_policy_metadata": {"reason_codes": ["quote_intent"]}},
        ))

        self.assertTrue(response.metadata["original_bypass_cache"])
        self.assertTrue(response.metadata["final_bypass_cache"])
        self.assertFalse(response.metadata["cache_policy_enforce_applied"])

    def test_missing_cache_policy_metadata_keeps_original_behavior(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(message="电池保修多久？", channel="api"))

        self.assertFalse(response.metadata["cache_policy_enforce_applied"])
        self.assertFalse(response.metadata["original_bypass_cache"])
        self.assertFalse(response.metadata["final_bypass_cache"])
        self.assertIn("cache_policy_metadata", response.metadata)
        self.assertEqual(response.metadata["cache_policy_enforce_skipped_reason"], "no_enforce_reason_codes")

    def test_cache_policy_enforce_exception_keeps_original_behavior(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(
            message="电池保修多久？",
            channel="api",
            metadata={"cache_policy_metadata": {"reason_codes": [BadReasonCode()]}},
        ))

        self.assertIn("cache_policy_enforce_error", response.metadata)
        self.assertFalse(response.metadata["cache_policy_enforce_applied"])
        self.assertFalse(response.metadata["original_bypass_cache"])
        self.assertFalse(response.metadata["final_bypass_cache"])

    def test_followup_price_question_triggers_real_bypass_true(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(message="那大概多少钱？", channel="api", conversation_id="bypass_followup"))

        self.assertTrue(response.metadata["final_bypass_cache"])

    def test_low_risk_after_sales_not_forced_bypass(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService())
        response = chat.answer(ChatRequest(message="电池保修多久？", channel="api", conversation_id="no_force_bypass"))

        self.assertFalse(response.metadata["final_bypass_cache"])

    def test_audit_record_uses_final_response_after_blocked_post_rule_enforce(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = ConversationHistoryService(JsonFileRepository(Path(tmp) / "conversation_history.json"))
            state_store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            audit = FakeAudit()
            chat = ChatService(
                settings=FakeSettings(),
                ollama=FakeOllama(),
                retrieval_service=RetrievalService(FakeSettings(), FakeOllama(), FakeVectorRepo()),
                rule_repo=FakeRuleRepo(),
                memory_service=FakeMemoryService(),
                audit_service=audit,
                quote_service=FakeRiskyQuoteService(),
                learning_service=FakeLearningService(),
                knowledge_gap_service=FakeKnowledgeGapService(),
                behavior_config_service=FakeBehaviorConfig(),
                conversation_history_service=history,
            )
            chat.risk_policy_service = RiskPolicyService()
            chat.conversation_state_store = state_store
            chat.post_rule_check_service = PostRuleCheckService()

            conversation_id = "blocked_post_rule_persist_consistency"
            request = ChatRequest(message="报价大概多少钱？", channel="api", conversation_id=conversation_id)
            response = ChatResponse(
                answer="我们保证现货，明天就能发。",
                route="quote_draft",
                need_human=False,
                channel="api",
                conversation_id=conversation_id,
                metadata={
                    "risk_plan": {"risk_level": "high", "need_human": False},
                    "conversation_state_before": {},
                },
            )
            chat._audit("req_post_rule_consistency", request, response)

            self.assertTrue(response.metadata["post_rule_check"]["blocked"])
            self.assertTrue(response.metadata["post_rule_enforce_applied"])
            self.assertTrue(response.need_human)
            self.assertEqual(response.answer, response.metadata["post_rule_check"]["safe_answer"])
            self.assertEqual(response.metadata.get("original_answer"), "我们保证现货，明天就能发。")

            turns = history.recent_for_request(ChatRequest(message="继续", channel="api", conversation_id=conversation_id))
            self.assertTrue(turns)
            self.assertEqual(turns[-1]["answer"], response.answer)
            self.assertEqual(turns[-1]["route"], response.route)

            self.assertIn("conversation_state_after", response.metadata)
            self.assertTrue(response.metadata["conversation_state_after"]["human_handoff_required"])
            self.assertEqual(response.metadata["conversation_state_after"]["last_assistant_route"], response.route)

            self.assertTrue(audit.records)
            latest_audit = audit.records[-1]
            self.assertEqual(latest_audit["answer"], response.answer)
            self.assertEqual(latest_audit["route"], response.route)
            self.assertTrue(latest_audit["need_human"])

    def test_medium_high_post_rule_stays_observation_without_enforce(self):
        chat = self.make_chat(risk_policy_service=RiskPolicyService(), quote_service=FakeQuoteService())
        chat.post_rule_check_service = PostRuleCheckService()

        response = chat.answer(ChatRequest(message="大概多少钱？", channel="api", conversation_id="medium_observation_only"))

        self.assertIn("post_rule_check", response.metadata)
        self.assertTrue(response.metadata["post_rule_check"]["need_rewrite"])
        self.assertFalse(response.metadata["post_rule_check"]["blocked"])
        self.assertFalse(response.metadata["post_rule_enforce_applied"])
        self.assertNotEqual(response.answer, "")


if __name__ == "__main__":
    unittest.main()
