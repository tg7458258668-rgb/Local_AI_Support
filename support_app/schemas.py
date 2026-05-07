from typing import Any, Literal

from pydantic import BaseModel, Field


ChannelName = Literal["api", "wechat", "feishu"]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    channel: ChannelName = "api"
    conversation_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyAskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class SourceItem(BaseModel):
    type: Literal["faq", "doc"]
    score: float | None = None
    adjusted_score: float | None = None
    source: str = ""
    category: str = ""
    question: str = ""
    doc_name: str = ""
    section: str = ""
    reason: str = ""


class TimingInfo(BaseModel):
    rule_match_ms: float = 0
    memory_ms: float = 0
    faq_retrieval_ms: float = 0
    doc_retrieval_ms: float = 0
    route_decision_ms: float = 0
    answer_generation_ms: float = 0
    source_format_ms: float = 0
    total_ms: float = 0
    retrieval_cache_hit: bool = False


class ChatResponse(BaseModel):
    answer: str
    route: Literal["faq", "doc", "quote_draft", "handoff", "fallback", "error"]
    need_human: bool = False
    hint: str = ""
    matched_rule: str | None = None
    faq_top_score: float = 0
    doc_top_score: float = 0
    sources: list[SourceItem] = Field(default_factory=list)
    retrieval_debug: list[dict[str, Any]] = Field(default_factory=list)
    memory: dict[str, Any] | None = None
    timings: TimingInfo = Field(default_factory=TimingInfo)
    channel: ChannelName = "api"
    conversation_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationWebhookRequest(BaseModel):
    channel: ChannelName
    payload: dict[str, Any] = Field(default_factory=dict)


class IntegrationWebhookResponse(BaseModel):
    channel: ChannelName
    reply_text: str
    rendered: dict[str, Any] = Field(default_factory=dict)
    raw_response: ChatResponse


class FAQItem(BaseModel):
    id: str | None = None
    questions: list[str] = Field(default_factory=list)
    answer: str = ""
    category: str = ""
    source: str = ""
    tags: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive"] = "active"
    priority: int = 1
    updated_at: str = ""


class RuleItem(BaseModel):
    id: str | None = None
    rule_name: str = ""
    keywords: list[str] = Field(default_factory=list)
    category: str = ""
    priority: int = 1
    status: Literal["active", "inactive"] = "active"
    action: Literal["faq_first", "manual_required", "doc_first", "block_commitment"] = "faq_first"
    note: str = ""
    updated_at: str = ""


class CategoryItem(BaseModel):
    name: str
    faq_count: int = 0
    rule_count: int = 0


class AdminListResponse(BaseModel):
    total: int
    items: list[dict[str, Any]]


class ReindexResult(BaseModel):
    collection: str
    faq_count: int
    point_count: int


class CustomerMemoryItem(BaseModel):
    channel: ChannelName = "api"
    user_id: str
    customer_name: str = ""
    contact: str = ""
    products: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    common_questions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    scenario: str = ""
    budget: str = ""
    project_time: str = ""
    decision_status: str = ""
    concerns: list[str] = Field(default_factory=list)
    quoted_schemes: list[str] = Field(default_factory=list)
    notes: str = ""
    updated_at: str = ""
