from __future__ import annotations

import re
from typing import Any

from support_app.repositories.document_repository import DocumentRepository
from support_app.repositories.json_file_repository import JsonFileRepository


class PricingCatalogService:
    PRODUCT_KEYWORDS = ("AIR", "MINI", "GRA", "PRO", "EXT")

    def __init__(self, store: JsonFileRepository, document_repo: DocumentRepository):
        self.store = store
        self.document_repo = document_repo

    def get(self) -> dict[str, Any]:
        saved = self.store.load_object()
        if saved:
            return saved
        return self.build_from_documents()

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        catalog = {
            "products": payload.get("products", []),
            "accessories": payload.get("accessories", []),
            "updated_at": payload.get("updated_at", ""),
        }
        self.store.save_object(catalog)
        return catalog

    def build_from_documents(self) -> dict[str, Any]:
        products = []
        seen = set()
        for row in self.document_repo.list():
            text = str(row.get("text", ""))
            price_fields = row.get("price_fields") or {}
            if not price_fields:
                continue
            if set(price_fields.keys()) == {"全部金额"}:
                continue
            product = self._detect_product(row, text)
            if not product:
                continue
            base_price = self._best_price(price_fields, prefer_discount=False)
            history_price = self._best_price(price_fields, prefer_discount=True)
            key = (product, str(row.get("source", "")), base_price, history_price)
            if key in seen:
                continue
            seen.add(key)
            products.append({
                "product": product,
                "version": self._detect_version(text),
                "base_price": base_price,
                "historical_offer": history_price if history_price != base_price else "",
                "source": row.get("source", ""),
                "doc_name": row.get("doc_name", ""),
                "configuration": self._configuration_lines(text),
            })
        return {"products": products, "accessories": self._default_accessories(), "updated_at": ""}

    def match_products(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        catalog = self.get()
        query_upper = query.upper()
        scored = []
        for item in catalog.get("products", []):
            haystack = f"{item.get('product', '')} {item.get('version', '')} {item.get('source', '')} {' '.join(item.get('configuration', []))}".upper()
            score = 0
            for token in self.PRODUCT_KEYWORDS:
                if token in query_upper and token in haystack:
                    score += 3
            for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2}", query):
                if token.upper() in haystack:
                    score += 1
            if score:
                scored.append((score, item))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

    @staticmethod
    def _detect_product(row: dict[str, Any], text: str) -> str:
        haystack = f"{row.get('doc_name', '')} {row.get('source', '')} {text}".upper()
        found = [token for token in PricingCatalogService.PRODUCT_KEYWORDS if token in haystack]
        if not found:
            return ""
        if "U-MOCO" in haystack:
            return "U-MOCO " + " + ".join(dict.fromkeys(found))
        return " + ".join(dict.fromkeys(found))

    @staticmethod
    def _detect_version(text: str) -> str:
        if "旗舰" in text:
            return "旗舰版"
        if "专业" in text:
            return "专业版"
        if "标准" in text:
            return "标准版"
        return ""

    @staticmethod
    def _best_price(price_fields: dict[str, Any], prefer_discount: bool) -> str:
        keys = ("优惠价", "总价（含税13%）", "总价", "合计") if prefer_discount else ("总价（含税13%）", "总价", "合计", "优惠价")
        for key in keys:
            value = str(price_fields.get(key, "")).strip()
            if value:
                return value
        amounts = str(price_fields.get("全部金额", "")).split("、")
        return amounts[-1].strip() if amounts else ""

    @staticmethod
    def _configuration_lines(text: str) -> list[str]:
        rows = []
        for line in text.splitlines():
            clean = line.strip(" -•\t")
            if clean and any(token in clean for token in ("U-MOCO", "轨道", "跟焦", "FreeD", "软件", "控制器", "采集卡", "示教器", "兔笼")):
                rows.append(clean)
        return rows[:18]

    @staticmethod
    def _default_accessories() -> list[dict[str, str]]:
        return [
            {"name": "影视地面轨道", "unit": "米", "reference_price": "¥15,000", "source": "历史报价单"},
            {"name": "影视地面轨道", "unit": "节/2米", "reference_price": "¥12,500", "source": "历史报价单"},
            {"name": "FreeD 跟踪协议", "unit": "套", "reference_price": "", "source": "历史配置项"},
            {"name": "自动跟焦模块", "unit": "套", "reference_price": "", "source": "历史配置项"},
        ]
