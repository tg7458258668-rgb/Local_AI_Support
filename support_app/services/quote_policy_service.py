from __future__ import annotations

from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository


class QuotePolicyService:
    DEFAULT_POLICY = {
        "mode": "draft_only",
        "default_when_unconfigured": "list_price_only",
        "max_discount_percent": "",
        "min_margin_note": "",
        "approval_required": ["优惠价", "低于标价", "交付时间", "合同条款", "特殊定制"],
        "reply_style": "sales_talk",
        "template": "先复述客户场景，再推荐方案，给参考标价和可选项，最后说明优惠/交付/合同需要人工确认。",
    }

    def __init__(self, store: JsonFileRepository):
        self.store = store

    def get(self) -> dict[str, Any]:
        data = self.store.load_object()
        return data or dict(self.DEFAULT_POLICY)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        policy = {**self.DEFAULT_POLICY, **payload}
        if not isinstance(policy.get("approval_required"), list):
            policy["approval_required"] = self.DEFAULT_POLICY["approval_required"]
        self.store.save_object(policy)
        return policy

    def discount_configured(self) -> bool:
        policy = self.get()
        return bool(str(policy.get("max_discount_percent", "")).strip())
