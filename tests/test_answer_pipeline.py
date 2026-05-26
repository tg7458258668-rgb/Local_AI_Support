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


class AnswerPipelineTests(unittest.TestCase):
    def test_pipeline_preserves_chat_response_and_adds_quality_metadata(self):
        request = ChatRequest(message="EXT 加 6 米轨道多少钱", conversation_id="s1")

        response = AnswerPipeline(FakeLegacyChatService()).answer(request)

        self.assertEqual(response.route, "quote_draft")
        self.assertEqual(response.matched_rule, "报价必须人工确认")
        self.assertIn("request_id", response.metadata)
        self.assertEqual(response.metadata["intent_plan"]["intent"], "quote_price")
        self.assertEqual(response.metadata["intent_plan"]["route_policy"], "quote_draft")
        self.assertIn("EXT", response.metadata["product_anchors"])
        self.assertIn("多少钱", response.metadata["action_terms"])
        self.assertIn("decision_trace", response.metadata)
        self.assertIn("QuoteIntentDetector", response.metadata["used_tools"])
        self.assertIn("QuoteTool", response.metadata["used_tools"])
        self.assertIn("quote_requires_review", response.metadata["quality_flags"])
        self.assertTrue(response.metadata["need_human_review"])


if __name__ == "__main__":
    unittest.main()
