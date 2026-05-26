import unittest

from support_app.schemas import ChatRequest
from support_app.services.quote_service import QuoteService


class FakeCatalogService:
    def get(self):
        return {
            "products": [
                {"product": "U-MOCO GRA + EXT", "version": "历史组合单", "base_price": "¥508,000"},
                {"product": "U-MOCO GRA", "version": "旗舰版", "base_price": "¥601,000", "source": "GRA旗舰版.pages"},
                {"product": "U-MOCO EXT", "version": "旗舰版", "base_price": "¥818,000", "source": "EXT旗舰版.pages"},
                {"product": "U-MOCO PRO", "version": "旗舰版", "base_price": "¥778,000", "source": "PRO旗舰版.pages"},
                {"product": "U-MOCO MINI", "version": "专业版", "base_price": "¥328,000"},
            ]
        }

    def match_products(self, _message):
        return []


class FakePolicyService:
    def get(self):
        return {"approval_required": ["优惠价", "交付时间", "合同条款", "特殊定制"]}


class FakeArchiveService:
    def __init__(self):
        self.saved = []

    def recent_for_customer(self, _channel, _user_id):
        return []

    def add_for_customer(self, _channel, _user_id, payload):
        self.saved.append(payload)
        return {"id": "quote_1", **payload}


class FakeConfigurationQuoteService:
    def draft(self, _message, _scenario, _metadata):
        return {
            "message": _message,
            "summary": "已按团播版生成单条 GRA 配置草稿。",
            "package": {"id": "group_live", "name": "团播版"},
            "recommended_arm": {"id": "GRA", "name": "U-MOCO GRA", "reference_price": "¥601,000"},
            "alternative_arms": [
                {"id": "EXT", "name": "U-MOCO EXT", "reference_price": "¥818,000"},
                {"id": "PRO", "name": "U-MOCO PRO", "reference_price": "¥778,000"},
            ],
            "needs": {"scenario": "group_live"},
            "modules": [
                {
                    "name": "U-MOCO GRA",
                    "role": "required",
                    "module_type": "core_arm",
                    "reference_price": "¥601,000",
                    "source": "产品价目",
                    "reason": "团播选型需按面积、效果和负载确认。",
                },
                {"name": "U-MOCO OS Pro", "role": "required", "module_type": "software", "reason": "软件运镜。"},
                {"name": "U-MOCO Live", "role": "required", "module_type": "software", "reason": "团播流程。"},
                {"name": "Stream Deck / 直播可编程键盘", "role": "required", "module_type": "control", "reason": "一键控制。"},
            ],
            "quote_items": [
                {"name": "U-MOCO GRA", "quantity": 1, "reference_price": "¥601,000", "reason": "核心机械臂。"}
            ],
            "source_refs": [{"source": "产品价目", "doc_name": "U-MOCO GRA 报价"}],
            "missing_questions": [
                "客户预算区间是多少？",
                "现场是否需要轨道？如果需要，轨道长度和可用空间是多少米？",
            ],
        }


class QuoteServiceTest(unittest.TestCase):
    def setUp(self):
        self.archive = FakeArchiveService()
        self.service = QuoteService(
            FakeCatalogService(),
            FakePolicyService(),
            self.archive,
            configuration_quote_service=FakeConfigurationQuoteService(),
        )

    def test_group_streaming_chat_answer_uses_gra_not_pdf_metadata(self):
        result = self.service.draft(
            ChatRequest(message="我想做团播直播间你们有什么推荐吗", metadata={"regression_test": True}),
            memory=None,
            doc_candidates=[],
        )

        answer = result["answer"]
        draft = result["draft"]
        self.assertIn("U-MOCO GRA", answer)
        self.assertIn("这个场景我们比较熟", answer)
        self.assertIn("把机械臂自动运镜", answer)
        self.assertIn("直播间面积", answer)
        self.assertIn("直播效果", answer)
        self.assertIn("所有配置全摊开", answer)
        self.assertNotIn("先从 U-MOCO GRA", answer)
        self.assertNotIn("默认起步", answer)
        self.assertNotIn("为了推荐得更合适", answer)
        self.assertNotIn("OCR", answer)
        self.assertNotIn("价格字段", answer)
        self.assertNotIn("U-MOCO团播系统 2025.03", answer)
        self.assertNotIn("内部配置报价草案", answer)
        self.assertEqual([item["product"] for item in draft["recommended_products"]], ["U-MOCO GRA", "U-MOCO EXT", "U-MOCO PRO"])
        self.assertEqual(draft["quote_items"][0]["quantity"], 1)

    def test_group_streaming_product_recommendation_shows_three_arm_forms(self):
        self.assertTrue(self.service.is_quote_request("我们是做团播的给我推荐一下你们的产品"))
        self.assertFalse(self.service.is_quote_request("团播"))
        self.assertFalse(self.service.is_quote_request("GRA 团播系统有什么配置"))
        result = self.service.draft(
            ChatRequest(message="我们是做团播的给我推荐一下你们的产品", metadata={"regression_test": True}),
            memory=None,
            doc_candidates=[],
        )

        answer = result["answer"]
        products = [item["product"] for item in result["draft"]["recommended_products"]]
        self.assertEqual(products, ["U-MOCO GRA", "U-MOCO EXT", "U-MOCO PRO"])
        self.assertIn("这个场景我们比较熟", answer)
        self.assertIn("机械臂自动运镜", answer)
        self.assertIn("直播间面积", answer)
        self.assertIn("直播效果", answer)
        self.assertIn("所有配置全摊开", answer)
        self.assertIn("EXT", answer)
        self.assertIn("PRO", answer)
        self.assertNotIn("直播间大概多大", answer)
        self.assertNotIn("AIR/MINI", answer)
        self.assertNotIn("1.6万", answer)
        self.assertNotIn("10万元", answer)

    def test_group_streaming_configuration_sheet_renders_sendable_list(self):
        result = self.service.draft(
            ChatRequest(message="给我写一份寄出团播配置单", metadata={"regression_test": True}),
            memory=None,
            doc_candidates=[],
        )

        answer = result["answer"]
        self.assertIn("可发客户的团播配置单草案", answer)
        self.assertIn("【U-MOCO 团播直播间配置单｜参考草案】", answer)
        self.assertIn("一、核心配置", answer)
        self.assertIn("U-MOCO GRA", answer)
        self.assertIn("U-MOCO Live", answer)
        self.assertIn("Stream Deck", answer)
        self.assertIn("三、参考价格口径", answer)
        self.assertIn("不是最终成交报价", answer)
        self.assertNotIn("为了推荐得更合适", answer)
        self.assertNotIn("直播间大概多大", answer)

    def test_explicit_gra_price_keeps_single_gra_not_bundle_options(self):
        result = self.service.draft(
            ChatRequest(message="gra 团播系统需要什么价格", metadata={"regression_test": True}),
            memory=None,
            doc_candidates=[],
        )

        products = [item["product"] for item in result["draft"]["recommended_products"]]
        answer = result["answer"]
        self.assertEqual(products, ["U-MOCO GRA"])
        self.assertNotIn("U-MOCO GRA + EXT", products)
        self.assertIn("¥601,000", answer)
        self.assertIn("不是多条机械臂组合单", answer)
        self.assertIn("正式价格、优惠和交付安排", answer)
        self.assertEqual(result["draft"]["quote_items"][0]["name"], "U-MOCO GRA")


if __name__ == "__main__":
    unittest.main()
