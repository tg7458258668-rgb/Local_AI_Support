from __future__ import annotations

import re
from typing import Any

from support_app.schemas import ChatRequest
from support_app.services.pricing_catalog_service import PricingCatalogService
from support_app.services.quote_archive_service import QuoteArchiveService
from support_app.services.quote_policy_service import QuotePolicyService


class QuoteService:
    INTENT_WORDS = ("报价", "价格", "多少钱", "预算", "方案", "配置", "定制", "优惠", "便宜", "采购", "直播间", "电视台", "轨道")

    def __init__(
        self,
        catalog_service: PricingCatalogService,
        policy_service: QuotePolicyService,
        archive_service: QuoteArchiveService,
    ):
        self.catalog_service = catalog_service
        self.policy_service = policy_service
        self.archive_service = archive_service

    def is_quote_request(self, message: str) -> bool:
        return any(word in message for word in self.INTENT_WORDS)

    def draft(self, request: ChatRequest, memory: dict | None, doc_candidates: list[Any]) -> dict[str, Any]:
        needs = self.extract_needs(request.message, memory)
        matched_products = self.catalog_service.match_products(request.message)
        if not matched_products:
            matched_products = self._products_from_docs(doc_candidates)
        matched_products = self._rank_by_budget(matched_products, needs.get("budget", ""))
        policy = self.policy_service.get()
        recent_quotes = self.archive_service.recent_for_customer(request.channel, request.user_id)
        quote_items = self._quote_items(matched_products)
        total = self._sum_prices([item.get("reference_price", "") for item in quote_items])
        confirmation = self._confirmation_items(policy)
        draft = {
            "need_summary": self._need_summary(needs),
            "recommended_products": matched_products[:3],
            "quote_items": quote_items,
            "reference_total": total,
            "pricing_policy": policy,
            "recent_quotes": recent_quotes,
            "sources": [item.get("source", "") for item in matched_products[:5] if item.get("source")],
            "requires_confirmation": confirmation,
            "status": "draft",
        }
        answer = self._render_answer(draft)
        archive_item = self.archive_service.add_for_customer(request.channel, request.user_id, {
            "need_summary": draft["need_summary"],
            "recommended_products": [item.get("product", "") for item in matched_products[:3]],
            "quote_items": quote_items,
            "reference_total": total,
            "sources": draft["sources"],
            "requires_confirmation": confirmation,
            "answer": answer,
            "status": "draft",
        })
        if archive_item:
            draft["archive"] = archive_item
        return {"answer": answer, "draft": draft}

    def extract_needs(self, message: str, memory: dict | None = None) -> dict[str, Any]:
        text = str(message or "")
        memory = memory or {}
        return {
            "scenario": self._first_match(text, ("直播间", "团播", "电视台", "影视", "广告", "电商", "虚拟拍摄")) or memory.get("scenario", ""),
            "budget": self._budget(text) or memory.get("budget", ""),
            "project_time": self._first_time(text) or memory.get("project_time", ""),
            "decision_status": self._first_match(text, ("先了解", "近期采购", "马上要", "招标", "比价", "老板确认")) or memory.get("decision_status", ""),
            "concerns": self._concerns(text) or memory.get("concerns", []),
            "preferred_products": self._preferred_products(text) or memory.get("products", []),
            "track_meters": self._track_meters(text),
            "raw_message": text[:200],
        }

    @staticmethod
    def _products_from_docs(doc_candidates: list[Any]) -> list[dict[str, Any]]:
        rows = []
        for item in doc_candidates[:5]:
            payload = item.payload or {}
            price_fields = payload.get("price_fields") or {}
            if not price_fields:
                continue
            rows.append({
                "product": str(payload.get("doc_name", "")).rsplit("_20", 1)[0].replace("_", " "),
                "version": "",
                "base_price": price_fields.get("总价（含税13%）") or price_fields.get("总价") or price_fields.get("合计") or "",
                "historical_offer": price_fields.get("优惠价", ""),
                "source": payload.get("source", ""),
                "doc_name": payload.get("doc_name", ""),
                "configuration": [line.strip(" -") for line in str(payload.get("text", "")).splitlines() if line.strip()][:12],
            })
        return rows

    @staticmethod
    def _quote_items(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for item in products[:1]:
            price = item.get("base_price") or item.get("historical_offer") or ""
            rows.append({
                "name": " ".join(part for part in (item.get("product", ""), item.get("version", "")) if part).strip(),
                "quantity": 1,
                "reference_price": price,
                "historical_offer": item.get("historical_offer", ""),
                "source": item.get("source", ""),
            })
        return rows

    @classmethod
    def _rank_by_budget(cls, products: list[dict[str, Any]], budget: str) -> list[dict[str, Any]]:
        budget_value = cls._money_to_number(budget)
        if not budget_value:
            return products
        return sorted(
            products,
            key=lambda item: (
                0 if cls._money_to_number(item.get("base_price", "")) <= budget_value * 1.25 else 1,
                abs(cls._money_to_number(item.get("base_price", "")) - budget_value),
            ),
        )

    @staticmethod
    def _render_answer(draft: dict[str, Any]) -> str:
        products = draft.get("recommended_products", [])
        first = products[0] if products else {}
        product_name = " ".join(part for part in (first.get("product", ""), first.get("version", "")) if part).strip() or "合适的 U-MOCO 方案"
        config = "、".join(first.get("configuration", [])[:6]) or "机械臂本体、控制器、软件授权及必要拍摄附件"
        total = draft.get("reference_total") or "需按最终配置核算"
        need_summary = draft.get("need_summary") or "你的使用需求"
        confirm = "、".join(draft.get("requires_confirmation", []))
        lines = [
            f"按你现在的需求，我会先把它当成“{need_summary}”来做报价草案。",
            f"我更建议先看 {product_name}，这类方案比较贴近你的拍摄/交付场景，核心配置可以按 {config} 来展开。",
            f"参考标价先按 {total} 作为预算口径；如果后面要加轨道米数、FreeD 跟踪、跟焦、软件授权或现场培训，我会把这些作为可选项单独拆出来。",
            f"优惠价、交付时间、合同条款和特殊定制需要人工同事复核后才能作为正式报价。当前需要确认：{confirm}。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _need_summary(needs: dict[str, Any]) -> str:
        parts = []
        if needs.get("scenario"):
            parts.append(str(needs["scenario"]))
        if needs.get("preferred_products"):
            parts.append("关注 " + "、".join(needs["preferred_products"][:3]))
        if needs.get("budget"):
            parts.append("预算 " + str(needs["budget"]))
        if needs.get("track_meters"):
            parts.append(f"{needs['track_meters']} 米轨道")
        return "，".join(parts) or "待进一步确认的拍摄方案"

    @staticmethod
    def _confirmation_items(policy: dict[str, Any]) -> list[str]:
        items = policy.get("approval_required", [])
        return items if isinstance(items, list) else ["优惠价", "交付时间", "合同条款"]

    @staticmethod
    def _sum_prices(values: list[str]) -> str:
        total = 0.0
        currency = "¥"
        for value in values:
            match = re.search(r"([¥￥])\s*([\d,]+(?:\.\d+)?)", str(value))
            if not match:
                continue
            currency = match.group(1)
            total += float(match.group(2).replace(",", ""))
        if total <= 0:
            return ""
        return f"{currency}{total:,.0f}"

    @staticmethod
    def _money_to_number(value: str) -> float:
        text = str(value or "").replace(",", "").replace(" ", "")
        if not text:
            return 0.0
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match:
            return 0.0
        amount = float(match.group(1))
        if "万" in text:
            amount *= 10000
        elif "千" in text:
            amount *= 1000
        return amount

    @staticmethod
    def _budget(text: str) -> str:
        match = re.search(r"预算\s*([¥￥]?\s*\d+(?:\.\d+)?\s*[万千]?)", text)
        if match:
            return match.group(1).replace(" ", "")
        match = re.search(r"(\d+(?:\.\d+)?\s*万)左右", text)
        return match.group(1).replace(" ", "") if match else ""

    @staticmethod
    def _track_meters(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*米\s*轨道", text)
        return match.group(1) if match else ""

    @staticmethod
    def _preferred_products(text: str) -> list[str]:
        products = []
        for token in ("AIR", "MINI", "GRA", "PRO", "EXT", "mini", "Mini", "gra", "pro", "ext"):
            if token in text:
                products.append(token.upper())
        return list(dict.fromkeys(products))

    @staticmethod
    def _concerns(text: str) -> list[str]:
        return [word for word in ("预算", "优惠", "交付", "合同", "跟踪", "跟焦", "轨道", "培训") if word in text]

    @staticmethod
    def _first_match(text: str, words: tuple[str, ...]) -> str:
        for word in words:
            if word in text:
                return word
        return ""

    @staticmethod
    def _first_time(text: str) -> str:
        match = re.search(r"(本周|下周|这个月|下个月|\d+月|\d+天内|\d+号)", text)
        return match.group(1) if match else ""
