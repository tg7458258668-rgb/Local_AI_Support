from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.schemas import ChatRequest, ChatResponse


class ConversationHistoryService:
    DEFAULT_LIMIT = 6
    PRODUCT_HINTS = ("U-MOCO", "UMOCO", "GRA", "MINI", "AIR", "EXT", "PRO", "FreeD", "OS PRO", "OS LITE")

    def __init__(self, store: JsonFileRepository, limit: int = DEFAULT_LIMIT):
        self.store = store
        self.limit = max(1, int(limit or self.DEFAULT_LIMIT))

    def recent_for_request(self, request: ChatRequest, limit: int | None = None) -> list[dict[str, Any]]:
        key = self._key(request.channel, request.conversation_id)
        if not key:
            return []
        data = self.store.load_object()
        turns = data.get(key, []) if isinstance(data, dict) else []
        if not isinstance(turns, list):
            return []
        return turns[-max(1, int(limit or self.limit)):]

    def append_turn(self, request: ChatRequest, response: ChatResponse) -> None:
        metadata = request.metadata or {}
        if metadata.get("model_compare_role") == "shadow":
            return
        if metadata.get("regression_test") and not (
            metadata.get("model_compare") and metadata.get("model_compare_role") == "primary"
        ):
            return
        key = self._key(request.channel, request.conversation_id)
        if not key:
            return
        data = self.store.load_object()
        if not isinstance(data, dict):
            data = {}
        turns = data.get(key, [])
        if not isinstance(turns, list):
            turns = []
        turns.append({
            "message": request.message[:500],
            "answer": response.answer[:700],
            "route": response.route,
            "sources": self._source_summary(response),
            "memory_summary": self._memory_summary(response.memory),
            "created_at": self._now(),
        })
        data[key] = turns[-self.limit:]
        self.store.save_object(data)

    def prompt_block(self, history: list[dict[str, Any]]) -> str:
        if not history:
            return ""
        lines = ["最近对话上下文（仅用于理解追问，不得编造事实）："]
        for index, item in enumerate(history[-self.limit:], start=1):
            lines.append(f"{index}. 客户：{item.get('message', '')}")
            answer = str(item.get("answer", "") or "").replace("\n", " ")
            if answer:
                lines.append(f"   客服：{answer[:180]}")
            if item.get("route"):
                lines.append(f"   路由：{item.get('route')}")
        return "\n".join(lines)

    def debug_summary(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for item in history[-self.limit:]:
            rows.append({
                "message": item.get("message", ""),
                "answer": item.get("answer", ""),
                "route": item.get("route", ""),
                "sources": item.get("sources", []),
                "memory_summary": item.get("memory_summary", {}),
                "created_at": item.get("created_at", ""),
            })
        return rows

    def fingerprint(self, history: list[dict[str, Any]]) -> str:
        if not history:
            return ""
        payload = [
            {
                "message": item.get("message", ""),
                "route": item.get("route", ""),
                "sources": item.get("sources", []),
            }
            for item in history[-self.limit:]
        ]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def product_anchors(self, history: list[dict[str, Any]]) -> list[str]:
        found: list[str] = []

        def collect_from_text(text: str) -> None:
            upper = text.upper()
            for hint in self.PRODUCT_HINTS:
                if hint.upper() in upper:
                    found.append(hint)
            for match in re.finditer(r"U-?MOCO\s+(?:GRA|MINI|AIR|EXT|PRO)", text, flags=re.I):
                found.append(match.group(0).upper().replace("UMOCO", "U-MOCO"))

        recent = history[-self.limit:]
        collect_from_text("\n".join(str(item.get("message", "") or "") for item in recent))
        for item in recent:
            memory_products = (item.get("memory_summary") or {}).get("products") or []
            for product in memory_products:
                if product:
                    found.append(str(product))
        if not found:
            collect_from_text("\n".join(str(item.get("answer", "") or "") for item in recent))
        return list(dict.fromkeys(found))[:6]

    @staticmethod
    def _key(channel: str, conversation_id: str | None) -> str:
        conversation = str(conversation_id or "").strip()
        if not conversation:
            return ""
        return f"{channel}:{conversation}"

    @staticmethod
    def _source_summary(response: ChatResponse) -> list[dict[str, Any]]:
        rows = []
        for item in response.sources[:5]:
            rows.append({
                "type": item.type,
                "source": item.source,
                "doc_name": item.doc_name,
                "section": item.section,
                "category": item.category,
            })
        return rows

    @staticmethod
    def _memory_summary(memory: dict[str, Any] | None) -> dict[str, Any]:
        memory = memory or {}
        return {
            "products": memory.get("products", []),
            "scenario": memory.get("scenario", ""),
            "budget": memory.get("budget", ""),
            "updated_at": memory.get("updated_at", ""),
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
