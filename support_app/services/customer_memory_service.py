from __future__ import annotations

import re

from support_app.repositories.customer_memory_repository import CustomerMemoryRepository
from support_app.schemas import ChatRequest
from support_app.settings import Settings


class CustomerMemoryService:
    PRODUCT_HINTS = ["电池", "充电器", "电机", "控制器", "轮胎", "刹车", "显示屏", "配件"]
    RISK_HINTS = ["投诉", "退款", "赔偿", "合同", "发票", "威胁", "差评", "律师"]
    PREFERENCE_HINTS = ["便宜", "优惠", "加急", "尽快", "不要打电话", "微信联系", "飞书联系"]

    def __init__(self, settings: Settings, repo: CustomerMemoryRepository):
        self.settings = settings
        self.repo = repo

    def load_for_request(self, request: ChatRequest) -> dict | None:
        if not self._enabled(request):
            return None
        return self.repo.get(request.channel, request.user_id or "")

    def update_from_turn(self, request: ChatRequest, answer: str, route: str) -> dict | None:
        if not self._enabled(request):
            return None
        updates = self._extract(request.message)
        if route in ("handoff", "error"):
            updates.setdefault("risk_flags", []).append("需要人工关注")
        if not any(updates.values()):
            return self.repo.get(request.channel, request.user_id or "")
        return self.repo.upsert(request.channel, request.user_id or "", updates)

    def list(self, q: str = "") -> dict:
        items = self.repo.list(q)
        return {"total": len(items), "items": items[:200]}

    def replace(self, channel: str, user_id: str, payload: dict) -> dict:
        return self.repo.replace(channel, user_id, payload)

    def delete(self, channel: str, user_id: str) -> None:
        self.repo.delete(channel, user_id)

    def render_prompt_block(self, memory: dict | None) -> str:
        if not memory:
            return ""
        lines = []
        if memory.get("customer_name"):
            lines.append(f"客户称呼：{memory['customer_name']}")
        if memory.get("products"):
            lines.append(f"已购/咨询产品：{'、'.join(memory['products'])}")
        if memory.get("preferences"):
            lines.append(f"客户偏好：{'、'.join(memory['preferences'])}")
        if memory.get("common_questions"):
            lines.append(f"历史常问：{'、'.join(memory['common_questions'][:5])}")
        if memory.get("risk_flags"):
            lines.append(f"风险标记：{'、'.join(memory['risk_flags'])}")
        if memory.get("scenario"):
            lines.append(f"使用场景：{memory['scenario']}")
        if memory.get("budget"):
            lines.append(f"预算：{memory['budget']}")
        if memory.get("project_time"):
            lines.append(f"项目时间：{memory['project_time']}")
        if memory.get("decision_status"):
            lines.append(f"决策状态：{memory['decision_status']}")
        if memory.get("concerns"):
            lines.append(f"关注点：{'、'.join(memory['concerns'])}")
        if memory.get("quoted_schemes"):
            lines.append(f"历史报价方案：{'、'.join(memory['quoted_schemes'][:3])}")
        if memory.get("notes"):
            lines.append(f"备注：{memory['notes']}")
        if not lines:
            return ""
        return "客户关键画像（仅用于延续上下文，不得编造事实）：\n" + "\n".join(lines)

    def _enabled(self, request: ChatRequest) -> bool:
        return bool(self.settings.memory_enabled and request.user_id)

    def _extract(self, text: str) -> dict:
        updates: dict[str, list[str] | str] = {
            "products": [],
            "preferences": [],
            "common_questions": [],
            "risk_flags": [],
            "concerns": [],
            "quoted_schemes": [],
        }
        cleaned = str(text or "").strip()
        name_match = re.search(r"(我叫|我是|叫我)([\u4e00-\u9fa5A-Za-z0-9_-]{2,12})", cleaned)
        if name_match:
            updates["customer_name"] = name_match.group(2)
        phone_match = re.search(r"1[3-9]\d{9}", cleaned)
        if phone_match:
            updates["contact"] = phone_match.group(0)
        for word in self.PRODUCT_HINTS:
            if word in cleaned:
                updates["products"].append(word)
        for word in self.PREFERENCE_HINTS:
            if word in cleaned:
                updates["preferences"].append(word)
        for word in self.RISK_HINTS:
            if word in cleaned:
                updates["risk_flags"].append(word)
        for word in ("直播间", "团播", "电视台", "影视", "广告", "电商", "虚拟拍摄"):
            if word in cleaned:
                updates["scenario"] = word
                break
        budget_match = re.search(r"(预算\s*)?([¥￥]?\s*\d+(?:\.\d+)?\s*[万千]?)", cleaned)
        if "预算" in cleaned and budget_match:
            updates["budget"] = budget_match.group(2).replace(" ", "")
        time_match = re.search(r"(本周|下周|这个月|下个月|\d+月|\d+天内|\d+号)", cleaned)
        if time_match:
            updates["project_time"] = time_match.group(1)
        for word in ("先了解", "近期采购", "马上要", "招标", "比价", "老板确认"):
            if word in cleaned:
                updates["decision_status"] = word
                break
        for word in ("预算", "优惠", "交付", "合同", "跟踪", "跟焦", "轨道", "培训"):
            if word in cleaned:
                updates["concerns"].append(word)
        for word in ("AIR", "MINI", "GRA", "PRO", "EXT", "mini", "gra", "pro", "ext"):
            if word in cleaned:
                updates["products"].append(word.upper())
        if "?" in cleaned or "？" in cleaned or any(word in cleaned for word in ["怎么", "多久", "能不能", "是否", "可以"]):
            updates["common_questions"].append(cleaned[:80])
        return {key: value for key, value in updates.items() if value}
