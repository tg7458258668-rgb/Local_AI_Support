from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentResult:
    intent: str
    confidence: float
    route_policy: str
    scenario_terms: list[str] = field(default_factory=list)
    action_terms: list[str] = field(default_factory=list)
    product_anchors: list[str] = field(default_factory=list)
    needs_retrieval: bool = False
    needs_quote_tool: bool = False
    reason: str = ""
    source: str = "rules"
    risk_flags: list[str] = field(default_factory=list)
    contextual_followup: bool = False
    inherited_from_history: bool = False
    inherited_route: str = ""
    resolved_query: str = ""
    history_anchor_summary: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(float(self.confidence or 0), 3),
            "route_policy": self.route_policy,
            "scenario_terms": self.scenario_terms,
            "action_terms": self.action_terms,
            "product_anchors": self.product_anchors,
            "needs_retrieval": bool(self.needs_retrieval),
            "needs_quote_tool": bool(self.needs_quote_tool),
            "reason": self.reason,
            "source": self.source,
            "risk_flags": self.risk_flags,
            "contextual_followup": bool(self.contextual_followup),
            "inherited_from_history": bool(self.inherited_from_history),
            "inherited_route": self.inherited_route,
            "resolved_query": self.resolved_query,
            "history_anchor_summary": self.history_anchor_summary,
        }


class IntentService:
    """Centralized intent router for chat.

    The deterministic layer owns high-risk decisions. The optional local model
    only helps with low-confidence business intent classification.
    """

    INTENTS = {
        "identity",
        "memory_followup",
        "quote_price",
        "quote_recommendation",
        "quote_configuration_sheet",
        "knowledge_lookup",
        "handoff",
        "correction_learning",
        "clarify",
        "fallback",
    }

    SCENARIO_TERMS = (
        "团播",
        "直播间",
        "直播",
        "电商",
        "带货",
        "主播",
        "机械臂",
        "产品",
        "配置",
        "轨道",
        "电视台",
        "晚会",
        "影视",
        "广告",
        "TVC",
        "虚拟拍摄",
    )
    PRODUCT_TERMS = ("U-MOCO", "UMOCO", "GRA", "MINI", "AIR", "EXT", "PRO", "FreeD", "FREE-D", "XR")
    IDENTITY_TERMS = (
        "你是谁",
        "你叫什么",
        "你是干嘛",
        "你能做什么",
        "你有什么用",
        "你是客服",
        "你是机器人",
        "你好",
        "您好",
        "在吗",
        "hi",
        "hello",
    )
    CORRECTION_TERMS = ("你说错", "说错了", "不是", "纠正", "记住", "记一下", "正确说法", "应该是")
    HANDOFF_TERMS = (
        "合同",
        "签约",
        "交付时间",
        "交期",
        "保证",
        "承诺",
        "最低价",
        "一定",
        "肯定",
        "三天",
        "免费",
        "库存",
        "直接签",
    )
    CONTEXT_TERMS = ("这款", "那个", "刚才", "刚刚", "上次", "之前", "前面", "上一轮", "继续", "它", "这个方案", "这套")
    SHORT_FOLLOWUP_TERMS = (
        "怎么样",
        "咋样",
        "如何",
        "呢",
        "吗",
        "可以吗",
        "行吗",
        "适合吗",
        "版本",
        "版",
        "换成",
        "那",
        "还有",
        "区别",
        "差别",
        "对比",
        "加",
        "不加",
        "换",
    )
    VERSION_SWITCH_TERMS = ("影视", "团播", "直播", "广播", "电视台", "TVC", "广告", "版本", "版", "换成")
    PRICE_TERMS = ("多少钱", "价格", "报价", "费用", "预算", "优惠", "便宜", "采购", "总价", "合计", "多少")
    RECOMMEND_TERMS = ("推荐", "选型", "怎么选", "用哪款", "哪款", "哪个型号", "什么产品", "产品推荐")
    SHEET_TERMS = ("配置单", "配置清单", "方案单", "报价单", "清单")
    WRITE_SEND_TERMS = ("写一份", "出一份", "做一份", "生成", "整理", "寄出", "发客户", "发给客户", "给客户")
    KNOWLEDGE_PHRASES = (
        "有什么配置",
        "配置是什么",
        "包含什么",
        "包括什么",
        "标配",
        "选配",
        "参数",
        "规格",
        "功能",
        "保修",
        "质保",
        "售后",
        "多久",
        "怎么用",
        "怎么操作",
        "支持",
        "FreeD 是标配",
        "freed 是标配",
    )

    def __init__(self, ollama: Any | None = None, timeout_seconds: float = 1.2, deterministic_threshold: float = 0.70):
        self.ollama = ollama
        self.timeout_seconds = timeout_seconds
        self.deterministic_threshold = deterministic_threshold
        self.intent_model = os.getenv("INTENT_MODEL", "").strip()

    def classify(self, query: str, context: dict[str, Any] | None = None) -> IntentResult:
        context = context or {}
        deterministic = self.classify_rules(query, context)
        if deterministic.confidence >= self.deterministic_threshold:
            return deterministic
        if deterministic.risk_flags:
            return deterministic
        model_result = self._classify_with_local_model(query, context, deterministic)
        return model_result or deterministic

    def classify_rules(self, query: str, context: dict[str, Any] | None = None) -> IntentResult:
        context = context or {}
        text = str(query or "").strip()
        compact = "".join(text.lower().split()).rstrip("？?！!。.")
        scenario_terms = self._matched_terms(text, self.SCENARIO_TERMS)
        product_anchors = self._product_anchors(text)
        context_terms = self._matched_terms(text, self.CONTEXT_TERMS)
        short_followup_terms = self._matched_terms(text, self.SHORT_FOLLOWUP_TERMS)
        price_terms = self._matched_terms(text, self.PRICE_TERMS)
        recommend_terms = self._matched_terms(text, self.RECOMMEND_TERMS)
        sheet_terms = self._matched_terms(text, self.SHEET_TERMS)
        write_terms = self._matched_terms(text, self.WRITE_SEND_TERMS)
        knowledge_terms = self._matched_terms(text, self.KNOWLEDGE_PHRASES)
        handoff_terms = self._matched_terms(text, self.HANDOFF_TERMS)
        correction_terms = self._matched_terms(text, self.CORRECTION_TERMS)
        history = context.get("history") if isinstance(context.get("history"), list) else []
        last_route = str(context.get("last_route", "") or "")
        last_message = str(context.get("last_message", "") or "")
        last_answer = str(context.get("last_answer", "") or "")
        history_anchor_summary = str(context.get("history_anchor_summary", "") or "").strip()
        history_product_anchors = self._clean_list(context.get("history_product_anchors"))
        has_history = bool(history or last_message or last_answer)

        if not text:
            return self._result("fallback", 0.4, "fallback", scenario_terms, [], product_anchors, False, False, "空问题，进入兜底")

        identity_like = compact in {"hi", "hello", "你好", "您好", "在吗", "在不在"} or (
            any(term in text for term in self.IDENTITY_TERMS if term not in {"你好", "您好", "在吗", "hi", "hello"})
            and len(text) <= 24
        )
        if identity_like and not (price_terms or recommend_terms or sheet_terms or knowledge_terms):
            return self._result("identity", 0.95, "identity", scenario_terms, ["identity"], product_anchors, False, False, "身份或寒暄问题")

        if correction_terms:
            return self._result("correction_learning", 0.92, "learned_correction", scenario_terms, correction_terms, product_anchors, False, False, "用户在纠错或要求记住新口径")

        if handoff_terms:
            return self._result(
                "handoff",
                0.94,
                "handoff",
                scenario_terms,
                handoff_terms,
                product_anchors,
                False,
                False,
                "涉及价格、交付、合同、库存或服务承诺风险",
                risk_flags=["commercial_commitment"],
            )

        if (
            not (price_terms or recommend_terms or sheet_terms or knowledge_terms)
            and self._is_short_followup(text, short_followup_terms, scenario_terms, product_anchors)
        ):
            if has_history:
                last_price_context = self._has_price_context(last_message, last_answer)
                version_switch = any(term in text for term in self.VERSION_SWITCH_TERMS)
                product_suitability = bool(product_anchors) and any(term in text for term in ("怎么样", "咋样", "如何", "可以", "行", "适合"))
                quote_like = (
                    bool(price_terms)
                    or (last_route == "quote_draft" and (product_suitability or (last_price_context and version_switch)))
                )
                inherited_route = "quote_draft" if quote_like else (last_route or "contextual")
                action_terms = [*short_followup_terms, *price_terms]
                resolved_query = self._resolved_followup_query(
                    text,
                    last_message,
                    last_answer,
                    [*product_anchors, *history_product_anchors],
                    scenario_terms,
                    inherited_route,
                    quote_like,
                )
                return self._result(
                    "memory_followup",
                    0.9,
                    "quote_draft" if quote_like else "contextual",
                    scenario_terms,
                    action_terms,
                    product_anchors or history_product_anchors,
                    not quote_like,
                    quote_like,
                    "短追问已结合最近对话补全，不再直接澄清",
                    contextual_followup=True,
                    inherited_from_history=True,
                    inherited_route=inherited_route,
                    resolved_query=resolved_query,
                    history_anchor_summary=history_anchor_summary or self._compact_history_summary(last_message, last_answer),
                )
            return self._result(
                "clarify",
                0.58,
                "fallback",
                scenario_terms,
                short_followup_terms,
                product_anchors,
                False,
                False,
                "短追问缺少最近上下文，需要先确认用户想了解适用场景、配置还是价格",
            )

        if context_terms and not product_anchors and (price_terms or recommend_terms or sheet_terms or knowledge_terms):
            intent = "memory_followup"
            quote_like = bool(price_terms or recommend_terms or sheet_terms)
            return self._result(
                intent,
                0.9,
                "quote_draft" if quote_like else "knowledge",
                scenario_terms,
                [*context_terms, *price_terms, *recommend_terms, *sheet_terms, *knowledge_terms],
                product_anchors,
                not quote_like,
                quote_like,
                "问题依赖上一轮上下文，需要先用历史或客户记忆补齐锚点",
                contextual_followup=True,
                inherited_from_history=has_history,
                inherited_route=last_route,
                resolved_query=self._resolved_followup_query(text, last_message, last_answer, history_product_anchors, scenario_terms, last_route, quote_like),
                history_anchor_summary=history_anchor_summary,
            )

        if sheet_terms and (write_terms or scenario_terms or product_anchors):
            return self._result(
                "quote_configuration_sheet",
                0.96,
                "quote_draft",
                scenario_terms,
                [*sheet_terms, *write_terms],
                product_anchors,
                False,
                True,
                "用户要求生成可发客户/可寄出的配置单或方案清单",
            )

        if price_terms:
            return self._result(
                "quote_price",
                0.92,
                "quote_draft",
                scenario_terms,
                price_terms,
                product_anchors,
                False,
                True,
                "出现明确价格、报价、预算或费用动作词",
            )

        if recommend_terms:
            return self._result(
                "quote_recommendation",
                0.88,
                "quote_draft",
                scenario_terms,
                recommend_terms,
                product_anchors,
                False,
                True,
                "出现明确推荐、选型或产品建议动作词",
            )

        if knowledge_terms:
            return self._result(
                "knowledge_lookup",
                0.86,
                "knowledge",
                scenario_terms,
                knowledge_terms,
                product_anchors,
                True,
                False,
                "用户在查配置、参数、标配、保修或售后资料",
            )

        if scenario_terms or product_anchors:
            return self._result(
                "clarify",
                0.58,
                "fallback",
                scenario_terms,
                [],
                product_anchors,
                False,
                False,
                "只识别到场景或实体词，缺少报价/推荐/配置单/知识查询动作",
            )

        return self._result("fallback", 0.48, "fallback", scenario_terms, [], product_anchors, True, False, "规则未能明确识别，交给本地模型辅助或兜底检索")

    def _classify_with_local_model(self, query: str, context: dict[str, Any], fallback: IntentResult) -> IntentResult | None:
        if not self.ollama:
            return None
        prompt = self._intent_prompt(query, fallback, context)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self.ollama.generate, prompt, self.intent_model or None)
            raw = future.result(timeout=self.timeout_seconds)
        except TimeoutError:
            executor.shutdown(wait=False, cancel_futures=True)
            return None
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            return None
        executor.shutdown(wait=False, cancel_futures=True)
        data = self._extract_json(raw)
        if not isinstance(data, dict):
            return None
        intent = str(data.get("intent", "") or "").strip()
        if intent not in self.INTENTS:
            return None
        confidence = self._bounded_float(data.get("confidence"), 0.55)
        scenario_terms = self._clean_list(data.get("scenario_terms")) or fallback.scenario_terms
        action_terms = self._clean_list(data.get("action_terms")) or fallback.action_terms
        product_anchors = self._clean_list(data.get("product_anchors")) or fallback.product_anchors
        route_policy = self._route_policy_for_intent(intent)
        needs_quote_tool = intent in {"quote_price", "quote_recommendation", "quote_configuration_sheet"} or (
            intent == "memory_followup" and any(term in action_terms for term in [*self.PRICE_TERMS, *self.RECOMMEND_TERMS, *self.SHEET_TERMS])
        )
        needs_retrieval = intent == "knowledge_lookup" or (intent == "fallback" and not needs_quote_tool)
        return IntentResult(
            intent=intent,
            confidence=max(0.0, min(confidence, 0.89)),
            route_policy=route_policy,
            scenario_terms=scenario_terms,
            action_terms=action_terms,
            product_anchors=product_anchors,
            needs_retrieval=needs_retrieval,
            needs_quote_tool=needs_quote_tool,
            reason=str(data.get("reason") or "本地模型辅助识别").strip()[:200],
            source="local_model",
            risk_flags=[],
        )

    def _intent_prompt(self, query: str, fallback: IntentResult, context: dict[str, Any]) -> str:
        return f"""
你是客服系统的轻量意图分类器。只输出 JSON，不要解释。
允许 intent：identity, memory_followup, quote_price, quote_recommendation, quote_configuration_sheet, knowledge_lookup, handoff, correction_learning, clarify, fallback。
判断原则：
- “团播、直播间、机械臂、产品、配置、轨道”只是场景/实体词，单独出现不能触发报价。
- 有“多少钱、价格、报价、预算、费用”等动作才是 quote_price。
- 有“推荐、选型、用哪款”等动作才是 quote_recommendation。
- 有“配置单、方案单、报价单、清单”且带“写/出/生成/整理/发客户/寄出”等动作才是 quote_configuration_sheet。
- “有什么配置、标配、参数、保修、质保、售后、FreeD 是标配吗”是 knowledge_lookup。
- 商业承诺、合同、交付、最低价、一定能、免费、库存相关倾向 handoff。
用户问题：{query}
规则初筛：{json.dumps(fallback.to_metadata(), ensure_ascii=False)}
上下文摘要：{json.dumps(context, ensure_ascii=False)[:500]}
输出 JSON：
{{"intent":"...","confidence":0.0,"scenario_terms":[],"action_terms":[],"product_anchors":[],"reason":"..."}}
"""

    def _route_policy_for_intent(self, intent: str) -> str:
        if intent in {"quote_price", "quote_recommendation", "quote_configuration_sheet"}:
            return "quote_draft"
        if intent == "identity":
            return "identity"
        if intent == "handoff":
            return "handoff"
        if intent == "correction_learning":
            return "learned_correction"
        if intent == "memory_followup":
            return "contextual"
        if intent == "knowledge_lookup":
            return "knowledge"
        return "fallback"

    def _result(
        self,
        intent: str,
        confidence: float,
        route_policy: str,
        scenario_terms: list[str],
        action_terms: list[str],
        product_anchors: list[str],
        needs_retrieval: bool,
        needs_quote_tool: bool,
        reason: str,
        risk_flags: list[str] | None = None,
        contextual_followup: bool = False,
        inherited_from_history: bool = False,
        inherited_route: str = "",
        resolved_query: str = "",
        history_anchor_summary: str = "",
    ) -> IntentResult:
        return IntentResult(
            intent=intent,
            confidence=confidence,
            route_policy=route_policy,
            scenario_terms=list(dict.fromkeys(scenario_terms)),
            action_terms=list(dict.fromkeys(action_terms)),
            product_anchors=list(dict.fromkeys(product_anchors)),
            needs_retrieval=needs_retrieval,
            needs_quote_tool=needs_quote_tool,
            reason=reason,
            risk_flags=risk_flags or [],
            contextual_followup=contextual_followup,
            inherited_from_history=inherited_from_history,
            inherited_route=inherited_route,
            resolved_query=resolved_query,
            history_anchor_summary=history_anchor_summary,
        )

    @classmethod
    def _is_short_followup(
        cls,
        text: str,
        short_followup_terms: list[str],
        scenario_terms: list[str],
        product_anchors: list[str],
    ) -> bool:
        compact = str(text or "").strip()
        if not compact or len(compact) > 28:
            return False
        if short_followup_terms and (scenario_terms or product_anchors):
            return True
        if product_anchors and any(word in compact for word in ("可以", "行", "适合")):
            return True
        if short_followup_terms and len(compact) <= 12:
            return True
        return False

    @classmethod
    def _has_price_context(cls, last_message: str, last_answer: str) -> bool:
        text = f"{last_message}\n{last_answer}"
        return any(word in text for word in [*cls.PRICE_TERMS, "参考价", "参考合计", "合计约", "报价草案"])

    @classmethod
    def _resolved_followup_query(
        cls,
        text: str,
        last_message: str,
        last_answer: str,
        anchors: list[str],
        scenario_terms: list[str],
        inherited_route: str,
        quote_like: bool,
    ) -> str:
        anchor_text = "、".join(list(dict.fromkeys([str(item).strip() for item in anchors if str(item).strip()]))[:6])
        scenario_text = "、".join(scenario_terms)
        last_bits = []
        if last_message:
            last_bits.append(f"上一轮客户问题：{last_message[:120]}")
        if last_answer:
            last_bits.append(f"上一轮客服回答摘要：{last_answer.replace(chr(10), ' ')[:180]}")
        prefix = "基于上一轮报价" if quote_like or inherited_route == "quote_draft" else "基于上一轮对话"
        if "GRA" in str(text).upper():
            return f"基于上一轮团播推荐，用户追问 GRA 是否适合当前场景；当前追问：{text}；相关产品：{anchor_text}；{'；'.join(last_bits)}"
        if "影视" in text:
            return f"基于上一轮报价或方案，用户追问影视版/影视场景版本差异或价格口径；当前追问：{text}；相关产品：{anchor_text}；{'；'.join(last_bits)}"
        if scenario_text:
            return f"{prefix}，用户追问{scenario_text}相关版本或适配情况；当前追问：{text}；相关产品：{anchor_text}；{'；'.join(last_bits)}"
        return f"{prefix}，用户追问：{text}；相关产品：{anchor_text}；{'；'.join(last_bits)}"

    @staticmethod
    def _compact_history_summary(last_message: str, last_answer: str) -> str:
        bits = []
        if last_message:
            bits.append(f"上一问：{last_message[:80]}")
        if last_answer:
            bits.append(f"上一答：{last_answer.replace(chr(10), ' ')[:100]}")
        return "；".join(bits)

    @classmethod
    def _matched_terms(cls, text: str, terms: tuple[str, ...]) -> list[str]:
        lower = str(text or "").lower()
        rows = []
        for term in terms:
            term_text = str(term)
            if term_text.lower() in lower and term_text not in rows:
                rows.append(term_text)
        return rows

    @classmethod
    def _product_anchors(cls, text: str) -> list[str]:
        upper = str(text or "").upper()
        anchors = []
        for token in cls.PRODUCT_TERMS:
            token_upper = token.upper()
            if token_upper in upper and token_upper not in anchors:
                anchors.append(token_upper if token_upper != "FREE-D" else "FreeD")
        return anchors

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
    def _bounded_float(value: Any, default: float) -> float:
        try:
            number = float(value)
        except Exception:
            return default
        return max(0.0, min(number, 1.0))

    @staticmethod
    def _clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:12]
