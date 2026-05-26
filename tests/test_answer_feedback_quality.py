import unittest

from support_app.services.admin_service import AdminService
from support_app.services.behavior_tuning_service import BehaviorTuningService
from support_app.schemas import ChatResponse


class FakeStore:
    def __init__(self, items=None):
        self.items = list(items or [])

    def load_list(self):
        return list(self.items)

    def save_list(self, items):
        self.items = list(items)


class FakeBehaviorConfig:
    def __init__(self):
        self.applied = []

    def apply_patch(self, behavior_patch=None, style_patch=None):
        self.applied.append((behavior_patch or {}, style_patch or {}))
        return {"behavior_rules": behavior_patch or {}, "answer_styles": style_patch or {}}


class FakeTuningService:
    def __init__(self):
        self.cases = []

    def list_regression_cases(self):
        return {"total": len(self.cases), "items": list(self.cases)}

    def save_regression_cases(self, payload):
        self.cases = list(payload.get("items", []))
        return {"ok": True, "total": len(self.cases), "items": list(self.cases)}


class AnswerFeedbackQualityTest(unittest.TestCase):
    def make_admin(self, tuning=None):
        return AdminService(
            document_repo=None,
            faq_repo=None,
            rule_repo=None,
            category_repo=None,
            faq_index_service=None,
            memory_service=None,
            document_ingestion_service=None,
            pricing_catalog_service=None,
            quote_catalog_service=None,
            quote_policy_service=None,
            quote_archive_service=None,
            configuration_quote_service=None,
            answer_feedback_store=FakeStore(),
            learning_service=None,
            behavior_config_service=None,
            behavior_tuning_service=tuning or FakeTuningService(),
            model_settings_service=None,
            chat_service=None,
        )

    def test_answer_feedback_roundtrip_preserves_snapshot(self):
        admin = self.make_admin()
        saved = admin.save_answer_feedback({
            "message": "mini 保修多久",
            "answer": "我暂时无法确认。",
            "verdict": "missing_knowledge",
            "route": "fallback",
            "snapshot": {"metadata": {"knowledge_gaps": {"has_gaps": True}}},
        })
        listed = admin.list_answer_feedback()

        self.assertTrue(saved["ok"])
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["verdict"], "missing_knowledge")
        self.assertEqual(listed["items"][0]["error_reason"], "knowledge_not_found")
        self.assertEqual(listed["items"][0]["fix_target"], "faq")
        self.assertEqual(listed["items"][0]["suggested_action"], "add_faq")
        self.assertEqual(listed["items"][0]["snapshot"]["metadata"]["knowledge_gaps"]["has_gaps"], True)

    def test_quality_records_filter_and_update(self):
        admin = self.make_admin()
        saved = admin.save_answer_feedback({
            "message": "mini 保修多久",
            "answer": "我暂时无法确认。",
            "verdict": "missing_knowledge",
            "route": "fallback",
            "snapshot": {
                "metadata": {
                    "request_id": "req_1",
                    "used_tools": ["KnowledgeTool"],
                    "quality_flags": ["knowledge_not_found"],
                    "next_actions": ["add_faq"],
                }
            },
        })

        records = admin.list_quality_records(flag="knowledge_miss")
        self.assertEqual(records["total"], 1)
        self.assertEqual(records["items"][0]["request_id"], "req_1")
        self.assertEqual(records["items"][0]["used_tools"], ["KnowledgeTool"])

        updated = admin.update_quality_record(saved["item"]["id"], {
            "status": "resolved",
            "human_annotation": "wrong",
        })
        self.assertEqual(updated["item"]["status"], "resolved")
        self.assertEqual(updated["item"]["human_annotation"], "wrong")

    def test_feedback_to_regression_case_creates_valid_case(self):
        tuning = FakeTuningService()
        admin = self.make_admin(tuning)
        saved = admin.save_answer_feedback({
            "message": "gra 团播系统需要什么价格",
            "answer": "GRA 参考价 ¥601,000，正式价格需人工确认。",
            "verdict": "good",
            "route": "quote_draft",
        })
        converted = admin.answer_feedback_to_regression_case(saved["item"]["id"])

        self.assertTrue(converted["ok"])
        self.assertEqual(converted["item"]["message"], "gra 团播系统需要什么价格")
        self.assertEqual(converted["item"]["expected_route"], "quote_draft")
        self.assertEqual(admin.answer_feedback_store.items[0]["status"], "in_regression")
        self.assertTrue(tuning.cases)


class BehaviorTuningSafetyTest(unittest.TestCase):
    def test_empty_regression_cases_are_filtered(self):
        service = BehaviorTuningService(None, FakeBehaviorConfig(), FakeStore(), FakeStore())
        result = service.save_regression_cases({
            "items": [
                {"id": "empty", "message": ""},
                {"id": "valid", "message": "你是谁", "expected_route": "identity"},
            ]
        })

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["id"], "valid")

    def test_apply_blocks_when_regression_check_failed_without_force(self):
        service = BehaviorTuningService(None, FakeBehaviorConfig(), FakeStore(), FakeStore())
        result = service.apply({
            "draft": {"id": "draft_1", "behavior_rules_patch": {}, "answer_style_patch": {}, "regression_cases": []},
            "regression_check": {"failed": 1},
        })

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])

    def test_regression_cases_support_tool_and_need_human_checks(self):
        class FakeChat:
            def answer(self, request):
                return ChatResponse(
                    answer="可发客户的团播配置单草案，正式价格需人工复核。",
                    route="quote_draft",
                    need_human=True,
                    metadata={"used_tools": ["QuoteIntentDetector", "QuoteTool"], "need_human_review": True},
                )

        service = BehaviorTuningService(None, FakeBehaviorConfig(), FakeStore(), FakeStore())
        result = service.run_regression_cases(FakeChat(), {
            "cases": [{
                "id": "intent_config_sheet",
                "question": "给我写一份寄出团播配置单",
                "expected_route": "quote_draft",
                "expected_tool": "QuoteTool",
                "must_include": ["配置单草案"],
                "must_not_include": ["为了推荐得更合适"],
                "expected_need_human_review": True,
            }]
        })

        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["results"][0]["used_tools"], ["QuoteIntentDetector", "QuoteTool"])
        self.assertTrue(result["results"][0]["need_human_review"])


if __name__ == "__main__":
    unittest.main()
