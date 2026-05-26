import unittest

from support_app.services.configuration_quote_service import ConfigurationQuoteService
from support_app.services.quote_catalog_service import QuoteCatalogService


class FakePolicyService:
    def get(self):
        return {"approval_required": ["优惠价", "交付时间", "特殊定制"]}


class FakeFeedbackStore:
    def __init__(self):
        self.items = []

    def load_list(self):
        return list(self.items)

    def save_list(self, items):
        self.items = list(items)


class FakeCatalogStore:
    def load_object(self):
        return {}

    def save_object(self, _item):
        return None


class ConfigurationQuoteServiceTest(unittest.TestCase):
    def setUp(self):
        self.feedback = FakeFeedbackStore()
        self.service = ConfigurationQuoteService(
            QuoteCatalogService(FakeCatalogStore()),
            FakePolicyService(),
            self.feedback,
        )

    def test_live_group_streaming_draft_splits_modules_and_questions(self):
        draft = self.service.draft("客户做团播，直播间约 80 平，希望 4 台相机，6 米轨道，FreeD 跟踪，预算 50 万左右，下个月交付。")

        self.assertTrue(draft["ok"])
        self.assertEqual(draft["needs"]["track_length"], "6")
        self.assertEqual(draft["needs"]["camera_count"], "4")
        self.assertTrue(draft["needs"]["freed_required"])
        self.assertIn("U-MOCO GRA", {item["name"] for item in draft["modules"]})
        self.assertNotIn("U-MOCO GRA + EXT", {item["name"] for item in draft["modules"]})
        self.assertIn("影视地面轨道", {item["name"] for item in draft["modules"]})
        self.assertIn("XR 虚拟制作 FreeD 协议", {item["name"] for item in draft["modules"]})
        track_rows = [item for item in draft["quote_items"] if item["name"] == "影视地面轨道"]
        self.assertEqual(track_rows[0]["quantity"], 6.0)
        self.assertTrue(draft["source_refs"])
        self.assertTrue(any("内部配置" in item for item in draft["review_flags"]))

    def test_group_streaming_uses_group_live_candidate_even_with_low_budget(self):
        draft = self.service.draft("客户做团播，预算 25 万以内，不确定是否需要轨道。")

        names = {item["name"] for item in draft["modules"]}
        self.assertIn("U-MOCO GRA", names)
        self.assertNotIn("U-MOCO MINI", names)
        self.assertNotIn("U-MOCO AIR", names)
        self.assertNotIn("影视地面轨道", names)
        self.assertTrue(any("直播间面积" in item for item in draft["review_flags"]))
        self.assertTrue(any("不能只按默认型号硬推" in item for item in draft["review_flags"]))

    def test_track_is_not_added_when_customer_does_not_need_track(self):
        draft = self.service.draft("客户做团播，直播间 70 平，预算 60 万，主要需要固定机位自动运镜。")

        self.assertIn("U-MOCO GRA", {item["name"] for item in draft["modules"]})
        self.assertNotIn("影视地面轨道", {item["name"] for item in draft["modules"]})
        self.assertTrue(any("轨道" in item for item in draft["missing_questions"]))

    def test_followup_request_uses_memory_context(self):
        draft = self.service.draft(
            "直播间大概 50 平，打算用三个机位，机械臂用一台。",
            metadata={"memory": {"scenario": "团播"}},
        )

        self.assertEqual(draft["scenario"], "group_live")
        self.assertEqual(draft["needs"]["live_room_area"], "50")
        self.assertEqual(draft["needs"]["camera_count"], "3")
        self.assertEqual(draft["needs"]["robot_arm_count"], "1")
        self.assertIn("U-MOCO GRA", {item["name"] for item in draft["modules"]})
        self.assertNotIn("影视地面轨道", {item["name"] for item in draft["modules"]})

    def test_sparse_request_keeps_missing_questions_visible(self):
        draft = self.service.draft("客户想做直播间机械臂。")

        self.assertGreaterEqual(len(draft["missing_questions"]), 4)
        self.assertTrue(any("预算" in item for item in draft["missing_questions"]))
        self.assertFalse(any("AIR/MINI" in item for item in draft["missing_questions"]))
        self.assertTrue(any("轨道" in item for item in draft["missing_questions"]))

    def test_feedback_store_roundtrip(self):
        saved = self.service.save_feedback({"message": "团播报价", "verdict": "usable", "draft": {"ok": True}})
        listed = self.service.list_feedback("团播")

        self.assertTrue(saved["ok"])
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["verdict"], "usable")


if __name__ == "__main__":
    unittest.main()
