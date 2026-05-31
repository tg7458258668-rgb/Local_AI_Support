import copy
import unittest

from support_app.services.understand_plan_adapter import UnderstandPlanAdapter


class UnderstandPlanAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = UnderstandPlanAdapter()

    def test_empty_inputs_return_complete_structure(self):
        plan = self.adapter.build(message="")

        self.assertEqual(plan["intent"]["primary_intent"], "fallback")
        self.assertIn("context", plan)
        self.assertIn("sales", plan)
        self.assertIn("risk", plan)
        self.assertIn("state_ref", plan)
        self.assertIn("cache_hints", plan)

    def test_intent_maps_to_primary_intent(self):
        plan = self.adapter.build(message="test", intent_plan={"intent": "knowledge_lookup"})
        self.assertEqual(plan["intent"]["primary_intent"], "knowledge_lookup")

    def test_primary_intent_takes_priority_over_intent(self):
        plan = self.adapter.build(
            message="test",
            intent_plan={"primary_intent": "quote_inquiry", "intent": "knowledge_lookup"},
        )
        self.assertEqual(plan["intent"]["primary_intent"], "quote_inquiry")

    def test_context_resolved_query_priority(self):
        plan = self.adapter.build(
            message="原始问题",
            intent_plan={"resolved_query": "intent解析问题"},
            context_plan={"resolved_query": "context解析问题"},
        )
        self.assertEqual(plan["context"]["resolved_query"], "context解析问题")

    def test_product_anchors_from_intent_plan(self):
        plan = self.adapter.build(message="test", intent_plan={"product_anchors": ["GRA", "PRO"]})
        self.assertEqual(plan["context"]["product_anchors"], ["GRA", "PRO"])
        self.assertEqual(plan["context"]["product_anchor"], "GRA")

    def test_product_anchor_falls_back_to_state(self):
        plan = self.adapter.build(message="test", conversation_state={"product_anchor": "U-MOCO GRA"})
        self.assertEqual(plan["context"]["product_anchor"], "U-MOCO GRA")
        self.assertEqual(plan["context"]["product_anchors"], ["U-MOCO GRA"])

    def test_known_needs_merge_sales_overrides_state(self):
        plan = self.adapter.build(
            message="test",
            conversation_state={"known_needs": {"room_size": "30平", "camera_count": 1}},
            sales_plan={"known_needs": {"camera_count": 2}},
        )
        self.assertEqual(plan["sales"]["known_needs"]["room_size"], "30平")
        self.assertEqual(plan["sales"]["known_needs"]["camera_count"], 2)

    def test_missing_fields_from_sales_plan(self):
        plan = self.adapter.build(
            message="test",
            conversation_state={"missing_fields": ["budget"]},
            sales_plan={"missing_fields": ["camera_count"]},
        )
        self.assertEqual(plan["sales"]["missing_fields"], ["camera_count"])

    def test_quote_readiness_prefers_sales_plan_then_state(self):
        plan_a = self.adapter.build(
            message="test",
            conversation_state={"quote_readiness": "partial"},
            sales_plan={"quote_readiness": "ready"},
        )
        plan_b = self.adapter.build(message="test", conversation_state={"quote_readiness": "partial"})
        self.assertEqual(plan_a["sales"]["quote_readiness"], "ready")
        self.assertEqual(plan_b["sales"]["quote_readiness"], "partial")

    def test_risk_plan_maps_to_risk_section(self):
        plan = self.adapter.build(
            message="test",
            risk_plan={
                "risk_level": "high",
                "need_human": True,
                "risk_reasons": ["库存敏感"],
                "matched_keywords": ["库存"],
            },
        )
        self.assertEqual(plan["risk"]["risk_level"], "high")
        self.assertTrue(plan["risk"]["need_human"])
        self.assertEqual(plan["risk"]["risk_reasons"], ["库存敏感"])
        self.assertEqual(plan["risk"]["matched_keywords"], ["库存"])

    def test_contextual_followup_triggers_bypass_cache(self):
        plan = self.adapter.build(
            message="test",
            context_plan={"contextual_followup": True},
        )
        self.assertTrue(plan["cache_hints"]["should_bypass_cache"])
        self.assertIn("contextual_followup", plan["cache_hints"]["reason_codes"])

    def test_quote_intent_triggers_quote_intent_reason(self):
        plan = self.adapter.build(message="test", intent_plan={"primary_intent": "quote_inquiry"})
        self.assertTrue(plan["cache_hints"]["should_bypass_cache"])
        self.assertIn("quote_intent", plan["cache_hints"]["reason_codes"])

    def test_high_risk_triggers_risk_sensitive_reason(self):
        plan = self.adapter.build(message="test", risk_plan={"risk_level": "high"})
        self.assertTrue(plan["cache_hints"]["should_bypass_cache"])
        self.assertIn("risk_sensitive", plan["cache_hints"]["reason_codes"])

    def test_track_followup_message_triggers_pronoun_or_price_track_reason(self):
        plan = self.adapter.build(message="那要不要轨道")
        self.assertTrue(plan["cache_hints"]["should_bypass_cache"])
        self.assertTrue(
            "pronoun_reference" in plan["cache_hints"]["reason_codes"]
            or "price_or_track_question" in plan["cache_hints"]["reason_codes"]
        )

    def test_build_does_not_mutate_input_dicts(self):
        intent = {"intent": "quote_inquiry", "product_anchors": ["GRA"], "risk_flags": ["commercial_commitment"]}
        sales = {"known_needs": {"scenario": "group_live"}, "missing_fields": ["budget"]}
        context = {"resolved_query": "解析问题", "contextual_followup": True}
        state = {"product_anchor": "GRA", "known_needs": {"camera_count": 2}}
        risk = {"risk_level": "medium", "risk_reasons": ["价格敏感"]}

        before = {
            "intent": copy.deepcopy(intent),
            "sales": copy.deepcopy(sales),
            "context": copy.deepcopy(context),
            "state": copy.deepcopy(state),
            "risk": copy.deepcopy(risk),
        }
        self.adapter.build(
            message="测试",
            intent_plan=intent,
            sales_plan=sales,
            context_plan=context,
            conversation_state=state,
            risk_plan=risk,
        )

        self.assertEqual(intent, before["intent"])
        self.assertEqual(sales, before["sales"])
        self.assertEqual(context, before["context"])
        self.assertEqual(state, before["state"])
        self.assertEqual(risk, before["risk"])


if __name__ == "__main__":
    unittest.main()
