from support_app.repositories.category_repository import CategoryRepository
from support_app.repositories.document_repository import DocumentRepository
from support_app.repositories.faq_repository import FAQRepository
from support_app.repositories.rule_repository import RuleRepository
from support_app.schemas import CustomerMemoryItem, FAQItem, RuleItem
from support_app.services.behavior_config_service import BehaviorConfigService
from support_app.services.behavior_tuning_service import BehaviorTuningService
from support_app.services.chat_service import ChatService
from support_app.services.customer_memory_service import CustomerMemoryService
from support_app.services.document_ingestion_service import DocumentIngestionService
from support_app.services.faq_index_service import FAQIndexService
from support_app.services.learning_service import LearningService
from support_app.services.model_settings_service import ModelSettingsService
from support_app.services.pricing_catalog_service import PricingCatalogService
from support_app.services.quote_archive_service import QuoteArchiveService
from support_app.services.quote_policy_service import QuotePolicyService


class AdminService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        faq_repo: FAQRepository,
        rule_repo: RuleRepository,
        category_repo: CategoryRepository,
        faq_index_service: FAQIndexService,
        memory_service: CustomerMemoryService,
        document_ingestion_service: DocumentIngestionService,
        pricing_catalog_service: PricingCatalogService,
        quote_policy_service: QuotePolicyService,
        quote_archive_service: QuoteArchiveService,
        learning_service: LearningService,
        behavior_config_service: BehaviorConfigService,
        behavior_tuning_service: BehaviorTuningService,
        model_settings_service: ModelSettingsService,
        chat_service: ChatService,
    ):
        self.document_repo = document_repo
        self.faq_repo = faq_repo
        self.rule_repo = rule_repo
        self.category_repo = category_repo
        self.faq_index_service = faq_index_service
        self.memory_service = memory_service
        self.document_ingestion_service = document_ingestion_service
        self.pricing_catalog_service = pricing_catalog_service
        self.quote_policy_service = quote_policy_service
        self.quote_archive_service = quote_archive_service
        self.learning_service = learning_service
        self.behavior_config_service = behavior_config_service
        self.behavior_tuning_service = behavior_tuning_service
        self.model_settings_service = model_settings_service
        self.chat_service = chat_service

    def summary(self) -> dict:
        docs = self.document_repo.list()
        faqs = self.faq_repo.list()
        rules = self.rule_repo.load(include_inactive=True)
        doc_names = self.document_repo.names()
        return {
            "doc_chunk_count": len(docs),
            "doc_count": len(doc_names),
            "faq_count": len(faqs),
            "rule_count": len(rules),
            "doc_names": doc_names[:20],
        }

    def list_docs(self, q: str = "") -> dict:
        items = self.document_repo.list(q)
        return {"total": len(items), "items": items[:200]}

    def upload_doc(self, filename: str, content: bytes, category: str = "", doc_name: str = "") -> dict:
        return self.document_ingestion_service.upload(filename, content, category, doc_name)

    def delete_doc(self, doc_name: str) -> dict:
        return self.document_ingestion_service.delete_doc(doc_name)

    def delete_docs(self, doc_names: list[str]) -> dict:
        return self.document_ingestion_service.delete_docs(doc_names)

    def upload_docs(self, files: list[tuple[str, bytes]], category: str = "", doc_name: str = "") -> dict:
        results = []
        success_count = 0
        indexed_count = 0
        chunk_count = 0
        for filename, content in files:
            try:
                item = self.upload_doc(filename, content, category, doc_name)
            except Exception as exc:
                item = {
                    "ok": False,
                    "status": "failed",
                    "message": f"{type(exc).__name__}: {exc}",
                    "source_file": filename,
                    "doc_name": doc_name or filename,
                    "chunk_count": 0,
                    "indexed": False,
                }
            if item.get("ok"):
                success_count += 1
            if item.get("indexed"):
                indexed_count += 1
            chunk_count += int(item.get("chunk_count") or 0)
            results.append(item)

        failed_count = len(results) - success_count
        return {
            "ok": failed_count == 0,
            "status": "uploaded" if failed_count == 0 else "partial",
            "message": f"上传完成：成功 {success_count} 个，失败 {failed_count} 个，入库 {indexed_count} 个。",
            "total": len(results),
            "success_count": success_count,
            "failed_count": failed_count,
            "indexed_count": indexed_count,
            "chunk_count": chunk_count,
            "results": results,
        }

    def list_faqs(self, q: str = "") -> dict:
        items = self.faq_repo.list(q)
        return {"total": len(items), "items": items[:200]}

    def create_faq(self, payload: FAQItem) -> dict:
        item = self.faq_repo.create(payload.model_dump(exclude_none=True))
        return {"ok": True, "item": item, "reindex": self.faq_index_service.rebuild()}

    def update_faq(self, faq_id: str, payload: FAQItem) -> dict:
        item = self.faq_repo.update(faq_id, payload.model_dump(exclude_none=True))
        return {"ok": True, "item": item, "reindex": self.faq_index_service.rebuild()}

    def delete_faq(self, faq_id: str) -> dict:
        self.faq_repo.delete(faq_id)
        return {"ok": True, "deleted_id": faq_id, "reindex": self.faq_index_service.rebuild()}

    def reindex_faqs(self) -> dict:
        return {"ok": True, "reindex": self.faq_index_service.rebuild()}

    def list_rules(self, q: str = "") -> dict:
        rules = self.rule_repo.load(include_inactive=True)
        if q:
            keyword = q.strip().lower()
            rules = [item for item in rules if keyword in str(item).lower()]
        return {"total": len(rules), "items": rules[:200]}

    def test_rule(self, text: str) -> dict:
        matched = self.rule_repo.match(text)
        return {"ok": True, "matched": bool(matched), "rule": matched}

    def create_rule(self, payload: RuleItem) -> dict:
        item = self.rule_repo.create(payload.model_dump(exclude_none=True))
        return {"ok": True, "item": item, "reload": {"rule_count": len(self.rule_repo.load(include_inactive=True))}}

    def update_rule(self, rule_id: str, payload: RuleItem) -> dict:
        item = self.rule_repo.update(rule_id, payload.model_dump(exclude_none=True))
        return {"ok": True, "item": item, "reload": {"rule_count": len(self.rule_repo.load(include_inactive=True))}}

    def delete_rule(self, rule_id: str) -> dict:
        self.rule_repo.delete(rule_id)
        return {"ok": True, "deleted_id": rule_id, "reload": {"rule_count": len(self.rule_repo.load(include_inactive=True))}}

    def reload_rules(self) -> dict:
        return {"ok": True, "reload": {"rule_count": len(self.rule_repo.load(include_inactive=True))}}

    def list_categories(self) -> dict:
        items = self.category_repo.list_with_usage()
        return {"total": len(items), "items": items}

    def create_category(self, name: str) -> dict:
        return {"ok": True, "items": self.category_repo.create(name)}

    def delete_category(self, name: str) -> dict:
        return {"ok": True, "deleted_name": name, "items": self.category_repo.delete(name)}

    def list_memories(self, q: str = "") -> dict:
        return self.memory_service.list(q)

    def update_memory(self, channel: str, user_id: str, payload: CustomerMemoryItem) -> dict:
        item = self.memory_service.replace(channel, user_id, payload.model_dump(exclude_none=True))
        return {"ok": True, "item": item}

    def delete_memory(self, channel: str, user_id: str) -> dict:
        self.memory_service.delete(channel, user_id)
        return {"ok": True, "deleted": {"channel": channel, "user_id": user_id}}

    def get_quote_policies(self) -> dict:
        return self.quote_policy_service.get()

    def update_quote_policies(self, payload: dict) -> dict:
        return {"ok": True, "item": self.quote_policy_service.save(payload)}

    def get_pricing_catalog(self) -> dict:
        return self.pricing_catalog_service.get()

    def update_pricing_catalog(self, payload: dict) -> dict:
        return {"ok": True, "item": self.pricing_catalog_service.save(payload)}

    def rebuild_pricing_catalog_preview(self) -> dict:
        return {"ok": True, "item": self.pricing_catalog_service.build_from_documents()}

    def list_quote_archives(self, q: str = "") -> dict:
        return self.quote_archive_service.list(q)

    def update_quote_archive(self, channel: str, user_id: str, quote_id: str, payload: dict) -> dict:
        return {"ok": True, "item": self.quote_archive_service.update(channel, user_id, quote_id, payload)}

    def list_learned_knowledge(self, q: str = "") -> dict:
        return self.learning_service.list(q)

    def delete_learned_knowledge(self, learned_id: str) -> dict:
        return self.learning_service.delete(learned_id)

    def reindex_learned_knowledge(self) -> dict:
        return self.learning_service.reindex()

    def get_behavior_rules(self) -> dict:
        return self.behavior_config_service.get_behavior_rules()

    def update_behavior_rules(self, payload: dict) -> dict:
        return {"ok": True, "item": self.behavior_config_service.save_behavior_rules(payload)}

    def get_answer_styles(self) -> dict:
        return self.behavior_config_service.get_answer_styles()

    def update_answer_styles(self, payload: dict) -> dict:
        return {"ok": True, "item": self.behavior_config_service.save_answer_styles(payload)}

    def create_tuning_draft(self, instruction: str) -> dict:
        return self.behavior_tuning_service.draft(instruction)

    def apply_tuning_draft(self, payload: dict) -> dict:
        return self.behavior_tuning_service.apply(payload)

    def list_regression_cases(self) -> dict:
        return self.behavior_tuning_service.list_regression_cases()

    def update_regression_cases(self, payload: dict) -> dict:
        return self.behavior_tuning_service.save_regression_cases(payload)

    def run_regression_cases(self, payload: dict | None = None) -> dict:
        return self.behavior_tuning_service.run_regression_cases(self.chat_service, payload or {})

    def get_models(self) -> dict:
        return self.model_settings_service.overview()

    def update_chat_model(self, payload: dict) -> dict:
        item = self.model_settings_service.save_chat_model(str(payload.get("chat_model", "") or ""))
        return {"ok": True, "settings": item, "models": self.model_settings_service.installed_models()}

    def rebuild_embed_model(self, payload: dict) -> dict:
        model = str(payload.get("embed_model", "") or "")
        self.model_settings_service.set_embed_rebuilding(model)
        try:
            faq_result = self.faq_index_service.rebuild()
            doc_result = self.document_ingestion_service.reindex_current_docs()
        except Exception as exc:
            item = self.model_settings_service.mark_embed_result("failed", f"{type(exc).__name__}: {exc}")
            raise ValueError(item["embed_index_message"]) from exc
        item = self.model_settings_service.mark_embed_result("success", "FAQ 和文档向量库已使用新向量模型重建")
        return {
            "ok": True,
            "settings": item,
            "faq_reindex": faq_result,
            "doc_reindex": doc_result,
        }
