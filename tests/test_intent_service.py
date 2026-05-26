import unittest

from support_app.services.intent_service import IntentService


class IntentServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = IntentService()

    def test_scene_word_alone_does_not_trigger_quote(self):
        result = self.service.classify_rules("团播")

        self.assertEqual(result.intent, "clarify")
        self.assertFalse(result.needs_quote_tool)
        self.assertIn("团播", result.scenario_terms)
        self.assertLess(result.confidence, 0.7)

    def test_group_live_recommendation_is_quote_recommendation(self):
        result = self.service.classify_rules("我们是做团播的给我推荐产品")

        self.assertEqual(result.intent, "quote_recommendation")
        self.assertTrue(result.needs_quote_tool)
        self.assertIn("推荐", result.action_terms)

    def test_sendable_group_live_configuration_sheet(self):
        result = self.service.classify_rules("给我写一份寄出团播配置单")

        self.assertEqual(result.intent, "quote_configuration_sheet")
        self.assertTrue(result.needs_quote_tool)
        self.assertEqual(result.route_policy, "quote_draft")

    def test_configuration_question_is_knowledge_lookup(self):
        result = self.service.classify_rules("GRA 团播系统有什么配置")

        self.assertEqual(result.intent, "knowledge_lookup")
        self.assertFalse(result.needs_quote_tool)
        self.assertTrue(result.needs_retrieval)
        self.assertIn("GRA", result.product_anchors)

    def test_track_price_question_is_quote_price(self):
        result = self.service.classify_rules("EXT 加 6 米轨道多少钱")

        self.assertEqual(result.intent, "quote_price")
        self.assertTrue(result.needs_quote_tool)
        self.assertIn("EXT", result.product_anchors)

    def test_warranty_question_is_knowledge_lookup(self):
        result = self.service.classify_rules("MINI 保修多久")

        self.assertEqual(result.intent, "knowledge_lookup")
        self.assertFalse(result.needs_quote_tool)

    def test_commercial_commitment_is_handoff(self):
        result = self.service.classify_rules("最低价一定能给吗")

        self.assertEqual(result.intent, "handoff")
        self.assertFalse(result.needs_quote_tool)
        self.assertIn("commercial_commitment", result.risk_flags)

    def test_short_followup_inherits_recent_history(self):
        result = self.service.classify_rules("gra怎么样", {
            "history": [{"message": "我们是做团播的给我推荐产品", "answer": "一般先看 U-MOCO GRA 团播版。", "route": "quote_draft"}],
            "last_route": "quote_draft",
            "last_message": "我们是做团播的给我推荐产品",
            "last_answer": "一般先看 U-MOCO GRA 团播版。",
            "history_product_anchors": ["GRA"],
            "history_anchor_summary": "产品锚点：GRA",
        })

        self.assertEqual(result.intent, "memory_followup")
        self.assertTrue(result.contextual_followup)
        self.assertTrue(result.inherited_from_history)
        self.assertTrue(result.needs_quote_tool)
        self.assertIn("GRA", result.resolved_query)


if __name__ == "__main__":
    unittest.main()
