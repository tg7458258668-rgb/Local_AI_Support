import uuid
from datetime import datetime
from typing import Any

from support_app.repositories.category_repository import CategoryRepository
from support_app.repositories.document_repository import DocumentRepository
from support_app.repositories.faq_repository import FAQRepository
from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.repositories.rule_repository import RuleRepository
from support_app.schemas import AnswerFeedbackRequest, CustomerMemoryItem, FAQItem, RuleItem
from support_app.services.behavior_config_service import BehaviorConfigService
from support_app.services.behavior_tuning_service import BehaviorTuningService
from support_app.services.chat_service import ChatService
from support_app.services.configuration_quote_service import ConfigurationQuoteService
from support_app.services.customer_memory_service import CustomerMemoryService
from support_app.services.document_ingestion_service import DocumentIngestionService
from support_app.services.faq_index_service import FAQIndexService
from support_app.services.learning_service import LearningService
from support_app.services.model_settings_service import ModelSettingsService
from support_app.services.pricing_catalog_service import PricingCatalogService
from support_app.services.quote_catalog_service import QuoteCatalogService
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
        quote_catalog_service: QuoteCatalogService,
        quote_policy_service: QuotePolicyService,
        quote_archive_service: QuoteArchiveService,
        configuration_quote_service: ConfigurationQuoteService,
        answer_feedback_store: JsonFileRepository,
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
        self.quote_catalog_service = quote_catalog_service
        self.quote_policy_service = quote_policy_service
        self.quote_archive_service = quote_archive_service
        self.configuration_quote_service = configuration_quote_service
        self.answer_feedback_store = answer_feedback_store
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

    def clear_quote_references(self) -> dict:
        return self.document_ingestion_service.clear_quote_references()

    def rebuild_semantic_docs(self) -> dict:
        return self.document_ingestion_service.rebuild_semantic_index()

    def render_doc_page_image(self, doc_name: str, page: int):
        return self.document_ingestion_service.render_doc_page_image(doc_name, page)

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

    def get_quote_catalog(self) -> dict:
        return self.quote_catalog_service.get()

    def update_quote_catalog(self, payload: dict) -> dict:
        return {"ok": True, "item": self.quote_catalog_service.save(payload)}

    def validate_quote_catalog(self, payload: dict) -> dict:
        return self.quote_catalog_service.validate(payload)

    def list_quote_archives(self, q: str = "") -> dict:
        return self.quote_archive_service.list(q)

    def update_quote_archive(self, channel: str, user_id: str, quote_id: str, payload: dict) -> dict:
        return {"ok": True, "item": self.quote_archive_service.update(channel, user_id, quote_id, payload)}

    def draft_configuration_quote(self, payload: dict) -> dict:
        return self.configuration_quote_service.draft(
            str(payload.get("message", "") or ""),
            str(payload.get("scenario", "") or "live_commerce"),
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )

    def save_configuration_quote_feedback(self, payload: dict) -> dict:
        return self.configuration_quote_service.save_feedback(payload)

    def list_configuration_quote_feedback(self, q: str = "") -> dict:
        return self.configuration_quote_service.list_feedback(q)

    def list_answer_feedback(self, q: str = "", verdict: str = "") -> dict:
        items = self.answer_feedback_store.load_list()
        if verdict:
            items = [item for item in items if item.get("verdict") == verdict]
        if q:
            keyword = q.strip().lower()
            items = [item for item in items if keyword in str(item).lower()]
        return {"total": len(items), "items": items[:200]}

    def save_answer_feedback(self, payload: AnswerFeedbackRequest | dict) -> dict:
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload or {})
        snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else {}
        snapshot_metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        message = str(data.get("message") or snapshot.get("message") or snapshot.get("question") or "").strip()
        answer = str(data.get("answer") or snapshot.get("answer") or "").strip()
        if not message:
            raise ValueError("message 不能为空")
        verdict = str(data.get("verdict") or "needs_review")
        inferred = self._infer_feedback_fields(verdict)
        route = str(data.get("route") or snapshot.get("route") or "").strip()
        item = {
            "id": f"answer_feedback_{uuid.uuid4().hex[:12]}",
            "message": message,
            "answer": answer,
            "verdict": verdict,
            "feedback_type": str(data.get("feedback_type") or "answer_quality").strip(),
            "error_reason": str(data.get("error_reason") or inferred["error_reason"]).strip(),
            "fix_target": str(data.get("fix_target") or inferred["fix_target"]).strip(),
            "suggested_action": str(data.get("suggested_action") or inferred["suggested_action"]).strip(),
            "status": str(data.get("status") or inferred["status"]).strip(),
            "regression_case_id": data.get("regression_case_id") or None,
            "request_id": str(data.get("request_id") or snapshot_metadata.get("request_id") or snapshot.get("request_id") or "").strip(),
            "notes": str(data.get("notes") or "").strip(),
            "route": route,
            "expected_route": str(data.get("expected_route") or snapshot.get("route") or "").strip(),
            "expected_keywords": self._clean_words(data.get("expected_keywords") or self._keyword_suggestions(answer, message)),
            "forbidden_keywords": self._clean_words(data.get("forbidden_keywords") or []),
            "matched_rule": snapshot.get("matched_rule"),
            "score": self._feedback_score(snapshot),
            "need_human_review": bool(snapshot_metadata.get("need_human_review") or snapshot.get("need_human") or route == "quote_draft"),
            "used_tools": snapshot_metadata.get("used_tools") if isinstance(snapshot_metadata.get("used_tools"), list) else [],
            "quality_flags": snapshot_metadata.get("quality_flags") if isinstance(snapshot_metadata.get("quality_flags"), list) else [],
            "next_actions": snapshot_metadata.get("next_actions") if isinstance(snapshot_metadata.get("next_actions"), list) else [],
            "decision_trace": snapshot_metadata.get("decision_trace") if isinstance(snapshot_metadata.get("decision_trace"), list) else [],
            "sources": snapshot.get("sources") if isinstance(snapshot.get("sources"), list) else [],
            "snapshot": snapshot,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        items = self.answer_feedback_store.load_list()
        items.insert(0, item)
        self.answer_feedback_store.save_list(items[:500])
        return {"ok": True, "item": item}

    def list_quality_records(self, q: str = "", status: str = "", reason: str = "", flag: str = "") -> dict:
        items = [self._quality_record(item) for item in self.answer_feedback_store.load_list()]
        if q:
            keyword = q.strip().lower()
            items = [item for item in items if keyword in str(item).lower()]
        if status:
            items = [item for item in items if item.get("status") == status]
        if reason:
            items = [item for item in items if item.get("error_reason") == reason]
        if flag:
            items = [item for item in items if self._quality_flag_match(item, flag)]
        return {"total": len(items), "items": items[:200]}

    def update_quality_record(self, record_id: str, payload: dict) -> dict:
        items = self.answer_feedback_store.load_list()
        item = next((row for row in items if row.get("id") == record_id), None)
        if not item:
            raise KeyError("质检记录不存在")
        allowed = {
            "notes",
            "status",
            "error_reason",
            "fix_target",
            "suggested_action",
            "feedback_type",
            "human_annotation",
        }
        for key in allowed:
            if key in payload:
                item[key] = payload.get(key)
        item["updated_at"] = self._now()
        self.answer_feedback_store.save_list(items)
        return {"ok": True, "item": self._quality_record(item)}

    def answer_feedback_to_regression_case(self, feedback_id: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        items = self.answer_feedback_store.load_list()
        feedback = next((item for item in items if item.get("id") == feedback_id), None)
        if not feedback:
            raise KeyError("反馈记录不存在")
        message = str(payload.get("message") or feedback.get("message") or "").strip()
        if not message:
            raise ValueError("message 不能为空，无法生成回归用例")
        verdict = str(feedback.get("verdict") or "needs_review")
        expected_keywords = self._clean_words(payload.get("expected_keywords") or feedback.get("expected_keywords") or [])
        forbidden_keywords = self._clean_words(payload.get("forbidden_keywords") or feedback.get("forbidden_keywords") or [])
        if verdict != "good" and not forbidden_keywords:
            forbidden_keywords = self._keyword_suggestions(str(feedback.get("answer") or ""), message)[:3]
        case = {
            "id": str(payload.get("id") or f"case_feedback_{uuid.uuid4().hex[:10]}"),
            "name": str(payload.get("name") or self._feedback_case_name(feedback)).strip(),
            "message": message,
            "channel": str(payload.get("channel") or "api"),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {"test_page": True},
            "test_memory": payload.get("test_memory") if isinstance(payload.get("test_memory"), dict) else {},
            "expected_route": str(payload.get("expected_route") or feedback.get("expected_route") or feedback.get("route") or "").strip(),
            "expected_keywords": expected_keywords,
            "forbidden_keywords": forbidden_keywords,
            "enabled": bool(payload.get("enabled", True)),
        }
        current = self.behavior_tuning_service.list_regression_cases()["items"]
        saved = self.behavior_tuning_service.save_regression_cases({"items": [case, *current]})
        feedback["regression_case_id"] = case["id"]
        feedback["status"] = "in_regression"
        feedback["suggested_action"] = "add_regression_case"
        feedback["updated_at"] = self._now()
        self.answer_feedback_store.save_list(items)
        return {"ok": True, "item": case, "regression_cases": saved}

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
        return self.apply_tuning_draft_with_check(payload)

    def list_regression_cases(self) -> dict:
        return self.behavior_tuning_service.list_regression_cases()

    def update_regression_cases(self, payload: dict) -> dict:
        return self.behavior_tuning_service.save_regression_cases(payload)

    def run_regression_cases(self, payload: dict | None = None) -> dict:
        return self.behavior_tuning_service.run_regression_cases(self.chat_service, payload or {})

    def apply_tuning_draft_with_check(self, payload: dict) -> dict:
        payload = dict(payload or {})
        if not payload.get("force"):
            check = self.run_regression_cases({})
            if check.get("failed", 0):
                payload["regression_check"] = check
        return self.behavior_tuning_service.apply(payload)

    def knowledge_index_status(self) -> dict:
        overview = self.model_settings_service.overview()
        model_settings = overview.get("settings") if isinstance(overview.get("settings"), dict) else {}
        status = str(model_settings.get("embed_index_status") or "unknown")
        pending = status in {"not_rebuilt", "rebuilding", "failed"}
        faq_collection = self.faq_index_service.settings.faq_collection
        doc_collection = self.document_ingestion_service.settings.doc_collection
        return {
            "ok": True,
            "pending_rebuild": pending,
            "status": status,
            "message": str(model_settings.get("embed_index_message") or ""),
            "last_rebuilt_at": str(model_settings.get("updated_at") or ""),
            "current_collection": doc_collection,
            "faq_collection": faq_collection,
            "doc_collection": doc_collection,
            "collections": [faq_collection, doc_collection],
            "embed_model": str(model_settings.get("embed_model") or ""),
        }

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

    @staticmethod
    def _infer_feedback_fields(verdict: str) -> dict[str, str]:
        mapping = {
            "good": {
                "error_reason": "",
                "fix_target": "regression",
                "suggested_action": "add_regression_case",
                "status": "resolved",
            },
            "factual_error": {
                "error_reason": "knowledge_wrong",
                "fix_target": "knowledge",
                "suggested_action": "edit_knowledge",
                "status": "pending",
            },
            "missing_knowledge": {
                "error_reason": "knowledge_not_found",
                "fix_target": "faq",
                "suggested_action": "add_faq",
                "status": "pending",
            },
            "wrong_retrieval": {
                "error_reason": "retrieval_wrong",
                "fix_target": "priority_rule",
                "suggested_action": "adjust_priority_rule",
                "status": "pending",
            },
            "style_issue": {
                "error_reason": "style_issue",
                "fix_target": "prompt",
                "suggested_action": "adjust_prompt",
                "status": "pending",
            },
            "bad_quote": {
                "error_reason": "quote_rule_missing",
                "fix_target": "quote_rule",
                "suggested_action": "add_quote_rule",
                "status": "pending",
            },
            "needs_review": {
                "error_reason": "needs_review",
                "fix_target": "manual_review",
                "suggested_action": "manual_review",
                "status": "pending",
            },
        }
        return mapping.get(verdict, mapping["needs_review"])

    @staticmethod
    def _feedback_score(snapshot: dict) -> float:
        for key in ("score", "faq_top_score", "doc_top_score"):
            try:
                value = float(snapshot.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value:
                return value
        return 0.0

    def _quality_record(self, item: dict) -> dict:
        snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
        metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        verdict = str(item.get("verdict") or "needs_review")
        inferred = self._infer_feedback_fields(verdict)
        route = str(item.get("route") or snapshot.get("route") or "").strip()
        used_tools = item.get("used_tools") if isinstance(item.get("used_tools"), list) else metadata.get("used_tools", [])
        quality_flags = item.get("quality_flags") if isinstance(item.get("quality_flags"), list) else metadata.get("quality_flags", [])
        next_actions = item.get("next_actions") if isinstance(item.get("next_actions"), list) else metadata.get("next_actions", [])
        sources = item.get("sources") if isinstance(item.get("sources"), list) else snapshot.get("sources", [])
        return {
            "id": item.get("id"),
            "request_id": item.get("request_id") or metadata.get("request_id") or snapshot.get("request_id") or "",
            "message": item.get("message") or snapshot.get("message") or snapshot.get("question") or "",
            "answer": item.get("answer") or snapshot.get("answer") or "",
            "verdict": verdict,
            "feedback_type": item.get("feedback_type") or "answer_quality",
            "human_annotation": item.get("human_annotation") or "",
            "error_reason": item.get("error_reason") or inferred["error_reason"],
            "fix_target": item.get("fix_target") or inferred["fix_target"],
            "suggested_action": item.get("suggested_action") or inferred["suggested_action"],
            "status": item.get("status") or inferred["status"],
            "regression_case_id": item.get("regression_case_id"),
            "notes": item.get("notes") or "",
            "route": route,
            "matched_rule": item.get("matched_rule") or snapshot.get("matched_rule"),
            "used_tools": used_tools if isinstance(used_tools, list) else [],
            "source": sources if isinstance(sources, list) else [],
            "sources": sources if isinstance(sources, list) else [],
            "score": item.get("score") if item.get("score") is not None else self._feedback_score(snapshot),
            "need_human_review": bool(item.get("need_human_review") or snapshot.get("need_human") or metadata.get("need_human_review") or route == "quote_draft"),
            "quality_flags": quality_flags if isinstance(quality_flags, list) else [],
            "next_actions": next_actions if isinstance(next_actions, list) else [],
            "decision_trace": item.get("decision_trace") if isinstance(item.get("decision_trace"), list) else metadata.get("decision_trace", []),
            "created_at": item.get("created_at") or "",
            "updated_at": item.get("updated_at") or "",
        }

    @staticmethod
    def _quality_flag_match(item: dict, flag: str) -> bool:
        flag = flag.strip()
        quality_flags = {str(value) for value in item.get("quality_flags", [])}
        error_reason = str(item.get("error_reason") or "")
        route = str(item.get("route") or "")
        verdict = str(item.get("verdict") or "")
        status = str(item.get("status") or "")
        if flag == "bad_answer":
            return verdict not in {"", "good"} or bool(error_reason)
        if flag == "quote_risk":
            return route == "quote_draft" or verdict == "bad_quote" or any("quote" in value or "commitment" in value for value in quality_flags)
        if flag == "need_human":
            return bool(item.get("need_human_review"))
        if flag == "knowledge_miss":
            return error_reason in {"knowledge_not_found", "missing_knowledge"} or "knowledge_not_found" in quality_flags
        if flag == "resolved":
            return status in {"resolved", "fixed"}
        return True

    @staticmethod
    def _clean_words(values: Any) -> list[str]:
        if isinstance(values, str):
            raw = values.replace("，", ",").replace("、", ",").split(",")
        elif isinstance(values, list):
            raw = values
        else:
            raw = []
        return [str(item).strip() for item in raw if str(item).strip()][:12]

    @staticmethod
    def _keyword_suggestions(answer: str, message: str) -> list[str]:
        text = f"{answer} {message}"
        candidates = []
        for token in ("U-MOCO", "GRA", "EXT", "PRO", "MINI", "AIR", "FreeD", "轨道", "保修", "质保", "报价", "人工", "确认"):
            if token in text and token not in candidates:
                candidates.append(token)
        if not candidates:
            compact = "".join(str(answer or message).split())
            if compact:
                candidates.append(compact[:12])
        return candidates[:5]

    @staticmethod
    def _feedback_case_name(feedback: dict) -> str:
        verdict_labels = {
            "good": "好回答固化",
            "factual_error": "事实错误防回退",
            "missing_knowledge": "资料缺失防回退",
            "wrong_retrieval": "检索错误防回退",
            "style_issue": "话术问题防回退",
            "bad_quote": "报价问题防回退",
            "needs_review": "待复核回答",
        }
        message = str(feedback.get("message") or "").strip()
        prefix = verdict_labels.get(str(feedback.get("verdict") or ""), "回答反馈")
        return f"{prefix}：{message[:24]}" if message else prefix

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
