from __future__ import annotations

from typing import Any

from support_app.services.quote_policy_service import QuotePolicyService


class KnowledgeGapService:
    def __init__(self, quote_policy_service: QuotePolicyService):
        self.quote_policy_service = quote_policy_service

    def analyze(
        self,
        message: str,
        route: str,
        faq_top_score: float,
        doc_top_score: float,
        memory: dict | None,
        metadata: dict[str, Any] | None = None,
        need_human: bool = False,
    ) -> dict[str, Any]:
        text = str(message or "")
        memory = memory or {}
        gaps = []
        questions = []
        docs_needed = []

        if route in ("identity", "memory_recall", "learned_correction"):
            return {
                "has_gaps": False,
                "gaps": [],
                "suggested_questions": [],
                "needed_documents": [],
            }

        if route == "fallback" or max(faq_top_score, doc_top_score) < 0.45:
            gaps.append(self._gap("low_retrieval_confidence", "检索置信度偏低", "建议补充与该问题直接相关的产品资料、报价单或 FAQ。"))
            docs_needed.append(self._needed_document_label(text))

        if self._is_quote_like(text):
            missing_need_questions = self._missing_quote_questions(text, memory)
            if missing_need_questions:
                gaps.append(self._gap("missing_customer_need", "客户需求信息不足", "先追问预算、场景、配置和交付时间，再生成更靠谱的报价草案。"))
                questions.extend(missing_need_questions)

            policy = self.quote_policy_service.get()
            if not policy.get("max_discount_percent") and "优惠" in text:
                gaps.append(self._gap("missing_price_rule", "缺少优惠审批规则", "后台需要配置最大折扣、底价说明或人工审批口径。"))

        if need_human:
            gaps.append(self._gap("needs_human_policy", "本轮涉及人工确认", "合同、交付、优惠、特殊定制等内容需要人工复核。"))

        if "文档" in text or "资料" in text or route == "doc":
            if doc_top_score < 0.55:
                docs_needed.append("更完整的产品资料或可复制文字 PDF/DOCX")

        return {
            "has_gaps": bool(gaps or questions or docs_needed),
            "gaps": gaps,
            "suggested_questions": list(dict.fromkeys(questions))[:8],
            "needed_documents": list(dict.fromkeys(docs_needed))[:6],
        }

    @staticmethod
    def _gap(kind: str, title: str, detail: str) -> dict[str, str]:
        return {"type": kind, "title": title, "detail": detail}

    @staticmethod
    def _is_quote_like(text: str) -> bool:
        return any(word in text for word in ("报价", "价格", "多少钱", "预算", "方案", "配置", "优惠", "直播间", "电视台", "轨道"))

    @staticmethod
    def _needed_document_label(text: str) -> str:
        product = ""
        for token in ("mini", "MINI", "GRA", "PRO", "EXT", "AIR", "U-MOCO"):
            if token in text:
                product = token.upper()
                break
        if any(word in text for word in ("保修", "质保", "售后", "维修")):
            prefix = f"{product} " if product else ""
            return f"{prefix}保修/质保政策文档，需包含保修期限、保修范围和不保修情况。"
        if any(word in text for word in ("配置", "包含", "参数", "功能")):
            prefix = f"{product} " if product else ""
            return f"{prefix}产品配置说明，需包含标准配置、选配项和适用版本。"
        if any(word in text for word in ("报价", "价格", "多少钱", "费用", "优惠")):
            prefix = f"{product} " if product else ""
            return f"{prefix}报价单或价目表，需包含标价、选配项和优惠审批口径。"
        return "与客户问题同主题的产品说明、报价单、售后政策或 FAQ。"

    @staticmethod
    def _missing_quote_questions(text: str, memory: dict) -> list[str]:
        questions = []
        if not memory.get("scenario") and not any(word in text for word in ("直播间", "团播", "电视台", "影视", "广告", "电商", "虚拟拍摄")):
            questions.append("客户主要使用场景是什么？例如直播间、电视台、影视拍摄或电商。")
        if not memory.get("budget") and "预算" not in text:
            questions.append("客户大概预算范围是多少？")
        if "轨道" in text and "米" not in text:
            questions.append("轨道需要几米？场地尺寸和运动范围是多少？")
        if not memory.get("project_time") and not any(word in text for word in ("本周", "下周", "这个月", "下个月", "交付", "多久")):
            questions.append("项目预计什么时候使用或交付？")
        if not any(word in text for word in ("FreeD", "跟踪", "跟焦", "培训")):
            questions.append("是否需要 FreeD 跟踪、跟焦、现场培训或软件授权等选配？")
        return questions
