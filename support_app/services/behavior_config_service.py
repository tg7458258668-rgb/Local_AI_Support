from __future__ import annotations

from datetime import datetime
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository


class BehaviorConfigService:
    def __init__(self, behavior_store: JsonFileRepository, style_store: JsonFileRepository):
        self.behavior_store = behavior_store
        self.style_store = style_store

    def get_behavior_rules(self) -> dict[str, Any]:
        data = self.behavior_store.load_object()
        return data if data else self._default_behavior_rules()

    def save_behavior_rules(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = self._deep_merge(self._default_behavior_rules(), payload or {})
        item["updated_at"] = self._now()
        self.behavior_store.save_object(item)
        return item

    def get_answer_styles(self) -> dict[str, Any]:
        data = self.style_store.load_object()
        return data if data else self._default_answer_styles()

    def save_answer_styles(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = self._deep_merge(self._default_answer_styles(), payload or {})
        item["updated_at"] = self._now()
        self.style_store.save_object(item)
        return item

    def apply_patch(self, behavior_patch: dict | None = None, style_patch: dict | None = None) -> dict[str, Any]:
        behavior = self.save_behavior_rules(self._deep_merge(self.get_behavior_rules(), behavior_patch or {}))
        styles = self.save_answer_styles(self._deep_merge(self.get_answer_styles(), style_patch or {}))
        return {"behavior_rules": behavior, "answer_styles": styles}

    def memory_policy(self) -> dict[str, Any]:
        return self.get_behavior_rules().get("memory_policy", {})

    def fallback_policy(self) -> dict[str, Any]:
        return self.get_behavior_rules().get("fallback_policy", {})

    def fallback_gap_template(self) -> str:
        return str(self.get_answer_styles().get("fallback_gap_template", "") or "")

    def memory_recall_template(self) -> str:
        return str(self.get_answer_styles().get("memory_recall_template", "") or "")

    @staticmethod
    def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = BehaviorConfigService._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _default_behavior_rules() -> dict[str, Any]:
        return {
            "memory_policy": {
                "previous_context_words": ["上次", "之前", "刚才", "前面", "上一轮", "那个", "这款"],
                "product_recall_words": ["什么机械臂", "哪个机械臂", "聊的什么", "是什么产品", "什么产品"],
                "previous_product_anchor": True,
            },
            "fallback_policy": {"active_gap_prompt_on_test_page": True},
            "intent_rules": [],
            "updated_at": "",
        }

    @staticmethod
    def _default_answer_styles() -> dict[str, Any]:
        return {
            "fallback_gap_template": (
                "我现在还不能确认这个问题，因为知识库里没有命中足够可靠的资料。\n"
                "我需要你补充：{needed_document}\n"
                "补充后我会把它入库，后续再问同类问题就能直接按资料回答。"
            ),
            "memory_recall_template": "你上次记录里关注的是 {product}。如果你现在要继续问价格或配置，我会优先按这个型号来查。",
            "quote_disclaimer": "优惠价、交付时间、合同条款和特殊定制需要人工同事复核后才能作为正式报价。",
            "updated_at": "",
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
