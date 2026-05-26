from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.services.quote_catalog_service import QuoteCatalogService
from support_app.services.quote_policy_service import QuotePolicyService


class ConfigurationQuoteService:
    LIVE_SCENE_WORDS = ("直播", "直播间", "团播", "电商", "带货", "主播", "短视频")
    TRACK_WORDS = ("轨道", "横移", "推拉", "走位", "全景", "环绕")
    FREED_WORDS = ("freed", "free-d", "xr", "虚拟", "跟踪", "追踪", "unreal", "ue")
    FOCUS_WORDS = ("跟焦", "对焦", "fiz", "变焦", "光圈")
    DMX_WORDS = ("dmx", "灯光", "控台", "灯控")
    KEYBOARD_WORDS = ("键盘", "stream deck", "一键", "歌曲", "景别", "切歌", "自动运镜")
    TRAINING_WORDS = ("培训", "上门", "安装", "交付", "部署")
    URGENCY_WORDS = ("本周", "下周", "这个月", "下个月", "马上", "尽快", "急")

    def __init__(
        self,
        quote_catalog_service: QuoteCatalogService,
        policy_service: QuotePolicyService,
        feedback_store: JsonFileRepository,
    ):
        self.quote_catalog_service = quote_catalog_service
        self.policy_service = policy_service
        self.feedback_store = feedback_store

    def draft(self, message: str, scenario: str = "live_commerce", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            raise ValueError("message 不能为空")
        metadata = metadata or {}
        memory = metadata.get("memory") if isinstance(metadata.get("memory"), dict) else {}

        needs = self.extract_needs(text, scenario, memory)
        scene_id = self.quote_catalog_service.scene_for(text, scenario)
        if needs.get("scenario") in {"group_live", "broadcast", "film_pro"} and not any(word in text for word in ("电视台", "晚会", "广播", "影视", "TVC", "广告", "团播", "直播")):
            scene_id = needs["scenario"]
        package = self.quote_catalog_service.package_for(scene_id)
        arm = self.quote_catalog_service.recommend_arm(text, package, needs)
        needs["scenario"] = scene_id
        needs["package_name"] = package.get("name", "")
        needs["recommended_arm"] = arm.get("id", "")

        modules = self.recommend_modules(text, needs, package, arm)
        quote_items = self._quote_items(modules, needs)
        sources = self._source_refs(package, arm, modules)
        missing_questions = self._missing_questions(needs)
        review_flags = self._review_flags(text, quote_items, missing_questions, package)
        summary = self._summary(needs, modules, missing_questions)

        return {
            "ok": True,
            "status": "draft",
            "scenario": needs["scenario"],
            "package": {
                "id": package.get("id", ""),
                "name": package.get("name", ""),
                "scenario": package.get("scenario", ""),
                "description": package.get("description", ""),
            },
            "recommended_arm": {
                "id": arm.get("id", ""),
                "name": arm.get("name", ""),
                "span": arm.get("span", ""),
                "payload": arm.get("payload", ""),
                "description": arm.get("description", ""),
                "reference_price": self.quote_catalog_service.quote_price_for_arm(arm, package),
            },
            "alternative_arms": self.quote_catalog_service.alternatives_for(package),
            "message": text,
            "needs": needs,
            "modules": modules,
            "quote_items": quote_items,
            "source_refs": sources,
            "missing_questions": missing_questions,
            "review_flags": review_flags,
            "summary": summary,
            "metadata": metadata,
            "generated_at": self._now(),
        }

    def save_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = self.feedback_store.load_list()
        item = {
            "id": f"config_feedback_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "message": str(payload.get("message", "") or "")[:1000],
            "verdict": str(payload.get("verdict", "") or "needs_review"),
            "notes": str(payload.get("notes", "") or "")[:1000],
            "draft": payload.get("draft") if isinstance(payload.get("draft"), dict) else {},
            "created_at": self._now(),
        }
        items.insert(0, item)
        self.feedback_store.save_list(items[:500])
        return {"ok": True, "item": item, "total": len(items[:500])}

    def list_feedback(self, q: str = "") -> dict[str, Any]:
        items = self.feedback_store.load_list()
        if q:
            keyword = q.strip().lower()
            items = [item for item in items if keyword in str(item).lower()]
        return {"total": len(items), "items": items[:100]}

    def extract_needs(self, text: str, scenario: str = "live_commerce", memory: dict[str, Any] | None = None) -> dict[str, Any]:
        lowered = text.lower()
        memory = memory or {}
        remembered_scenario = self._scenario_from_memory(memory.get("scenario", ""))
        live_scene = any(word in text for word in self.LIVE_SCENE_WORDS) or remembered_scenario == "group_live" or scenario == "live_commerce"
        return {
            "scenario": remembered_scenario or ("live_commerce" if live_scene else scenario),
            "budget": self._budget(text) or str(memory.get("budget", "") or ""),
            "budget_value": self._money_to_number(self._budget(text) or str(memory.get("budget", "") or "")),
            "track_length": self._track_length(text),
            "camera_payload": self._camera_payload(text),
            "camera_count": self._camera_count(text) or str(memory.get("camera_count", "") or ""),
            "live_room_area": self._live_room_area(text) or str(memory.get("live_room_area", "") or ""),
            "robot_arm_count": self._robot_arm_count(text) or str(memory.get("robot_arm_count", "") or ""),
            "track_preference": self._track_preference(text) or str(memory.get("track_preference", "") or ""),
            "tracking_required": any(word in lowered for word in self.FREED_WORDS),
            "freed_required": any(word in lowered for word in self.FREED_WORDS),
            "focus_required": any(word in lowered for word in self.FOCUS_WORDS),
            "dmx_required": any(word in lowered for word in self.DMX_WORDS),
            "keyboard_required": any(word in lowered for word in self.KEYBOARD_WORDS),
            "training_required": any(word in text for word in self.TRAINING_WORDS),
            "delivery_urgency": self._first_match(text, self.URGENCY_WORDS),
            "explicit_products": self._explicit_products(text),
            "raw_message": text[:500],
        }

    def recommend_modules(self, text: str, needs: dict[str, Any], package: dict[str, Any], arm: dict[str, Any]) -> list[dict[str, Any]]:
        modules: list[dict[str, Any]] = []
        if arm:
            price = self.quote_catalog_service.quote_price_for_arm(arm, package)
            modules.append(self._module(
                name=arm.get("name", "U-MOCO 机械臂"),
                role="required",
                module_type="core_arm",
                reason=self._product_reason(arm, needs, package),
                source="结构化报价规则库",
                reference_price=price,
                catalog_item=arm,
                review_required=False,
            ))

        for option_id in package.get("required_options", []) or []:
            option = self.quote_catalog_service.option_for(option_id)
            if option:
                modules.append(self._option_module(option, "required", f"{package.get('name', '版本包')}核心配置。"))

        for option_id in package.get("recommended_options", []) or []:
            option = self.quote_catalog_service.option_for(option_id)
            if option:
                modules.append(self._option_module(option, "recommended", option.get("description", "按场景建议选配。"), review_required=True))

        if self.quote_catalog_service.needs_track(text, needs):
            for option_id, reason in (
                ("film_track", "客户提到轨道、走位、横移、全景/环绕或空间调度，轨道需作为独立报价项。"),
                ("track_motor", "机械臂上轨道时通常需要轨道电机，需结合现场轨道方案确认。"),
            ):
                option = self.quote_catalog_service.option_for(option_id)
                if option:
                    modules.append(self._option_module(option, "optional", reason, review_required=True))
        if needs.get("freed_required") and not any(item.get("catalog_item", {}).get("id") == "freed_xr" for item in modules):
            option = self.quote_catalog_service.option_for("freed_xr")
            if option:
                modules.append(self._option_module(option, "optional", "客户提到 FreeD/XR/虚拟跟踪，需要确认现场系统和协议适配。", review_required=True))
        if needs.get("focus_required"):
            option = self.quote_catalog_service.option_for("fiz_focus")
            if option and not any(item.get("catalog_item", {}).get("id") == "fiz_focus" for item in modules):
                modules.append(self._option_module(option, "optional", "客户提到跟焦、对焦、变焦或光圈控制，需要拆成可选项。"))
        if needs.get("dmx_required") and not any(item.get("catalog_item", {}).get("id") == "dmx_control" for item in modules):
            option = self.quote_catalog_service.option_for("dmx_control")
            if option:
                modules.append(self._option_module(option, "optional", "客户提到灯光或控台联动，需要确认现场灯控品牌与连接方式。", review_required=True))
        if needs.get("training_required") or needs["scenario"] in {"group_live", "broadcast"}:
            option = self.quote_catalog_service.option_for("training")
            if option and not any(item.get("catalog_item", {}).get("id") == "training" for item in modules):
                modules.append(self._option_module(option, "recommended", "现场安装、按键映射、运镜交付和培训需结合城市、排期与交付范围确认。", review_required=True))

        return modules

    def _quote_items(self, modules: list[dict[str, Any]], needs: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for module in modules:
            quantity = self._quantity_for_module(module, needs)
            rows.append({
                "name": module["name"],
                "role": module["role"],
                "quantity": quantity,
                "unit": module.get("unit") or ("米" if module["module_type"] == "track" else "项"),
                "reference_price": module.get("reference_price", ""),
                "reference_total": self._reference_total(module.get("reference_price", ""), quantity),
                "source": module.get("source", ""),
                "reason": module.get("reason", ""),
                "review_required": bool(module.get("review_required")) or bool(module.get("reference_price")),
            })
        return rows

    def _source_refs(self, package: dict[str, Any], arm: dict[str, Any], modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "quote_rule",
                "title": "结构化报价规则库",
                "section": package.get("name", ""),
                "source": "data/quote_catalog.json",
                "category": "报价规则",
                "score": 1,
                "snippet": package.get("description", ""),
            },
            {
                "type": "quote_rule",
                "title": arm.get("name", "U-MOCO 机械臂"),
                "section": "臂型价格",
                "source": "data/quote_catalog.json",
                "category": "臂型",
                "score": 1,
                "snippet": arm.get("description", ""),
            },
        ]

    def _missing_questions(self, needs: dict[str, Any]) -> list[str]:
        questions = []
        if not needs.get("budget"):
            if needs.get("scenario") == "group_live":
                questions.append("客户预算区间是多少？预算会影响臂形档位、轨道方案和控制选配范围。")
            else:
                questions.append("客户预算区间是多少？预算会决定 AIR/MINI/GRA/PRO/EXT 的推荐档位。")
        if not needs.get("track_length"):
            questions.append("现场是否需要轨道？如果需要，轨道长度和可用空间是多少米？")
        if not needs.get("camera_payload"):
            questions.append("客户使用的相机、镜头和附件总重量大约多少？")
        if not needs.get("camera_count"):
            questions.append("现场需要几台相机或几个机位？")
        if needs.get("scenario") == "broadcast" and not needs.get("freed_required"):
            questions.append("是否需要 FreeD/XR/虚拟制作跟踪，以及现场同步/讯道系统如何接入？")
        elif not needs.get("freed_required"):
            questions.append("是否需要 FreeD/XR/虚拟制作跟踪，还是只做常规直播运镜？")
        if not needs.get("delivery_urgency"):
            questions.append("客户期望交付和培训时间是什么？")
        return questions[:6]

    def _review_flags(self, text: str, quote_items: list[dict[str, Any]], missing_questions: list[str], package: dict[str, Any]) -> list[str]:
        policy = self.policy_service.get()
        approval = policy.get("approval_required", [])
        flags = ["当前结果是内部配置与报价项草稿，不是正式报价。"]
        if package.get("id") == "group_live":
            flags.append("团播选型需按直播间面积、直播效果需求、走位范围和相机负载确认，不能只按默认型号硬推。")
            flags.append("轨道不默认添加，只有客户需要横移、走位、全景/环绕或明确轨道长度时才拆成选配。")
        if package.get("id") == "broadcast":
            flags.append("广播版涉及讯道机、虚拟拍摄、帧同步和现场协议适配，必须由人工复核。")
        if any(item.get("reference_price") for item in quote_items):
            flags.append("所有参考价格、优惠价和历史报价都需要销售主管复核。")
        if missing_questions:
            flags.append("客户需求信息未完整，缺失问题未确认前不应发送正式报价。")
        if any(word in text for word in ("优惠", "折扣", "合同", "交付", "保证", "承诺")):
            flags.append("客户提到优惠、合同、交付或承诺类事项，必须人工确认。")
        for item in approval:
            if str(item) and str(item) not in "、".join(flags):
                continue
        return flags

    def _primary_product(self, text: str, needs: dict[str, Any]) -> dict[str, Any]:
        catalog = self.catalog_service.get()
        products = catalog.get("products", []) if isinstance(catalog, dict) else []
        explicit = needs.get("explicit_products") or []
        if explicit:
            matched = self._find_single_product(products, explicit) or self._find_product(products, explicit)
            if matched:
                return matched

        budget = needs.get("budget_value") or 0
        if self._is_group_streaming(text, needs):
            return self._find_single_product(products, ["GRA"]) or self._find_single_product(products, ["PRO"]) or self._find_single_product(products, ["EXT"]) or {}
        if "大型" in text or "电视台" in text or "广播" in text:
            return self._find_single_product(products, ["EXT"]) or self._find_single_product(products, ["PRO"]) or {}
        if self._needs_track(text, needs) and budget >= 450000:
            return self._find_single_product(products, ["GRA"]) or self._find_single_product(products, ["PRO"]) or {}
        if "小型" in text or "单人" in text or (budget and budget <= 250000):
            return self._find_single_product(products, ["AIR"]) or self._find_single_product(products, ["MINI"]) or {}
        if budget >= 700000:
            return self._find_single_product(products, ["PRO"]) or self._find_single_product(products, ["GRA"]) or {}
        return self._find_single_product(products, ["MINI"]) or self._find_single_product(products, ["GRA"]) or {}

    @classmethod
    def _is_group_streaming(cls, text: str, needs: dict[str, Any]) -> bool:
        return "团播" in text or "多人直播" in text or ("直播间" in text and needs.get("camera_count"))

    @staticmethod
    def _is_bundle_product(product: dict[str, Any]) -> bool:
        name = str(product.get("product", "")).upper()
        return "+" in name or "＋" in name or " AND " in name

    @classmethod
    def _find_single_product(cls, products: list[dict[str, Any]], tokens: list[str]) -> dict[str, Any]:
        token_set = [token.upper() for token in tokens]
        singles = [product for product in products if not cls._is_bundle_product(product)]
        for product in singles:
            name = str(product.get("product", "")).upper()
            if all(token in name for token in token_set):
                return product
        return {}

    @staticmethod
    def _find_product(products: list[dict[str, Any]], tokens: list[str]) -> dict[str, Any]:
        token_set = [token.upper() for token in tokens]
        for product in products:
            haystack = f"{product.get('product', '')} {product.get('version', '')} {product.get('source', '')}".upper()
            if all(token in haystack for token in token_set):
                return product
        for product in products:
            haystack = f"{product.get('product', '')} {product.get('version', '')} {product.get('source', '')}".upper()
            if any(token in haystack for token in token_set):
                return product
        return {}

    def _accessory_module(self, name: str, needs: dict[str, Any], reason: str, review_required: bool = False) -> dict[str, Any]:
        accessory = self._find_accessory(name)
        return self._module(
            name=name,
            role="optional",
            module_type="track" if "轨道" in name else "accessory",
            reason=reason,
            source=accessory.get("source", ""),
            reference_price=accessory.get("reference_price", ""),
            catalog_item=accessory,
            review_required=review_required,
        )

    def _find_accessory(self, name: str) -> dict[str, Any]:
        for item in self.quote_catalog_service.get().get("options", []):
            if str(item.get("name", "")) in name or name in str(item.get("name", "")):
                return item
        return {}

    def _option_module(self, option: dict[str, Any], role: str, reason: str, review_required: bool = False) -> dict[str, Any]:
        category = str(option.get("category", "accessory"))
        module_type = "track" if category == "track" else category
        return self._module(
            name=option.get("name", "选配项"),
            role=role,
            module_type=module_type,
            reason=reason,
            source="结构化报价规则库",
            reference_price=option.get("reference_price", ""),
            unit=option.get("unit", ""),
            catalog_item=option,
            review_required=review_required,
        )

    @staticmethod
    def _module(
        name: str,
        role: str,
        module_type: str,
        reason: str,
        source: str = "",
        reference_price: str = "",
        unit: str = "",
        catalog_item: dict[str, Any] | None = None,
        review_required: bool = False,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "role": role,
            "module_type": module_type,
            "reason": reason,
            "source": source,
            "reference_price": reference_price,
            "unit": unit,
            "catalog_item": catalog_item or {},
            "review_required": review_required,
        }

    @staticmethod
    def _product_reason(product: dict[str, Any], needs: dict[str, Any], package: dict[str, Any]) -> str:
        product_name = product.get("name", "该型号")
        package_name = package.get("name", "版本包")
        if package.get("id") == "group_live":
            return f"{product_name} 是团播场景的候选臂形之一，最终要按直播间面积、直播效果需求、走位范围和相机负载确认。"
        if package.get("id") == "broadcast":
            return f"{product_name} 匹配广播版场景，适合把讯道机、虚拟拍摄、帧同步和广播控制硬件一起拆项。"
        if needs.get("track_length"):
            return f"{product_name} 命中{package_name}，且客户提到轨道需求，适合先作为核心机械臂方案拆解。"
        return f"{product_name} 命中{package_name}，可先作为核心机械臂方案，后续根据预算、负载和空间修正。"

    @classmethod
    def _needs_track(cls, text: str, needs: dict[str, Any]) -> bool:
        if needs.get("track_length"):
            return True
        if re.search(r"(不需要|不用|不要|暂不|不考虑|不确定|是否需要|要不要).{0,8}轨道", text):
            return False
        if re.search(r"轨道.{0,8}(不需要|不用|不要|暂不|不考虑|不确定|是否需要|要不要)", text):
            return False
        if re.search(r"(需要|希望|想要|要|加|上|配|配置|增加|安装).{0,8}轨道", text):
            return True
        if re.search(r"轨道.{0,8}(\d+(?:\.\d+)?\s*米|走位|横移|全景|环绕|推拉)", text):
            return True
        return any(word in text for word in ("横移", "推拉", "走位", "全景", "环绕"))

    @staticmethod
    def _quantity_for_module(module: dict[str, Any], needs: dict[str, Any]) -> float | int:
        unit = str(module.get("unit") or "")
        if module.get("module_type") == "track" and unit == "米" and needs.get("track_length"):
            try:
                return float(needs["track_length"])
            except Exception:
                return 1
        return 1

    @classmethod
    def _reference_total(cls, reference_price: str, quantity: float | int) -> str:
        text = str(reference_price or "")
        match = re.search(r"([¥￥])\s*([\d,]+(?:\.\d+)?)", text)
        if not match:
            return ""
        unit_price = float(match.group(2).replace(",", ""))
        total = unit_price * float(quantity or 1)
        return f"{match.group(1)}{total:,.0f}"

    @staticmethod
    def _explicit_products(text: str) -> list[str]:
        return list(dict.fromkeys(
            token.upper()
            for token in ("AIR", "MINI", "GRA", "PRO", "EXT", "air", "mini", "gra", "pro", "ext")
            if token in text
        ))

    @staticmethod
    def _budget(text: str) -> str:
        match = re.search(r"预算\s*([¥￥]?\s*\d+(?:\.\d+)?\s*[万千]?)", text)
        if match:
            return match.group(1).replace(" ", "")
        match = re.search(r"([¥￥]?\s*\d+(?:\.\d+)?\s*万)\s*(?:左右|以内|预算)?", text)
        return match.group(1).replace(" ", "") if match else ""

    @staticmethod
    def _money_to_number(value: str) -> float:
        text = str(value or "").replace(",", "").replace(" ", "")
        if not text:
            return 0
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match:
            return 0
        amount = float(match.group(1))
        if "万" in text:
            amount *= 10000
        elif "千" in text:
            amount *= 1000
        return amount

    @staticmethod
    def _track_length(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)(?:\s*[-~到至]\s*\d+(?:\.\d+)?)?\s*米\s*轨道", text)
        if match:
            return match.group(1)
        match = re.search(r"轨道\s*(\d+(?:\.\d+)?)\s*米", text)
        return match.group(1) if match else ""

    @staticmethod
    def _camera_payload(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤)\s*(?:相机|镜头|负载|载重)?", text)
        return match.group(1) if match else ""

    @staticmethod
    def _camera_count(text: str) -> str:
        match = re.search(r"([一二两三四五六七八九十\d]+)\s*(?:台|个|路)?\s*(?:相机|机位|摄像机)", text)
        return ConfigurationQuoteService._chinese_number(match.group(1)) if match else ""

    @staticmethod
    def _live_room_area(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:平|平方|平方米|㎡)", text)
        return match.group(1) if match else ""

    @staticmethod
    def _robot_arm_count(text: str) -> str:
        match = re.search(r"机械臂.{0,6}(?:用|要|配|上)?\s*([一二两三四五六七八九十\d]+)\s*台", text)
        if not match:
            match = re.search(r"([一二两三四五六七八九十\d]+)\s*台\s*机械臂", text)
        return ConfigurationQuoteService._chinese_number(match.group(1)) if match else ""

    @staticmethod
    def _track_preference(text: str) -> str:
        if any(word in text for word in ("固定机位", "不上轨道", "不需要轨道", "不用轨道", "先不上轨道")):
            return "暂不需要轨道"
        if any(word in text for word in ("轨道", "横移", "环绕", "走位", "全景")):
            return "需要进一步确认轨道"
        return ""

    @staticmethod
    def _scenario_from_memory(value: str) -> str:
        text = str(value or "")
        if "团播" in text or "直播间" in text or "直播" in text:
            return "group_live"
        if "电视台" in text or "晚会" in text or "广播" in text:
            return "broadcast"
        if "影视" in text or "TVC" in text or "广告" in text:
            return "film_pro"
        return ""

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

    @staticmethod
    def _first_match(text: str, words: tuple[str, ...]) -> str:
        for word in words:
            if word in text:
                return word
        match = re.search(r"(\d+月|\d+天内|\d+号)", text)
        return match.group(1) if match else ""

    @staticmethod
    def _summary(needs: dict[str, Any], modules: list[dict[str, Any]], missing_questions: list[str]) -> str:
        required = [item["name"] for item in modules if item["role"] == "required"]
        optional = [item["name"] for item in modules if item["role"] != "required"]
        package_name = needs.get("package_name") or "配置"
        arm_name = needs.get("recommended_arm") or "机械臂"
        parts = [
            f"已按{package_name}生成单条 {arm_name} 配置草稿。",
            f"核心模块：{'、'.join(required) if required else '待确认'}。",
        ]
        if optional:
            parts.append(f"可选/需拆项：{'、'.join(optional[:5])}。")
        if needs.get("budget"):
            parts.append(f"客户预算线索：{needs['budget']}。")
        if missing_questions:
            parts.append(f"还需补问 {len(missing_questions)} 个关键信息。")
        return "".join(parts)

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
