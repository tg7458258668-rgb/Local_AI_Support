import unittest

from support_app.services.post_rule_check_service import PostRuleCheckService


class PostRuleCheckServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = PostRuleCheckService()

    def test_empty_answer_requires_rewrite(self):
        result = self.service.check(route="faq", answer="   ")

        self.assertFalse(result["passed"])
        self.assertTrue(result["need_rewrite"])
        self.assertTrue(result["safe_answer"])

    def test_low_risk_direct_answer_after_sales_passes(self):
        result = self.service.check(
            route="direct_answer",
            answer="电池保修为3个月。",
            risk_plan={"risk_level": "low"},
        )

        self.assertTrue(result["passed"])
        self.assertFalse(result["blocked"])
        self.assertFalse(result["need_rewrite"])

    def test_medium_risk_without_disclaimer_needs_rewrite(self):
        result = self.service.check(
            route="quote_draft",
            answer="这套方案大概5万元。",
            risk_plan={"risk_level": "medium"},
        )

        self.assertFalse(result["passed"])
        self.assertTrue(result["need_rewrite"])
        self.assertTrue(result["need_human"])

    def test_high_risk_with_guarantee_stock_is_blocked(self):
        result = self.service.check(
            route="quote_draft",
            answer="我们保证现货，明天就能发。",
            risk_plan={"risk_level": "high"},
        )

        self.assertTrue(result["blocked"])
        self.assertTrue(result["need_rewrite"])

    def test_lowest_price_is_blocked(self):
        result = self.service.check(
            route="quote_draft",
            answer="最低价就是4万，今天就能定。",
            risk_plan={"risk_level": "medium"},
        )

        self.assertTrue(result["blocked"])
        self.assertTrue(result["need_rewrite"])

    def test_handoff_without_human_guidance_needs_rewrite(self):
        result = self.service.check(
            route="handoff",
            answer="你的需求我知道了。",
            risk_plan={"risk_level": "blocked"},
        )

        self.assertTrue(result["need_rewrite"])
        self.assertTrue(result["safe_answer"])

    def test_handoff_with_human_guidance_passes(self):
        result = self.service.check(
            route="handoff",
            answer="这个问题需要销售同事人工确认，我先帮你整理需求。",
            risk_plan={"risk_level": "blocked"},
        )

        self.assertTrue(result["passed"])
        self.assertFalse(result["need_rewrite"])

    def test_quote_draft_without_final_confirmation_needs_rewrite(self):
        result = self.service.check(
            route="quote_draft",
            answer="推荐你选GRA加轨道。",
            risk_plan={"risk_level": "low"},
        )

        self.assertTrue(result["need_rewrite"])

    def test_quote_draft_with_confirmation_passes(self):
        result = self.service.check(
            route="quote_draft",
            answer="这套可以先按5万元参考，具体价格以销售确认为准。",
            risk_plan={"risk_level": "medium"},
            metadata={"quote_source": "catalog_v1"},
        )

        self.assertTrue(result["passed"])
        self.assertFalse(result["need_rewrite"])

    def test_medium_risk_price_without_source_adds_warning(self):
        result = self.service.check(
            route="quote_draft",
            answer="预算大概5万元。",
            risk_plan={"risk_level": "medium"},
            metadata={},
        )

        self.assertIn("price_number_without_source", result["warnings"])
        self.assertTrue(result["need_human"])


if __name__ == "__main__":
    unittest.main()
