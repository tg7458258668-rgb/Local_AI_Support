import unittest

from support_app.services.cache_policy_metadata_service import CachePolicyMetadataService


class CachePolicyMetadataServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = CachePolicyMetadataService()

    def test_low_risk_direct_answer_defaults(self):
        result = self.service.build(
            message="电池保修多久？",
            understand_plan={
                "context": {"is_followup": False},
                "intent": {"primary_intent": "knowledge_lookup"},
                "sales": {"stage": "direct_answer"},
                "risk": {"risk_level": "low"},
                "cache_hints": {"should_bypass_cache": False},
            },
        )
        self.assertFalse(result["should_bypass_cache"])
        self.assertFalse(result["allow_final_answer_cache"])

    def test_understand_cache_hint_triggers_reason(self):
        result = self.service.build(
            message="test",
            understand_plan={"cache_hints": {"should_bypass_cache": True}},
        )
        self.assertTrue(result["should_bypass_cache"])
        self.assertIn("understand_cache_hint", result["reason_codes"])

    def test_contextual_followup_triggers_reason(self):
        result = self.service.build(
            message="test",
            understand_plan={"context": {"is_followup": True}},
        )
        self.assertTrue(result["should_bypass_cache"])
        self.assertIn("contextual_followup", result["reason_codes"])

    def test_quote_intent_triggers_reason(self):
        result = self.service.build(
            message="报价",
            understand_plan={"intent": {"primary_intent": "quote_price"}},
        )
        self.assertTrue(result["should_bypass_cache"])
        self.assertIn("quote_intent", result["reason_codes"])

    def test_risk_sensitive_triggers_reason(self):
        result = self.service.build(
            message="库存",
            risk_plan={"risk_level": "high"},
        )
        self.assertTrue(result["should_bypass_cache"])
        self.assertIn("risk_sensitive", result["reason_codes"])

    def test_handoff_state_triggers_reason(self):
        result = self.service.build(
            message="test",
            conversation_state_after={"human_handoff_required": True},
        )
        self.assertTrue(result["should_bypass_cache"])
        self.assertIn("handoff_state", result["reason_codes"])

    def test_track_question_triggers_pronoun_or_price_track_reason(self):
        result = self.service.build(message="那要不要轨道")
        self.assertTrue(result["should_bypass_cache"])
        self.assertTrue(
            "pronoun_reference" in result["reason_codes"]
            or "price_or_track_question" in result["reason_codes"]
        )

    def test_would_change_behavior_when_current_false_but_should_true(self):
        result = self.service.build(
            message="报价",
            understand_plan={"intent": {"primary_intent": "quote_inquiry"}},
            current_retrieval_bypass_cache=False,
        )
        self.assertTrue(result["should_bypass_cache"])
        self.assertTrue(result["would_change_current_behavior"])
        self.assertEqual(result["current_retrieval_bypass_cache"], False)


if __name__ == "__main__":
    unittest.main()
