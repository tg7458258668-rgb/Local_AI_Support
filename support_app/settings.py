from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    qdrant_url: str
    ollama_url: str
    embed_model: str
    chat_model: str
    faq_collection: str
    doc_collection: str
    top_k_faq: int
    top_k_doc: int
    faq_score_threshold: float
    doc_score_threshold: float
    faq_doc_margin: float
    retrieval_cache_ttl_seconds: int
    faq_direct_answer_threshold: float
    memory_enabled: bool

    @classmethod
    def from_env(cls) -> "Settings":
        base_dir = Path(os.getenv("AI_CS_BASE_DIR", Path(__file__).resolve().parent.parent))
        data_dir = Path(os.getenv("AI_CS_DATA_DIR", base_dir / "data"))
        return cls(
            base_dir=base_dir,
            data_dir=data_dir,
            qdrant_url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            embed_model=os.getenv("EMBED_MODEL", "bge-m3"),
            chat_model=os.getenv("CHAT_MODEL", "qwen3:8b"),
            faq_collection=os.getenv("FAQ_COLLECTION", "company_kb"),
            doc_collection=os.getenv("DOC_COLLECTION", "docs_kb"),
            top_k_faq=int(os.getenv("TOP_K_FAQ", "3")),
            top_k_doc=int(os.getenv("TOP_K_DOC", "5")),
            faq_score_threshold=float(os.getenv("FAQ_SCORE_THRESHOLD", "0.68")),
            doc_score_threshold=float(os.getenv("DOC_SCORE_THRESHOLD", "0.40")),
            faq_doc_margin=float(os.getenv("FAQ_DOC_MARGIN", "0.10")),
            retrieval_cache_ttl_seconds=int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "300")),
            faq_direct_answer_threshold=float(os.getenv("FAQ_DIRECT_ANSWER_THRESHOLD", "0.88")),
            memory_enabled=os.getenv("MEMORY_ENABLED", "true").lower() not in ("0", "false", "no"),
        )


settings = Settings.from_env()
