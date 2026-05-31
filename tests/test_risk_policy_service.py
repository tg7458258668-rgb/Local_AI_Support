import json
import unittest
from pathlib import Path

from support_app.services.risk_policy_service import RiskPolicyService


class RiskPolicyServiceTests(unittest.TestCase):
    @staticmethod
    def _load_policy_from_file() -> dict:
        path = Path("data/agent_behavior_rules.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_contract_confirmation_is_handoff(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.precheck("合同能直接确认吗？")

        self.assertIn(result["risk_level"], {"blocked", "high"})
        self.assertEqual(result["route"], "handoff")
        self.assertTrue(result["need_human"])

    def test_lowest_price_is_blocked_or_high(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.precheck("最低价多少？")

        self.assertIn(result["risk_level"], {"blocked", "high"})
        self.assertTrue(result["need_human"])

    def test_inventory_question_is_high(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.precheck("库存有没有？")

        self.assertEqual(result["risk_level"], "high")
        self.assertTrue(result["need_human"])

    def test_delivery_question_is_high(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.evaluate("这个月底能不能交付？")

        self.assertEqual(result["risk_level"], "high")
        self.assertTrue(result["need_human"])

    def test_price_question_is_medium_with_scope_limit(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.evaluate("大概多少钱？")

        self.assertEqual(result["risk_level"], "medium")
        self.assertIn("不能承诺最终价格", result["allowed_answer_scope"])
        self.assertTrue(result["need_human"])

    def test_warranty_question_is_low(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.evaluate("电池保修多久？")

        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["need_human"])

    def test_mixed_risk_message_contains_multiple_points(self):
        service = RiskPolicyService(self._load_policy_from_file())

        result = service.evaluate("合同最低价能不能保证月底交付？")

        self.assertIn(result["risk_level"], {"blocked", "high"})
        self.assertTrue(result["need_human"])
        self.assertGreaterEqual(len(result["matched_keywords"]), 2)

    def test_missing_or_empty_config_uses_default_rules(self):
        service_no_config = RiskPolicyService(None)
        service_empty = RiskPolicyService({})
        service_invalid = RiskPolicyService({"risk_policy": "bad"})

        result_a = service_no_config.precheck("合同能直接确认吗？")
        result_b = service_empty.precheck("库存有没有？")
        result_c = service_invalid.evaluate("大概多少钱？")

        self.assertIn(result_a["risk_level"], {"blocked", "high"})
        self.assertEqual(result_b["risk_level"], "high")
        self.assertEqual(result_c["risk_level"], "medium")


if __name__ == "__main__":
    unittest.main()
