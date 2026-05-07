from functools import lru_cache

from support_app.repositories.rule_repository import RuleRepository
from support_app.repositories.vector_repository import VectorRepository
from support_app.repositories.document_repository import DocumentRepository
from support_app.repositories.faq_repository import FAQRepository
from support_app.repositories.category_repository import CategoryRepository
from support_app.repositories.customer_memory_repository import CustomerMemoryRepository
from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.repositories.quote_archive_repository import QuoteArchiveRepository
from support_app.services.admin_service import AdminService
from support_app.services.audit_service import AuditService
from support_app.services.chat_service import ChatService
from support_app.services.customer_memory_service import CustomerMemoryService
from support_app.services.document_ingestion_service import DocumentIngestionService
from support_app.services.faq_index_service import FAQIndexService
from support_app.services.ollama_client import OllamaClient
from support_app.services.pricing_catalog_service import PricingCatalogService
from support_app.services.quote_archive_service import QuoteArchiveService
from support_app.services.quote_policy_service import QuotePolicyService
from support_app.services.quote_service import QuoteService
from support_app.services.retrieval_service import RetrievalService
from support_app.settings import settings


@lru_cache
def get_ollama_client() -> OllamaClient:
    return OllamaClient(settings)


@lru_cache
def get_rule_repository() -> RuleRepository:
    return RuleRepository(settings.data_dir / "faq_priority_rules.csv")


@lru_cache
def get_faq_repository() -> FAQRepository:
    return FAQRepository(settings.data_dir / "faq.json")


@lru_cache
def get_document_repository() -> DocumentRepository:
    return DocumentRepository(settings.data_dir / "docs_chunks" / "docs_chunks.json")


@lru_cache
def get_category_repository() -> CategoryRepository:
    return CategoryRepository(
        settings.data_dir / "category_options.json",
        get_faq_repository(),
        get_rule_repository(),
    )


@lru_cache
def get_vector_repository() -> VectorRepository:
    return VectorRepository(settings, get_ollama_client())


@lru_cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(settings, get_ollama_client(), get_vector_repository())


@lru_cache
def get_customer_memory_repository() -> CustomerMemoryRepository:
    return CustomerMemoryRepository(settings.data_dir / "customer_memories.json")


@lru_cache
def get_customer_memory_service() -> CustomerMemoryService:
    return CustomerMemoryService(settings, get_customer_memory_repository())


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService(settings.base_dir / "runtime")


@lru_cache
def get_pricing_catalog_service() -> PricingCatalogService:
    return PricingCatalogService(
        JsonFileRepository(settings.data_dir / "pricing_catalog.json"),
        get_document_repository(),
    )


@lru_cache
def get_quote_policy_service() -> QuotePolicyService:
    return QuotePolicyService(JsonFileRepository(settings.data_dir / "quote_policies.json"))


@lru_cache
def get_quote_archive_repository() -> QuoteArchiveRepository:
    return QuoteArchiveRepository(settings.data_dir / "quote_archives.json")


@lru_cache
def get_quote_archive_service() -> QuoteArchiveService:
    return QuoteArchiveService(get_quote_archive_repository())


@lru_cache
def get_quote_service() -> QuoteService:
    return QuoteService(
        get_pricing_catalog_service(),
        get_quote_policy_service(),
        get_quote_archive_service(),
    )


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        settings=settings,
        ollama=get_ollama_client(),
        retrieval_service=get_retrieval_service(),
        rule_repo=get_rule_repository(),
        memory_service=get_customer_memory_service(),
        audit_service=get_audit_service(),
        quote_service=get_quote_service(),
    )


@lru_cache
def get_faq_index_service() -> FAQIndexService:
    return FAQIndexService(settings, get_faq_repository(), get_ollama_client())


@lru_cache
def get_document_ingestion_service() -> DocumentIngestionService:
    return DocumentIngestionService(
        settings,
        get_document_repository(),
        get_ollama_client(),
        get_retrieval_service(),
    )


@lru_cache
def get_admin_service() -> AdminService:
    return AdminService(
        document_repo=get_document_repository(),
        faq_repo=get_faq_repository(),
        rule_repo=get_rule_repository(),
        category_repo=get_category_repository(),
        faq_index_service=get_faq_index_service(),
        memory_service=get_customer_memory_service(),
        document_ingestion_service=get_document_ingestion_service(),
        pricing_catalog_service=get_pricing_catalog_service(),
        quote_policy_service=get_quote_policy_service(),
        quote_archive_service=get_quote_archive_service(),
    )
