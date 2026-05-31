from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SalesStrategyPlan:
    sales_stage: str
    known_needs: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    soft_question: str = ""
    recommendation_goal: str = ""
    should_quote: bool = False
    should_direct_answer: bool = False
    route_reason: str = ""
    recommendation_basis: list[str] = field(default_factory=list)
    quote_readiness: dict[str, Any] = field(default_factory=dict)
    decision_trace: list[dict[str, Any]] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "sales_stage": self.sales_stage,
            "known_needs": self.known_needs,
            "missing_fields": self.missing_fields,
            "soft_question": self.soft_question,
            "recommendation_goal": self.recommendation_goal,
            "should_quote": bool(self.should_quote),
            "should_direct_answer": bool(self.should_direct_answer),
            "route_reason": self.route_reason,
            "recommendation_basis": self.recommendation_basis,
            "quote_readiness": self.quote_readiness,
            "decision_trace": self.decision_trace,
        }


class SalesStrategyService:
    DEFAULT_POLICY = {
        "direct_answer_intents": ["knowledge_lookup", "identity", "correction_learning"],
        "commercial_risk_words": ["合同", "签约", "交付时间", "交期", "保证", "承诺", "最低价", "库存", "优惠", "折扣", "直接确认"],
        "contextual_followup_words": ["这个", "这款", "那款", "那个", "这套", "它", "多少钱", "价格", "适合吗", "多大直播间", "要不要轨道", "还有轨道"],
        "quote_ready_threshold": 3,
        "required_fields_by_scenario": {
            "group_live": ["scenario", "live_room_area", "camera_count", "track_preference", "budget"],
            "film_pro": ["scenario", "camera_payload", "track_preference", "budget"],
            "broadcast": ["scenario", "camera_count", "freed_required", "budget"],
            "default": ["scenario", "budget", "track_preference"],
        },
        "soft_question_by_field": {
            "live_room_area": "我再顺手确认一下直播间大概面积和主播走位范围。",
            "camera_count": "我再确认一下现场大概是几台相机或几个机位。",
            "track_preference": "我再确认一下是否需要横移、环绕或轨道走位。",
            "budget": "预算区间也可以后面补一下，它会影响臂形档位和选配范围。",
            "camera_payload": "相机、镜头和附件重量也需要再确认一下。",
            "freed_required": "如果涉及虚拟制作或 XR，还需要确认是否要 FreeD/跟踪协议。",
            "delivery_urgency": "交付时间需要人工同事结合排期再确认。",
        },
    }

    DIRECT_KNOWLEDGE_WORDS = ("保修", "质保", "售后", "安装", "参数", "规格", "怎么操作", "支持", "多久")
    PRICE_WORDS = ("多少钱", "价格", "报价", "费用", "预算", "总价", "合计")
    RECOMMEND_WORDS = ("推荐", "选型", "怎么选", "用哪款", "哪款", "什么产品", "产品推荐")
    PRODUCT_WORDS = ("U-MOCO", "UMOCO", "GRA", "MINI", "AIR", "EXT", "PRO")

    def __init__(self, policy: dict[str, Any] | None = None):
        self.policy = self._merge_policy(self.DEFAULT_POLICY, policy or {})

    def plan(
        self,
        query: str,
        intent_plan: dict[str, Any] | None = None,
        context_plan: dict[str, Any] | None = None,
        memory: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> SalesStrategyPlan:
        text = str(query or "").strip()
        intent_plan = intent_plan or {}
        context_plan = context_plan or {}
        history = history or []
        known = self._known_needs(text, intent_plan, context_plan, memory, history)
        trace: list[dict[str, Any]] = [{"step": "extract_known_needs", "known": dict(known)}]

        if self._is_handoff(text, intent_plan):
            return self._result(
                "handoff",
                known,
                [],
                "",
                "",
                False,
                False,
                "涉及合同、库存、优惠、交付或其他商业承诺，需要人工确认",
                [],
                trace,
                readiness="human_required",
            )

        if self._is_direct_answer(text, intent_plan):
            return self._result(
                "direct_answer",
                known,
                [],
                "",
                "基于 FAQ/DOC 直接回答客户的明确问题",
                False,
                True,
                "明确售后、保修、安装、参数或知识查询问题，优先知识库直答",
                self._basis(known),
                trace,
                readiness="not_applicable",
            )

        missing = self._missing_fields(known)
        readiness = self._quote_readiness(known, missing)
        intent = str(intent_plan.get("intent", "") or "")
        is_price = intent == "quote_price" or any(word in text for word in self.PRICE_WORDS)
        is_recommend = intent == "quote_recommendation" or any(word in text for word in self.RECOMMEND_WORDS)
        contextual = bool(intent_plan.get("contextual_followup") or context_plan.get("contextual_query"))
        trace.append({
            "step": "stage_decision",
            "intent": intent,
            "is_price": is_price,
            "is_recommend": is_recommend,
            "contextual": contextual,
            "quote_ready": readiness["ready"],
        })

        if is_price and readiness["ready"]:
            return self._result(
                "quote_ready",
                known,
                missing,
                "",
                "按已知配置生成参考报价草案",
                True,
                False,
                "客户问价格且关键配置基本齐备，可以进入报价草案但仍需人工复核",
                self._basis(known),
                trace,
                quote_readiness=readiness,
            )
        if is_price:
            return self._result(
                "recommend",
                known,
                missing,
                self._soft_question(missing),
                "先给参考配置方向，再确认缺失条件后核价",
                False,
                False,
                "客户问价格但关键信息不足，先不承诺最终价格",
                self._basis(known),
                trace,
                quote_readiness=readiness,
            )
        if is_recommend or contextual:
            stage = "recommend" if known else "discovery"
            return self._result(
                stage,
                known,
                missing,
                self._soft_question(missing),
                "基于当前场景给初步选型方向",
                False,
                False,
                "销售咨询类问题，先给初步推荐并自然确认关键条件",
                self._basis(known),
                trace,
                quote_readiness=readiness,
            )
        return self._result(
            "discovery",
            known,
            missing,
            self._soft_question(missing),
            "先理解客户需求并补齐关键场景",
            False,
            False,
            "未形成明确知识查询或报价条件，进入轻量需求理解",
            self._basis(known),
            trace,
            quote_readiness=readiness,
        )

    def _result(
        self,
        sales_stage: str,
        known: dict[str, Any],
        missing: list[str],
        soft_question: str,
        goal: str,
        should_quote: bool,
        direct: bool,
        reason: str,
        basis: list[str],
        trace: list[dict[str, Any]],
        readiness: str = "",
        quote_readiness: dict[str, Any] | None = None,
    ) -> SalesStrategyPlan:
        quote_readiness = quote_readiness or {
            "ready": False,
            "status": readiness or "not_ready",
            "score": 0,
            "threshold": int(self.policy.get("quote_ready_threshold") or 3),
            "missing_fields": missing,
        }
        return SalesStrategyPlan(
            sales_stage=sales_stage,
            known_needs=known,
            missing_fields=missing,
            soft_question=soft_question,
            recommendation_goal=goal,
            should_quote=should_quote,
            should_direct_answer=direct,
            route_reason=reason,
            recommendation_basis=basis,
            quote_readiness=quote_readiness,
            decision_trace=trace,
        )

    def _known_needs(
        self,
        text: str,
        intent_plan: dict[str, Any],
        context_plan: dict[str, Any],
        memory: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        memory = memory or {}
        known: dict[str, Any] = {}
        scenario = self._scenario(text) or self._scenario(str(memory.get("scenario", "")))
        if not scenario and self._history_has(history, ("团播", "直播间", "直播")):
            scenario = "group_live"
        if not scenario and self._history_has(history, ("电视台", "晚会", "广播")):
            scenario = "broadcast"
        if not scenario and self._history_has(history, ("影视", "TVC", "广告")):
            scenario = "film_pro"
        if scenario:
            known["scenario"] = scenario
        for key, value in {
            "budget": self._budget(text) or memory.get("budget", ""),
            "live_room_area": self._live_room_area(text) or memory.get("live_room_area", ""),
            "camera_count": self._camera_count(text) or memory.get("camera_count", ""),
            "robot_arm_count": self._robot_arm_count(text) or memory.get("robot_arm_count", ""),
            "camera_payload": self._camera_payload(text),
            "track_preference": self._track_preference(text) or memory.get("track_preference", ""),
            "delivery_urgency": self._delivery_urgency(text) or memory.get("project_time", ""),
        }.items():
            if value:
                known[key] = str(value)
        if any(word in text.lower() for word in ("freed", "free-d", "xr", "虚拟", "跟踪")):
            known["freed_required"] = True
        anchors = []
        anchors.extend(str(item) for item in intent_plan.get("product_anchors", []) if str(item))
        anchors.extend(str(item) for item in context_plan.get("anchors", []) if str(item))
        anchors.extend(str(item) for item in memory.get("products", []) if str(item))
        explicit = [token for token in self.PRODUCT_WORDS if token.upper() in text.upper()]
        anchors.extend(explicit)
        if anchors:
            known["product_anchors"] = list(dict.fromkeys(anchors))[:8]
        risks = [word for word in self.policy.get("commercial_risk_words", []) if word in text]
        if risks:
            known["risk_flags"] = list(dict.fromkeys(risks))
        return known

    def _missing_fields(self, known: dict[str, Any]) -> list[str]:
        scenario = str(known.get("scenario") or "default")
        fields_by_scenario = self.policy.get("required_fields_by_scenario", {})
        required = fields_by_scenario.get(scenario) or fields_by_scenario.get("default") or []
        missing = [field for field in required if not known.get(field)]
        if known.get("track_preference") == "需要进一步确认轨道" and not known.get("live_room_area"):
            missing.append("live_room_area")
        return list(dict.fromkeys(missing))

    def _quote_readiness(self, known: dict[str, Any], missing: list[str]) -> dict[str, Any]:
        required_count = len(set(missing) | set(known.keys()))
        score = max(0, required_count - len(missing))
        threshold = int(self.policy.get("quote_ready_threshold") or 3)
        ready = score >= threshold and not any(field in missing for field in ("scenario", "budget"))
        return {
            "ready": ready,
            "status": "ready" if ready else "not_ready",
            "score": score,
            "threshold": threshold,
            "missing_fields": missing,
        }

    def _is_handoff(self, text: str, intent_plan: dict[str, Any]) -> bool:
        if str(intent_plan.get("intent", "")) == "handoff":
            return True
        return any(word in text for word in self.policy.get("commercial_risk_words", []))

    def _is_direct_answer(self, text: str, intent_plan: dict[str, Any]) -> bool:
        intent = str(intent_plan.get("intent", "") or "")
        if intent in set(self.policy.get("direct_answer_intents", [])):
            return True
        if any(word in text for word in self.DIRECT_KNOWLEDGE_WORDS) and not any(word in text for word in self.PRICE_WORDS):
            return True
        return False

    def _soft_question(self, missing: list[str]) -> str:
        prompts = self.policy.get("soft_question_by_field", {})
        for field in missing:
            question = str(prompts.get(field, "") or "").strip()
            if question:
                return question
        return ""

    @staticmethod
    def _basis(known: dict[str, Any]) -> list[str]:
        labels = {
            "scenario": "使用场景",
            "live_room_area": "直播间面积",
            "camera_count": "相机/机位数量",
            "robot_arm_count": "机械臂数量",
            "track_preference": "轨道需求",
            "budget": "预算",
            "product_anchors": "产品锚点",
        }
        return [labels.get(key, key) for key, value in known.items() if value and key in labels]

    @staticmethod
    def _scenario(text: str) -> str:
        if any(word in text for word in ("团播", "直播间", "直播", "电商", "带货", "主播")):
            return "group_live"
        if any(word in text for word in ("电视台", "晚会", "广播", "广电", "演播室")):
            return "broadcast"
        if any(word in text for word in ("影视", "TVC", "tvc", "广告", "拍摄", "工作室")):
            return "film_pro"
        return ""

    @staticmethod
    def _history_has(history: list[dict[str, Any]], words: tuple[str, ...]) -> bool:
        text = "\n".join(f"{item.get('message', '')}\n{item.get('answer', '')}" for item in history[-4:])
        return any(word in text for word in words)

    @staticmethod
    def _budget(text: str) -> str:
        match = re.search(r"预算\s*([¥￥]?\s*\d+(?:\.\d+)?\s*[万千]?)", text)
        if match:
            return match.group(1).replace(" ", "")
        match = re.search(r"([¥￥]?\s*\d+(?:\.\d+)?\s*万)\s*(?:左右|以内|预算)?", text)
        return match.group(1).replace(" ", "") if match else ""

    @staticmethod
    def _live_room_area(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:平|平方|平方米|㎡)", text)
        return match.group(1) if match else ""

    @classmethod
    def _camera_count(cls, text: str) -> str:
        match = re.search(r"([一二两三四五六七八九十\d]+)\s*(?:个|台|路)?\s*(?:相机|机位|摄像机)", text)
        return cls._chinese_number(match.group(1)) if match else ""

    @classmethod
    def _robot_arm_count(cls, text: str) -> str:
        match = re.search(r"机械臂.{0,6}(?:用|要|配|上)?\s*([一二两三四五六七八九十\d]+)\s*台", text)
        if not match:
            match = re.search(r"([一二两三四五六七八九十\d]+)\s*台\s*机械臂", text)
        return cls._chinese_number(match.group(1)) if match else ""

    @staticmethod
    def _camera_payload(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤)\s*(?:相机|镜头|负载|载重)?", text)
        return match.group(1) if match else ""

    @staticmethod
    def _track_preference(text: str) -> str:
        if any(word in text for word in ("固定机位", "不上轨道", "不需要轨道", "不用轨道", "先不上轨道")):
            return "暂不需要轨道"
        if any(word in text for word in ("轨道", "横移", "环绕", "走位", "全景")):
            return "需要进一步确认轨道"
        return ""

    @staticmethod
    def _delivery_urgency(text: str) -> str:
        match = re.search(r"(本周|下周|这个月|下个月|马上|尽快|\d+月|\d+天内|\d+号)", text)
        return match.group(1) if match else ""

    @staticmethod
    def _chinese_number(value: str) -> str:
        text = str(value or "").strip()
        if text.isdigit():
            return text
        mapping = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if text == "十":
            return "10"
        if "十" in text:
            left, _, right = text.partition("十")
            tens = mapping.get(left, 1) if left else 1
            ones = mapping.get(right, 0) if right else 0
            return str(tens * 10 + ones)
        return str(mapping.get(text, "")) if text in mapping else ""

    @classmethod
    def _merge_policy(cls, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._merge_policy(merged[key], value)
            elif value not in (None, "", []):
                merged[key] = value
        return merged
