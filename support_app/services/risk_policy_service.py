from __future__ import annotations

from typing import Any


class RiskPolicyService:
    DEFAULT_POLICY = {
        "blocked_keywords": [
            "合同",
            "合同条款",
            "最终价",
            "最低价",
            "底价",
            "保证交付",
            "保证现货",
            "保证有货",
            "承诺",
            "违约",
            "赔偿",
        ],
        "high_keywords": [
            "库存",
            "现货",
            "交付",
            "发货",
            "月底能不能到",
            "优惠",
            "折扣",
            "付款",
            "定金",
            "发票",
            "税点",
            "交期",
            "排产",
        ],
        "medium_keywords": [
            "报价",
            "价格",
            "多少钱",
            "预算",
            "费用",
            "成本",
            "大概多少",
            "参考价",
        ],
        "safe_answers": {
            "blocked": "这个问题涉及合同、最终价格或交付承诺，需要销售同事为您确认。我可以先帮您整理需求，再由销售同事给您准确答复。",
            "high": "这个问题涉及库存、交付或商务条件，我可以先给你参考方向，但最终信息需要人工同事确认。",
            "medium": "我可以先给你参考配置方向和价格区间思路，最终价格和商务条款需要人工同事确认。",
            "low": "",
        },
        "allowed_scopes": {
            "blocked": "仅可引导转人工，不得给出合同、最终价格或确定性交付承诺。",
            "high": "可提供参考信息，但不得承诺库存、交付、优惠、付款和税务条款。",
            "medium": "只能给参考配置方向，不能承诺最终价格。",
            "low": "可按知识库正常回答。",
        },
    }
    LOW_RISK_HINTS = ("保修", "质保", "售后", "参数", "安装", "维修", "功能", "规格")

    def __init__(self, risk_policy: dict[str, Any] | None = None):
        self.policy = self._normalize_policy(risk_policy)

    def precheck(self, message: str, state: dict | None = None) -> dict:
        try:
            return self._assess(message, understand_plan=None, state=state, phase="precheck")
        except Exception:
            return self._fail_safe()

    def evaluate(
        self,
        message: str,
        understand_plan: dict | None = None,
        state: dict | None = None,
    ) -> dict:
        try:
            return self._assess(message, understand_plan=understand_plan, state=state, phase="evaluate")
        except Exception:
            return self._fail_safe()

    def _assess(
        self,
        message: str,
        understand_plan: dict | None = None,
        state: dict | None = None,
        phase: str = "evaluate",
    ) -> dict:
        text = str(message or "").strip()
        blocked_hits = self._match_keywords(text, self.policy["blocked_keywords"])
        high_hits = self._match_keywords(text, self.policy["high_keywords"])
        medium_hits = self._match_keywords(text, self.policy["medium_keywords"])

        risk_reasons: list[str] = []
        matched_keywords: list[str] = []

        if blocked_hits:
            risk_level = "blocked"
            route = "handoff"
            need_human = True
            risk_reasons.append("命中 blocked 商业风险词")
            matched_keywords.extend(blocked_hits)
        elif high_hits:
            risk_level = "high"
            route = "answer_with_review"
            need_human = True
            risk_reasons.append("命中 high 商业风险词")
            matched_keywords.extend(high_hits)
        elif medium_hits:
            risk_level = "medium"
            route = "answer_with_review"
            need_human = True
            risk_reasons.append("命中 medium 价格咨询词")
            matched_keywords.extend(medium_hits)
        else:
            inferred_level, inferred_reasons = self._infer_from_plan(understand_plan, state, text)
            risk_level = inferred_level
            route = "answer" if risk_level == "low" else "answer_with_review"
            need_human = risk_level != "low"
            risk_reasons.extend(inferred_reasons)

        if not risk_reasons and any(word in text for word in self.LOW_RISK_HINTS):
            risk_reasons.append("普通售后/参数类问题")
        if not risk_reasons and not text:
            risk_reasons.append("空消息，按低风险处理")
        if not risk_reasons:
            risk_reasons.append("未命中风险词，按低风险处理")

        if risk_level == "blocked":
            route = "handoff"
            need_human = True

        safe_answer = self.policy["safe_answers"].get(risk_level, "")
        allowed_scope = self.policy["allowed_scopes"].get(risk_level, self.DEFAULT_POLICY["allowed_scopes"]["low"])

        return {
            "risk_level": risk_level,
            "need_human": bool(need_human),
            "route": route,
            "safe_answer": safe_answer,
            "risk_reasons": list(dict.fromkeys(risk_reasons)),
            "allowed_answer_scope": allowed_scope,
            "matched_keywords": list(dict.fromkeys(matched_keywords)),
            "phase": phase,
        }

    def _infer_from_plan(self, understand_plan: dict | None, state: dict | None, text: str) -> tuple[str, list[str]]:
        plan = understand_plan if isinstance(understand_plan, dict) else {}
        reasons: list[str] = []
        level = "low"

        intent = str(plan.get("intent") or "")
        if intent in {"handoff", "contract_handoff"}:
            return "blocked", ["understand_plan 意图要求人工接管"]
        if intent in {"quote_price", "quote_recommendation", "quote_configuration_sheet", "quote_inquiry"}:
            level = "medium"
            reasons.append("understand_plan 表示价格/报价相关意图")

        risk_flags = plan.get("risk_flags")
        if isinstance(risk_flags, list) and risk_flags:
            level = "high" if level == "low" else level
            reasons.append("understand_plan 包含风险标记")

        state_obj = state if isinstance(state, dict) else {}
        if state_obj.get("human_handoff_required"):
            level = "high" if level in {"low", "medium"} else level
            reasons.append("会话状态显示需要人工确认")

        if level == "low" and any(word in text for word in self.LOW_RISK_HINTS):
            reasons.append("普通售后/参数类问题")

        return level, reasons

    @staticmethod
    def _match_keywords(message: str, keywords: list[str]) -> list[str]:
        text = str(message or "")
        return [word for word in keywords if word and word in text]

    def _normalize_policy(self, risk_policy: dict[str, Any] | None) -> dict[str, Any]:
        default = self.DEFAULT_POLICY
        if not isinstance(risk_policy, dict):
            return default

        candidate = risk_policy.get("risk_policy") if isinstance(risk_policy.get("risk_policy"), dict) else risk_policy
        if not isinstance(candidate, dict):
            return default

        normalized: dict[str, Any] = {
            "blocked_keywords": self._as_keywords(candidate.get("blocked_keywords"), default["blocked_keywords"]),
            "high_keywords": self._as_keywords(candidate.get("high_keywords"), default["high_keywords"]),
            "medium_keywords": self._as_keywords(candidate.get("medium_keywords"), default["medium_keywords"]),
            "safe_answers": self._merge_dict(default["safe_answers"], candidate.get("safe_answers")),
            "allowed_scopes": self._merge_dict(default["allowed_scopes"], candidate.get("allowed_scopes")),
        }
        return normalized

    @staticmethod
    def _as_keywords(raw: Any, fallback: list[str]) -> list[str]:
        if not isinstance(raw, list):
            return list(fallback)
        cleaned = [str(item).strip() for item in raw if str(item).strip()]
        return cleaned or list(fallback)

    @staticmethod
    def _merge_dict(base: dict[str, str], patch: Any) -> dict[str, str]:
        merged = dict(base)
        if not isinstance(patch, dict):
            return merged
        for key, value in patch.items():
            text = str(value or "").strip()
            if key in merged and text:
                merged[key] = text
        return merged

    def _fail_safe(self) -> dict:
        return {
            "risk_level": "high",
            "need_human": True,
            "route": "handoff",
            "safe_answer": self.DEFAULT_POLICY["safe_answers"]["high"],
            "risk_reasons": ["risk_policy_service_internal_error"],
            "allowed_answer_scope": self.DEFAULT_POLICY["allowed_scopes"]["high"],
            "matched_keywords": [],
            "phase": "fail_safe",
        }
