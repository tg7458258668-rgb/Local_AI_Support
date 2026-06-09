from __future__ import annotations

import re
from typing import Any

from support_app.schemas import ChatRequest
from support_app.services.behavior_config_service import BehaviorConfigService
from support_app.services.configuration_quote_service import ConfigurationQuoteService
from support_app.services.intent_service import IntentService
from support_app.services.pricing_catalog_service import PricingCatalogService
from support_app.services.quote_archive_service import QuoteArchiveService
from support_app.services.quote_policy_service import QuotePolicyService


class QuoteService:
    INTENT_WORDS = ("报价", "价格", "多少钱", "预算", "费用", "优惠", "便宜", "采购", "推荐", "选型", "配置单", "报价单")

    def __init__(
        self,
        catalog_service: PricingCatalogService,
        policy_service: QuotePolicyService,
        archive_service: QuoteArchiveService,
        behavior_config_service: BehaviorConfigService | None = None,
        configuration_quote_service: ConfigurationQuoteService | None = None,
    ):
        self.catalog_service = catalog_service
        self.policy_service = policy_service
        self.archive_service = archive_service
        self.behavior_config_service = behavior_config_service
        self.configuration_quote_service = configuration_quote_service

    def is_quote_request(self, message: str) -> bool:
        plan = IntentService().classify_rules(message)
        return bool(plan.needs_quote_tool)

    def draft(self, request: ChatRequest, memory: dict | None, doc_candidates: list[Any]) -> dict[str, Any]:
        if self.configuration_quote_service and self._should_use_configuration_quote(request.message, memory):
            return self._configuration_draft(request, memory)

        needs = self.extract_needs(request.message, memory)
        memory_anchors = self._memory_product_anchors(request.message, memory)
        matched_products = self.catalog_service.match_products(request.message)
        if (
            memory_anchors
            and not self._explicit_products(request.message)
            and self._previous_product_anchor_enabled()
        ):
            matched_products = self.catalog_service.match_products(" ".join(memory_anchors))
        if not matched_products:
            matched_products = self._products_from_docs(doc_candidates)
        if (
            memory_anchors
            and not self._explicit_products(request.message)
            and self._previous_product_anchor_enabled()
        ):
            matched_products = self._prefer_anchor_products(matched_products, memory_anchors)
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
            "memory_product_anchor": memory_anchors[:3],
        }
        answer = self._render_answer(draft)
        archive_item = None
        if not (request.metadata or {}).get("regression_test"):
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

    def _configuration_draft(self, request: ChatRequest, memory: dict | None) -> dict[str, Any]:
        intent_plan = (request.metadata or {}).get("intent_plan", {})
        scenario = self._scenario_for_configuration_quote(request.message, memory, intent_plan if isinstance(intent_plan, dict) else {})
        memory_for_quote = self._memory_for_configuration_quote(request.message, memory, intent_plan if isinstance(intent_plan, dict) else {})
        config = self.configuration_quote_service.draft(
            request.message,
            scenario,
            {
                "source": "chat_quote_service",
                "user_id": request.user_id,
                "memory": memory_for_quote or {},
                "intent_plan": intent_plan if isinstance(intent_plan, dict) else {},
            },
        )
        policy = self.policy_service.get()
        confirmation = self._confirmation_items(policy)
        core_products = [
            {
                "product": module.get("name", ""),
                "version": "",
                "base_price": module.get("reference_price", ""),
                "historical_offer": "",
                "source": module.get("source", ""),
                "configuration": [module.get("reason", "")] if module.get("reason") else [],
            }
            for module in config.get("modules", [])
            if module.get("module_type") == "core_arm"
        ]
        if not core_products and config.get("modules"):
            first = config["modules"][0]
            core_products = [{"product": first.get("name", ""), "version": "", "base_price": first.get("reference_price", ""), "configuration": []}]

        quote_items = [
            {
                "name": item.get("name", ""),
                "quantity": item.get("quantity", 1),
                "unit": item.get("unit", ""),
                "reference_price": item.get("reference_price", ""),
                "reference_total": item.get("reference_total", ""),
                "source": item.get("source", ""),
                "note": item.get("reason", ""),
                "review_required": item.get("review_required", False),
            }
            for item in config.get("quote_items", [])
        ]
        sources = self._config_sources(config.get("source_refs", []))
        if self._is_group_product_recommendation(request.message) and not self._explicit_products(request.message):
            recommended_products = self._configuration_products(config, core_products)
        else:
            recommended_products = core_products[:1]
        draft = {
            "need_summary": config.get("summary", "直播间/团播配置草案"),
            "recommended_products": recommended_products,
            "quote_items": quote_items,
            "reference_total": "",
            "pricing_policy": policy,
            "recent_quotes": self.archive_service.recent_for_customer(request.channel, request.user_id),
            "sources": sources,
            "requires_confirmation": confirmation,
            "status": "draft",
            "configuration_quote": config,
        }
        answer = self._render_configuration_answer(config, confirmation)
        archive_item = None
        if not (request.metadata or {}).get("regression_test"):
            archive_item = self.archive_service.add_for_customer(request.channel, request.user_id, {
                "need_summary": draft["need_summary"],
                "recommended_products": [item.get("product", "") for item in recommended_products],
                "quote_items": quote_items,
                "reference_total": "",
                "sources": sources,
                "requires_confirmation": confirmation,
                "answer": answer,
                "status": "draft",
            })
        if archive_item:
            draft["archive"] = archive_item
        return {"answer": answer, "draft": draft}

    @classmethod
    def _should_use_configuration_quote(cls, message: str, memory: dict | None) -> bool:
        text = str(message or "").strip()
        if not text:
            return False
        if cls._is_pure_overview_message(text):
            return False
        return True

    @staticmethod
    def _is_pure_overview_message(message: str) -> bool:
        plan = IntentService().classify_rules(message)
        return str(plan.intent or "") in {"product_overview", "company_intro", "service_overview"}

    @classmethod
    def _scenario_for_configuration_quote(cls, message: str, memory: dict | None, intent_plan: dict[str, Any]) -> str:
        text = str(message or "")
        if cls._has_group_live_scene(text):
            return "live_commerce"
        if cls._has_broadcast_scene(text):
            return "broadcast"
        if cls._has_film_scene(text):
            return "film_pro"
        if intent_plan.get("contextual_followup") and (
            cls._memory_scenario(memory) == "group_live" or cls._intent_has_group_live_scene(intent_plan)
        ):
            return "live_commerce"
        if cls._standalone_explicit_track_price(text, intent_plan):
            return "film_pro"
        return "film_pro"

    @classmethod
    def _memory_for_configuration_quote(cls, message: str, memory: dict | None, intent_plan: dict[str, Any]) -> dict[str, Any]:
        merged = dict(memory or {})
        if (
            cls._standalone_explicit_track_price(message, intent_plan)
            and not cls._has_any_scene_term(message)
            and not intent_plan.get("contextual_followup")
        ):
            merged.pop("scenario", None)
        return merged

    @staticmethod
    def _has_group_live_scene(message: str) -> bool:
        return any(word in str(message or "") for word in ("团播", "直播间", "直播", "电商直播", "带货", "主播"))

    @staticmethod
    def _has_broadcast_scene(message: str) -> bool:
        return any(word in str(message or "") for word in ("电视台", "晚会", "广播", "广电", "演播室"))

    @staticmethod
    def _has_film_scene(message: str) -> bool:
        return any(word in str(message or "") for word in ("影视", "影视版", "TVC", "tvc", "广告", "拍摄", "工作室"))

    @classmethod
    def _has_any_scene_term(cls, message: str) -> bool:
        return cls._has_group_live_scene(message) or cls._has_broadcast_scene(message) or cls._has_film_scene(message)

    @staticmethod
    def _memory_scenario(memory: dict | None) -> str:
        text = str((memory or {}).get("scenario", "") or "")
        if "团播" in text or "直播" in text:
            return "group_live"
        if "广播" in text or "电视台" in text:
            return "broadcast"
        if "影视" in text or "TVC" in text or "广告" in text:
            return "film_pro"
        return ""

    @staticmethod
    def _intent_has_group_live_scene(intent_plan: dict[str, Any]) -> bool:
        scenario_terms = intent_plan.get("scenario_terms", [])
        if isinstance(scenario_terms, list) and any(str(item) in {"团播", "直播", "直播间"} for item in scenario_terms):
            return True
        text = f"{intent_plan.get('resolved_query', '')} {intent_plan.get('history_anchor_summary', '')}"
        return any(word in str(text) for word in ("团播", "直播间", "直播"))

    @classmethod
    def _standalone_explicit_track_price(cls, message: str, intent_plan: dict[str, Any]) -> bool:
        text = str(message or "")
        upper = text.upper()
        has_arm = any(token in upper for token in ("GRA", "MINI", "AIR", "EXT", "PRO", "U-MOCO", "UMOCO"))
        has_track = "轨道" in text
        has_price = any(word in text for word in ("多少钱", "价格", "报价", "费用", "预算", "多少"))
        has_context_marker = any(word in text for word in ("这款", "刚才", "刚刚", "上次", "之前", "那个", "这个方案", "这套", "继续"))
        return has_arm and has_track and has_price and not has_context_marker and not intent_plan.get("contextual_followup")

    @classmethod
    def _is_group_product_recommendation(cls, message: str) -> bool:
        text = str(message or "")
        return "团播" in text and any(word in text for word in ("推荐", "产品", "型号", "臂形", "选型", "怎么选"))

    @staticmethod
    def _configuration_products(config: dict[str, Any], core_products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = list(core_products[:1])
        package = config.get("package") or {}
        for item in config.get("alternative_arms", []) or []:
            rows.append({
                "product": item.get("name", ""),
                "version": package.get("name", ""),
                "base_price": item.get("reference_price", ""),
                "historical_offer": "",
                "source": "结构化报价规则库",
                "configuration": [item.get("description", "")] if item.get("description") else [],
            })
        return rows

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
    def _explicit_products(message: str) -> list[str]:
        text = str(message or "")
        return [token for token in ("AIR", "MINI", "GRA", "PRO", "EXT", "mini", "gra", "pro", "ext") if token in text]

    @classmethod
    def _memory_product_anchors(cls, message: str, memory: dict | None) -> list[str]:
        if not memory:
            return []
        text = str(message or "")
        if not any(word in text for word in ("上次", "之前", "刚才", "前面", "上一轮", "那个", "这款")):
            return []
        products = [str(item).strip().upper() for item in memory.get("products", []) if str(item).strip()]
        anchors = []
        for item in products:
            for token in ("MINI", "GRA", "PRO", "EXT", "AIR"):
                if token in item and token not in anchors:
                    anchors.append(token)
        return anchors

    def _previous_product_anchor_enabled(self) -> bool:
        if not self.behavior_config_service:
            return True
        return bool(self.behavior_config_service.memory_policy().get("previous_product_anchor", True))

    @staticmethod
    def _prefer_anchor_products(products: list[dict[str, Any]], anchors: list[str]) -> list[dict[str, Any]]:
        if not anchors:
            return products
        anchor_set = {item.upper() for item in anchors}

        def score(item: dict[str, Any]) -> tuple[int, int]:
            haystack = f"{item.get('product', '')} {item.get('version', '')} {item.get('source', '')} {item.get('doc_name', '')}".upper()
            matched = sum(1 for token in anchor_set if token in haystack)
            extra_core_tokens = sum(1 for token in ("GRA", "PRO", "EXT", "AIR") if token in haystack and token not in anchor_set)
            return (-matched, extra_core_tokens)

        return sorted(products, key=score)

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
            f"可以，我先按“{need_summary}”给你一个参考方向。",
            "我们会先看场景价值，不会一上来把所有配置都堆给客户：核心是让机械臂运镜、镜头控制和现场流程更稳定、更可复制。",
            f"{product_name} 可以先作为候选方案来评估，具体型号还是要看直播间面积、画面效果需求、相机镜头重量和预算。",
            f"参考预算先按 {total} 做内部口径；轨道、FreeD、跟焦、软件授权和培训这些后面按客户需求再单独拆。",
            f"优惠价、交付时间、合同条款和特殊定制需要人工同事复核后才能作为正式报价。当前需要确认：{confirm}。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_configuration_answer(config: dict[str, Any], confirmation: list[str]) -> str:
        modules = config.get("modules", [])
        needs = config.get("needs", {})
        message = str(config.get("message", ""))
        package = config.get("package") or {}
        recommended_arm = config.get("recommended_arm") or {}
        alternatives = config.get("alternative_arms") or []
        core = next((item for item in modules if item.get("module_type") == "core_arm"), {})
        core_name = recommended_arm.get("name") or core.get("name") or "U-MOCO 机械臂"
        core_price = recommended_arm.get("reference_price") or core.get("reference_price", "")
        has_track = any(item.get("module_type") == "track" for item in modules)
        missing = config.get("missing_questions", [])
        package_name = package.get("name") or "推荐方案"
        metadata = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        intent_plan = metadata.get("intent_plan") if isinstance(metadata.get("intent_plan"), dict) else {}
        contextual_followup = bool(intent_plan.get("contextual_followup"))
        required = [
            item.get("name", "")
            for item in modules
            if item.get("role") == "required" and item.get("module_type") != "core_arm" and item.get("name")
        ]
        optional = [item.get("name", "") for item in modules if item.get("role") != "required" and item.get("name")]
        is_price_question = any(word in message for word in ("价格", "多少钱", "报价", "费用", "预算", "多少"))
        is_config_sheet_request = QuoteService._is_configuration_sheet_request(message)
        package_id = package.get("id")
        track_price_requested = is_price_question and has_track

        explicit_products = [str(item).upper() for item in needs.get("explicit_products", []) or []]
        scenario_unconfirmed_track_quote = (
            package_id == "film_pro"
            and track_price_requested
            and explicit_products
            and not QuoteService._has_any_scene_term(message)
        )

        if package_id == "group_live" and is_config_sheet_request:
            lines = QuoteService._render_group_live_configuration_sheet(config, confirmation)
        elif package_id == "group_live" and is_price_question and explicit_products:
            lines = [
                f"{core_name} 可以作为这个团播方案的核心臂形来核价。",
                "团播方案的价值不只是机械臂本体，而是把自动运镜、镜头控制和现场一键操作做成稳定流程，减少人工临场切换的不确定性。",
                "具体选 U-MOCO GRA、U-MOCO EXT 还是 U-MOCO PRO，还是要看直播间面积、主播走位范围、想要的画面效果和相机镜头重量；轨道也是根据横移、环绕或大范围走位需求再加。",
            ]
        elif package_id == "group_live" and explicit_products:
            lead = (
                f"接着刚才团播场景说，{core_name} 可以重点看。"
                if contextual_followup
                else f"{core_name} 可以作为团播方案里的重点候选，但我不会只按型号硬推。"
            )
            lines = [
                lead,
                "它比较适合先把团播间最常见的自动运镜、景别切换和镜头控制跑起来，画面稳，现场也少靠人临时切。",
                "具体是不是选它，要看直播间面积、主播走位、想要的直播效果以及相机镜头重量；如果空间更大、效果要求更强或负载更高，再看 EXT/PRO 或轨道方案。",
                "给客户介绍时可以先讲它适合中小型团播间，方案不会一下做得太重；配置和报价等客户确认面积、机位和预算后再展开。",
            ]
        elif package_id == "group_live" and any(needs.get(key) for key in ("live_room_area", "camera_count", "robot_arm_count", "track_preference")):
            area = needs.get("live_room_area")
            camera_count = needs.get("camera_count")
            arm_count = needs.get("robot_arm_count")
            facts = []
            if area:
                facts.append(f"{area} 平直播间")
            if camera_count:
                facts.append(f"{camera_count} 个机位")
            if arm_count:
                facts.append(f"{arm_count} 台机械臂")
            fact_text = "、".join(facts) or "你补充的情况"
            selection_line = (
                f"结合{fact_text}，我会先看面积、走位范围和想要的画面效果，再在 U-MOCO GRA、U-MOCO EXT、U-MOCO PRO 里选档位。"
                if facts
                else "型号我不会直接拍死。先看直播间面积、走位范围和想要的直播效果，再在 U-MOCO GRA、U-MOCO EXT、U-MOCO PRO 里选档位。"
            )
            lines = [
                "可以，你们做团播的话，这个场景我们比较熟。",
                "我们这套不是单纯让机械臂动起来，而是帮直播间把运镜、景别和镜头控制做稳。主播走位的时候画面不乱，现场也少靠人临时切。",
                selection_line,
                "如果只是固定机位加顺滑运镜，GRA 这档可以先看；如果要横移、环绕、大范围走位，或者设备更重，再看 EXT/PRO 和轨道。",
            ]
            lines.append("你先给我直播间面积和想要的效果，我就能把方案收成标准版/升级版，不会一上来把所有配置全摊开。")
        elif package_id == "group_live":
            lines = [
                "可以，你们做团播的话，这个场景我们比较熟。",
                "我们这套不是单纯让机械臂动起来，而是帮直播间把机械臂自动运镜、景别切换和镜头控制做稳。主播走位的时候画面不乱，现场也少靠人临时切。",
                "具体选 U-MOCO GRA、U-MOCO EXT 还是 U-MOCO PRO，要看直播间面积、主播走位范围、想要的直播效果，以及相机镜头和附件重量。",
                "简单说：固定机位加顺滑运镜，可以先看 U-MOCO GRA 这个档位；如果要横移、环绕、大范围走位，或者设备更重，再看 EXT/PRO 和轨道。",
                "你先告诉我直播间大概面积，以及想要的是稳定景别切换、横移环绕，还是更强的视觉效果，我再给你收一版方案，不会一上来把所有配置全摊开。",
            ]
        elif package_id == "broadcast":
            lines = [
                f"如果是电视台、晚会或广播播出场景，建议先按 {package_name} 的标准来聊。",
                "这类客户最看重的是播出稳定性、系统联动和现场风险控制，我们会先把讯道、同步、虚拟拍摄和控制链路的可靠性讲清楚。",
            ]
            if required:
                lines.append(f"具体配置可以后面再按现场系统拆，第一步先确认 {core_name} 是否匹配场地范围和负载。")
        else:
            if scenario_unconfirmed_track_quote:
                neutral_length = QuoteService._format_quantity(needs.get("track_length")) if needs.get("track_length") else "对应长度"
                lines = [
                    "可以先粗算，但我先说明一下：你这句还没说是团播版、影视版还是广播版，我不会默认按团播来算。",
                    f"下面先按常规专业版口径，把 {core_name} + {neutral_length} 米地面轨道 + 轨道电机做参考；如果你确认是团播版或广播版，控制软件、现场联动和交付范围要重新核。",
                ]
            else:
                lines = [
                    f"如果是自媒体工作室、TVC 或影视拍摄，建议先按 {package_name} 的拍摄效率和画面稳定性来讲。",
                    f"{core_name} 可以作为候选核心臂形，具体型号还是看场地空间、镜头重量、运动范围和客户想要的画面效果。",
                ]
                if required:
                    lines.append("具体配置和选配可以后面按拍摄流程再拆，避免一开始把客户压得太重。")
        if optional and package_id != "group_live" and not scenario_unconfirmed_track_quote:
            lines.append(f"可选项可以按现场需要再加，比如 {'、'.join(optional[:5])}。")
        if core_price and is_price_question and not track_price_requested:
            lines.append(f"如果先按单条 {core_name} 看，当前参考臂型价格是 {core_price}，不是多条机械臂组合单，也不默认包含轨道。")
        if has_track:
            length = needs.get("track_length")
            if track_price_requested:
                length_text = f"{QuoteService._format_quantity(length)} 米" if length else "这个长度"
                lines.extend(QuoteService._track_price_lines(core_name, core_price, config.get("quote_items", []), length_text))
                lines.append("上轨道默认需要配轨道电机，我先按这个口径一起算。")
                if scenario_unconfirmed_track_quote:
                    lines.append("还需要确认三点：这是团播版、影视版还是广播版？现场层高大概多少？上轨道主要是横移、环绕、大范围走位，还是预留升级？")
                else:
                    lines.append("还想确认两点：直播间层高大概多少？上轨道主要是为了横移、环绕、大范围走位，还是只是想保留后续升级空间？")
                lines.append("以上是参考报价口径，正式价格、优惠和交付安排还需要结合现场配置复核。")
            else:
                suffix = f"目前可以先按 {length} 米轨道单独核算。" if length else "轨道会作为独立选配单独核算。"
                lines.append(f"你提到轨道/走位需求的话，我会把它单独拆出来；{suffix}")
        if any(item.get("name") == "FreeD / XR 跟踪协议" for item in modules):
            lines.append("FreeD/XR/虚拟跟踪可以做，但需要确认现场系统和协议适配。")
        if missing and not is_price_question and package_id != "group_live":
            questions = [str(item).rstrip("。；; ") for item in missing[:4]]
            lines.append("为了把方案收得更贴近现场，我再确认两点：\n" + "\n".join(f"- {item}" for item in questions[:2]))
        if confirmation and is_price_question and not track_price_requested:
            lines.append("正式价格、优惠和交付安排需要结合现场配置再核一版，我可以先按你的场地和预算给你拆方案。")
        return "\n".join(lines)

    @staticmethod
    def _is_configuration_sheet_request(message: str) -> bool:
        text = str(message or "")
        sheet_words = ("配置单", "配置清单", "方案单", "报价单", "清单")
        write_words = ("写一份", "出一份", "做一份", "生成", "整理", "发客户", "发给客户", "寄出", "给客户")
        return any(word in text for word in sheet_words) and (
            any(word in text for word in write_words) or "团播" in text or "直播间" in text
        )

    @staticmethod
    def _render_group_live_configuration_sheet(config: dict[str, Any], confirmation: list[str]) -> list[str]:
        package = config.get("package") or {}
        modules = config.get("modules") or []
        quote_items = config.get("quote_items") or []
        missing = [str(item).rstrip("。；; ") for item in config.get("missing_questions", []) or []]
        review_flags = [str(item).rstrip("。；; ") for item in config.get("review_flags", []) or []]
        required = [item for item in modules if item.get("role") == "required"]
        recommended = [item for item in modules if item.get("role") != "required"]
        total = QuoteService._quote_items_total(quote_items)
        total_text = f"¥{total:,.0f}" if total else "需按最终配置核算"

        lines = [
            "可以，我先给你整理一份可发客户的团播配置单草案：",
            "",
            "【U-MOCO 团播直播间配置单｜参考草案】",
            f"方案版本：{package.get('name') or '团播版'}",
            "适用场景：团播直播间、电商直播间、多人主播景别切换与自动运镜。",
            "",
            "一、核心配置",
        ]
        for index, item in enumerate(required, 1):
            price = item.get("reference_price") or "需按最终配置核算"
            reason = item.get("reason") or item.get("description") or ""
            lines.append(f"{index}. {item.get('name', '-') }｜{price}" + (f"｜{reason}" if reason else ""))

        if recommended:
            lines.extend(["", "二、建议选配"])
            for index, item in enumerate(recommended, 1):
                price = item.get("reference_price") or "需按最终配置核算"
                reason = item.get("reason") or item.get("description") or ""
                lines.append(f"{index}. {item.get('name', '-') }｜{price}" + (f"｜{reason}" if reason else ""))

        lines.extend(["", "三、参考价格口径"])
        for item in quote_items:
            name = item.get("name") or "-"
            quantity = QuoteService._format_quantity(item.get("quantity"))
            unit = item.get("unit") or ""
            price = item.get("reference_price") or "需按最终配置核算"
            subtotal = item.get("reference_total") or price
            lines.append(f"- {name}：{quantity}{unit}，参考单价 {price}，参考小计 {subtotal}")
        lines.append(f"参考合计：{total_text}")

        lines.extend([
            "",
            "四、说明与待确认",
            "1. 以上为内部参考配置单，不是最终成交报价。",
            "2. 优惠价、交付周期、安装培训、合同条款和售后范围需要销售同事复核后确认。",
        ])
        for index, item in enumerate(missing[:4], 3):
            lines.append(f"{index}. {item}")
        if confirmation:
            lines.append(f"需人工复核项：{'、'.join(confirmation[:6])}。")
        if review_flags:
            lines.append(f"内部提醒：{review_flags[0]}。")
        return lines

    @classmethod
    def _quote_items_total(cls, quote_items: list[dict[str, Any]]) -> float:
        total = 0.0
        for item in quote_items or []:
            total += cls._money_to_number(item.get("reference_total") or item.get("reference_price") or "")
        return total

    @classmethod
    def _track_price_lines(cls, core_name: str, core_price: str, quote_items: list[dict[str, Any]], length_text: str) -> list[str]:
        core_total = cls._money_to_number(core_price)
        track_item = cls._find_quote_item(quote_items, "轨道")
        motor_item = cls._find_quote_item(quote_items, "轨道电机")
        track_total = track_item.get("reference_total") or track_item.get("reference_price", "")
        motor_total = motor_item.get("reference_total") or motor_item.get("reference_price", "")
        total = core_total + cls._money_to_number(track_total) + cls._money_to_number(motor_total)
        total_text = f"¥{total:,.0f}" if total else "需按最终配置核算"
        return [
            f"你提到 {core_name} 加 {length_text}轨道，我先按“机械臂 + 地面轨道 + 轨道电机”的基础组合给你一个参考口径。",
            f"{core_name} 参考价：{core_price or '需按最终配置核算'}。",
            f"{track_item.get('name', '地面轨道')}：{cls._format_quantity(track_item.get('quantity'))}{track_item.get('unit') or ''}，参考小计 {track_total or '需按最终配置核算'}。",
            f"{motor_item.get('name', '轨道电机')}：默认随上轨道配置，参考小计 {motor_total or '需按最终配置核算'}。",
            f"这三项参考合计约 {total_text}，不含最终优惠、交付、安装培训和其他场景选配。",
        ]

    @staticmethod
    def _find_quote_item(quote_items: list[dict[str, Any]], keyword: str) -> dict[str, Any]:
        for item in quote_items or []:
            if keyword in str(item.get("name", "")):
                return item
        return {}

    @staticmethod
    def _format_quantity(value: Any) -> str:
        try:
            number = float(value)
        except Exception:
            return str(value or "")
        return str(int(number)) if number.is_integer() else str(number)

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
    def _config_sources(items: list[dict[str, Any]]) -> list[str]:
        sources = []
        for item in items:
            label = item.get("source") or item.get("doc_name") or ""
            if label and label not in sources:
                sources.append(label)
        return sources[:5]

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
