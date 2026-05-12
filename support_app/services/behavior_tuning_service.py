from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.schemas import ChatRequest
from support_app.services.behavior_config_service import BehaviorConfigService
from support_app.services.ollama_client import OllamaClient


class BehaviorTuningService:
    def __init__(
        self,
        ollama: OllamaClient,
        behavior_config: BehaviorConfigService,
        regression_store: JsonFileRepository,
        draft_store: JsonFileRepository,
    ):
        self.ollama = ollama
        self.behavior_config = behavior_config
        self.regression_store = regression_store
        self.draft_store = draft_store

    def draft(self, instruction: str) -> dict[str, Any]:
        instruction = str(instruction or "").strip()
        if not instruction:
            raise ValueError("instruction 不能为空")
        draft = self._draft_with_ollama(instruction) or self._heuristic_draft(instruction, "heuristic")
        drafts = self.draft_store.load_list()
        drafts = [item for item in drafts if item.get("id") != draft["id"]]
        drafts.insert(0, draft)
        self.draft_store.save_list(drafts[:100])
        return {"ok": True, "draft": draft}

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._resolve_draft(payload)
        if not draft:
            raise KeyError("未找到可应用的草稿")
        applied_config = self.behavior_config.apply_patch(
            draft.get("behavior_rules_patch") or {},
            draft.get("answer_style_patch") or {},
        )
        cases = self._append_regression_cases(draft.get("regression_cases") or [])
        self._mark_applied(draft["id"])
        return {
            "ok": True,
            "draft_id": draft["id"],
            "behavior_rules": applied_config["behavior_rules"],
            "answer_styles": applied_config["answer_styles"],
            "regression_cases": cases,
        }

    def list_regression_cases(self) -> dict[str, Any]:
        items = self.regression_store.load_list()
        return {"total": len(items), "items": items}

    def save_regression_cases(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("items 必须是数组")
        normalized = [self._normalize_case(item) for item in items if isinstance(item, dict)]
        self.regression_store.save_list(normalized)
        return {"ok": True, "total": len(normalized), "items": normalized}

    def run_regression_cases(self, chat_service, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        cases = payload.get("cases")
        if not isinstance(cases, list):
            cases = self.regression_store.load_list()
        enabled_cases = [self._normalize_case(item) for item in cases if item.get("enabled", True)]
        results = []
        for item in enabled_cases:
            metadata = dict(item.get("metadata") or {})
            metadata["regression_test"] = True
            if item.get("test_memory"):
                metadata["test_memory"] = item["test_memory"]
            response = chat_service.answer(ChatRequest(
                message=item.get("message", ""),
                channel=item.get("channel", "api"),
                user_id=None,
                conversation_id=f"regression_{item.get('id', '')}",
                metadata=metadata,
            ))
            answer = response.answer or ""
            failures = []
            expected_route = item.get("expected_route", "")
            if expected_route and response.route != expected_route:
                failures.append(f"route 应为 {expected_route}，实际为 {response.route}")
            for keyword in item.get("expected_keywords", []):
                if str(keyword) and str(keyword) not in answer:
                    failures.append(f"缺少关键词：{keyword}")
            for keyword in item.get("forbidden_keywords", []):
                if str(keyword) and str(keyword) in answer:
                    failures.append(f"出现禁止关键词：{keyword}")
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "passed": not failures,
                "failures": failures,
                "route": response.route,
                "answer": answer,
                "metadata": response.metadata,
            })
        return {
            "ok": True,
            "total": len(results),
            "passed": len([item for item in results if item["passed"]]),
            "failed": len([item for item in results if not item["passed"]]),
            "results": results,
        }

    def _draft_with_ollama(self, instruction: str) -> dict[str, Any] | None:
        prompt = f"""
你是本地客服系统的配置助手。请把用户优化指令转成 JSON 草稿，不要输出解释。
JSON 字段固定为 behavior_rules_patch、answer_style_patch、regression_cases、notes。
用户优化指令：{instruction}
"""
        try:
            raw = self.ollama.generate(prompt)
            data = self._extract_json(raw)
            if not isinstance(data, dict):
                return None
        except Exception:
            return None
        draft = self._heuristic_draft(instruction, "ollama")
        draft["notes"].append("Ollama 已参与生成；第一版仍用安全模板补齐结构。")
        for key in ("behavior_rules_patch", "answer_style_patch"):
            if isinstance(data.get(key), dict):
                draft[key] = BehaviorConfigService._deep_merge(draft[key], data[key])
        if isinstance(data.get("regression_cases"), list) and data["regression_cases"]:
            draft["regression_cases"] = [self._normalize_case(item) for item in data["regression_cases"] if isinstance(item, dict)]
        if isinstance(data.get("notes"), list):
            draft["notes"].extend(str(item) for item in data["notes"])
        return draft

    def _heuristic_draft(self, instruction: str, generator: str) -> dict[str, Any]:
        lower = instruction.lower()
        behavior_patch: dict[str, Any] = {"intent_rules": []}
        style_patch: dict[str, Any] = {}
        cases = []
        notes = []
        if any(word in instruction for word in ("上次", "之前", "记忆", "客户记忆")):
            behavior_patch["memory_policy"] = {
                "previous_context_words": ["上次", "之前", "刚才", "前面", "上一轮", "那个", "这款"],
                "product_recall_words": ["什么机械臂", "哪个机械臂", "聊的什么", "是什么产品", "什么产品"],
                "previous_product_anchor": True,
            }
            cases.append({
                "id": "case_previous_product_anchor_mini",
                "name": "上次聊的机械臂价格优先客户记忆",
                "message": "上次聊的机械臂多少钱",
                "test_memory": {"products": ["MINI"]},
                "expected_route": "quote_draft",
                "expected_keywords": ["MINI"],
                "forbidden_keywords": ["GRA 旗舰"],
                "enabled": True,
            })
            notes.append("已生成客户记忆优先规则。")
        if any(word in instruction for word in ("保修", "资料不足", "缺少文档", "主动")):
            behavior_patch["fallback_policy"] = {"active_gap_prompt_on_test_page": True}
            cases.append({
                "id": "case_mini_warranty_gap",
                "name": "mini 保修资料不足时主动要文档",
                "message": "mini 保修多久",
                "metadata": {"test_page": True},
                "expected_route": "fallback",
                "expected_keywords": ["MINI 保修", "质保政策文档"],
                "forbidden_keywords": [],
                "enabled": True,
            })
            notes.append("已生成资料不足主动追问规则。")
        if any(word in instruction for word in ("纠错", "你说错", "学习")):
            cases.append({
                "id": "case_correction_learning",
                "name": "测试页纠错写入学习库",
                "message": "你说错了，mini 标准版不包含 FreeD，FreeD 是选配",
                "metadata": {"test_page": True},
                "expected_route": "learned_correction",
                "expected_keywords": ["记下"],
                "forbidden_keywords": [],
                "enabled": True,
            })
            notes.append("已生成纠错学习测试用例。")
        if "报价" in instruction or "价格" in instruction or "quote" in lower:
            style_patch["quote_disclaimer"] = "优惠价、交付时间、合同条款和特殊定制需要人工同事复核后才能作为正式报价。"
        if not cases:
            behavior_patch["intent_rules"].append({
                "name": instruction[:24],
                "description": instruction,
                "enabled": True,
            })
            notes.append("未识别到专用模板，已保存为通用意图规则草稿。")
        return {
            "id": f"draft_{uuid.uuid4().hex[:12]}",
            "status": "pending",
            "instruction": instruction,
            "behavior_rules_patch": behavior_patch,
            "answer_style_patch": style_patch,
            "regression_cases": cases,
            "notes": notes,
            "generator": generator,
            "created_at": self._now(),
            "updated_at": self._now(),
        }

    def _resolve_draft(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(payload.get("draft"), dict):
            return payload["draft"]
        draft_id = str(payload.get("draft_id", "") or "").strip()
        for item in self.draft_store.load_list():
            if item.get("id") == draft_id:
                return item
        return None

    def _mark_applied(self, draft_id: str) -> None:
        drafts = self.draft_store.load_list()
        for item in drafts:
            if item.get("id") == draft_id:
                item["status"] = "applied"
                item["updated_at"] = self._now()
        self.draft_store.save_list(drafts)

    def _append_regression_cases(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = self.regression_store.load_list()
        by_id = {item.get("id"): item for item in current if item.get("id")}
        for item in cases:
            normalized = self._normalize_case(item)
            by_id[normalized["id"]] = normalized
        items = list(by_id.values())
        self.regression_store.save_list(items)
        return items

    @staticmethod
    def _normalize_case(item: dict[str, Any]) -> dict[str, Any]:
        case_id = str(item.get("id", "") or "").strip() or f"case_{uuid.uuid4().hex[:10]}"
        return {
            "id": case_id,
            "name": str(item.get("name", "") or case_id).strip(),
            "message": str(item.get("message", "") or "").strip(),
            "channel": str(item.get("channel", "") or "api").strip(),
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "test_memory": item.get("test_memory") if isinstance(item.get("test_memory"), dict) else {},
            "expected_route": str(item.get("expected_route", "") or "").strip(),
            "expected_keywords": [str(x) for x in item.get("expected_keywords", []) if str(x)],
            "forbidden_keywords": [str(x) for x in item.get("forbidden_keywords", []) if str(x)],
            "enabled": bool(item.get("enabled", True)),
        }

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            raw = match.group(0)
        try:
            data = json.loads(raw)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
