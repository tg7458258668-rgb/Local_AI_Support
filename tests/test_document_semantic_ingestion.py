import tempfile
import unittest
from pathlib import Path

from support_app.repositories.document_repository import DocumentRepository
from support_app.services.document_analysis_service import DocumentAnalysisService
from support_app.services.document_ingestion_service import DocumentIngestionService


class DummySettings:
    def __init__(self, root: Path):
        self.base_dir = root
        self.data_dir = root / "data"
        self.qdrant_url = "http://127.0.0.1:6333"
        self.doc_collection = "docs_test"


class DummyOllama:
    def embedding(self, text):
        return [0.1, 0.2, 0.3]


class DummyRetrieval:
    def clear_cache(self):
        pass


class DocumentSemanticIngestionTests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        settings = DummySettings(root)
        repo = DocumentRepository(settings.data_dir / "docs_chunks" / "docs_chunks.json")
        service = DocumentIngestionService(
            settings,
            repo,
            DummyOllama(),
            DummyRetrieval(),
            DocumentAnalysisService(None),
        )
        return tmp, service

    def test_heuristic_analysis_identifies_products_parameters_and_scenarios(self):
        text = """
        U-MOCO GRA 团播系统适用于直播间和电商团播。
        支持 FreeD、Stream Deck 控制，轨道为选配。
        关键参数：机械臂负载 8kg，重复定位精度高。
        """
        analysis = DocumentAnalysisService(None).analyze(doc_name="GRA产品资料", text=text, category="产品资料")

        self.assertIn("产品资料", analysis["doc_type"])
        self.assertIn("团播", analysis["scenarios"])
        self.assertTrue(any("GRA" in item for item in analysis["products"]))
        self.assertTrue(any("FreeD" in item or "轨道" in item for item in analysis["key_parameters"]))

    def test_price_fields_only_attached_to_price_chunks(self):
        tmp, service = self.make_service()
        self.addCleanup(tmp.cleanup)
        parsed = {
            "doc_name": "gra_doc",
            "source_file": "gra.pdf",
            "doc_type": "产品资料",
            "summary": "GRA 产品资料",
            "key_points": ["轨道为选配"],
            "products": ["U-MOCO GRA"],
            "scenarios": ["团播"],
            "price_items": [{"item": "GRA 团播系统 ￥448,000", "amount": "￥448,000"}],
            "semantic_sections": [
                {
                    "section_title": "GRA 配置",
                    "text": "U-MOCO GRA 团播系统支持 Stream Deck 控制，轨道按场地选配。",
                    "topics": ["配置", "场景"],
                    "entities": ["U-MOCO GRA"],
                    "semantic_summary": "说明 GRA 团播配置。",
                },
                {
                    "section_title": "GRA 报价",
                    "text": "GRA 团播系统参考价格 ￥448,000，最终以配置单为准。",
                    "topics": ["报价"],
                    "entities": ["U-MOCO GRA"],
                    "semantic_summary": "说明 GRA 参考价格。",
                    "price_fields": {"参考价格": "￥448,000"},
                    "quote_items": ["GRA 团播系统参考价格 ￥448,000"],
                },
            ],
        }

        chunks = service._build_chunks(parsed)

        config_chunk = next(item for item in chunks if item["section_title"] == "GRA 配置")
        price_chunk = next(item for item in chunks if item["section_title"] == "GRA 报价")
        self.assertEqual(config_chunk["price_fields"], {})
        self.assertEqual(config_chunk["quote_items"], [])
        self.assertEqual(price_chunk["price_fields"], {"参考价格": "￥448,000"})
        self.assertIn("￥448,000", price_chunk["text"])

    def test_warranty_policy_identifies_terms(self):
        text = "售后政策：控制器质保 12 个月，电池保修 3 个月。人为损坏、进水不在保修范围内。"
        analysis = DocumentAnalysisService(None).analyze(doc_name="售后政策", text=text, category="售后政策")

        self.assertEqual(analysis["doc_type"], "售后政策")
        self.assertTrue(any("保修" in item or "质保" in item for item in analysis["warranty_terms"]))
        self.assertTrue(any("不在保修" in item for item in analysis["restrictions"]))

    def test_analysis_fallback_generates_sections_without_model(self):
        analysis = DocumentAnalysisService(None).analyze(doc_name="普通资料", text="这是产品资料，包含直播场景和配置说明。" * 10)

        self.assertEqual(analysis["analysis_method"], "heuristic")
        self.assertTrue(analysis["semantic_sections"])

    def test_search_text_includes_semantic_context_and_payload_keeps_original_text(self):
        tmp, service = self.make_service()
        self.addCleanup(tmp.cleanup)
        parsed = {
            "doc_name": "mini_doc",
            "display_name": "MINI 售后",
            "source_file": "mini.md",
            "doc_type": "售后政策",
            "summary": "MINI 售后摘要",
            "key_points": ["电池保修 3 个月"],
            "products": ["MINI"],
            "scenarios": [],
            "semantic_sections": [{
                "section_title": "MINI 保修",
                "page_range": "第2页",
                "text": "电池保修 3 个月。",
                "topics": ["售后"],
                "entities": ["MINI"],
                "semantic_summary": "MINI 电池保修规则。",
            }],
        }

        chunk = service._build_chunks(parsed)[0]

        self.assertEqual(chunk["text"], "电池保修 3 个月。")
        self.assertIn("MINI 售后摘要", chunk["search_text"])
        self.assertIn("MINI 电池保修规则", chunk["search_text"])
        self.assertIn("第2页", chunk["search_text"])


if __name__ == "__main__":
    unittest.main()
