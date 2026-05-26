from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository


DEFAULT_QUOTE_CATALOG: dict[str, Any] = {
    "version": 1,
    "currency": "CNY",
    "arms": [
        {
            "id": "AIR",
            "name": "U-MOCO AIR",
            "description": "轻量入门机械臂，适合小型拍摄；团播场景需结合直播间面积、效果需求和负载谨慎评估。",
            "span": "",
            "payload": "",
            "prices": {"标准版": "¥198,000", "专业版": "¥208,000"},
        },
        {
            "id": "MINI",
            "name": "U-MOCO MINI",
            "description": "小型机械臂，适合轻量影像项目；团播场景需结合直播间面积、效果需求和负载谨慎评估。",
            "span": "",
            "payload": "",
            "prices": {"标准版": "¥318,000", "专业版": "¥328,000", "旗舰版": "¥368,000", "广播版": "¥548,000"},
        },
        {
            "id": "GRA",
            "name": "U-MOCO GRA",
            "description": "团播直播间常用候选臂形之一，适合中小型单条机械臂直播方案，最终按面积、走位、效果需求和负载确认。",
            "span": "约 2 米",
            "payload": "",
            "prices": {"标准版": "¥438,000", "专业版": "¥448,000", "旗舰版": "¥508,000", "广播版": "¥978,000"},
        },
        {
            "id": "PRO",
            "name": "U-MOCO PRO",
            "description": "高负载、专业拍摄臂形，适合更重相机镜头组合和高规格影视/TVC。",
            "span": "约 2.7 米",
            "payload": "约 50 公斤",
            "prices": {"标准版": "¥708,000", "专业版": "¥718,000", "旗舰版": "¥778,000", "广播版": "¥1,248,000"},
        },
        {
            "id": "EXT",
            "name": "U-MOCO EXT",
            "description": "大臂展空间调度臂形，适合大直播间、舞台、晚会和电视台场景。",
            "span": "约 3.3 米",
            "payload": "",
            "prices": {"标准版": "¥748,000", "专业版": "¥758,000", "旗舰版": "¥818,000", "广播版": "¥1,318,000"},
        },
    ],
    "packages": [
        {
            "id": "film_pro",
            "name": "影视版",
            "scenario": "自媒体工作室 / TVC / 影视拍摄",
            "default_arm": "GRA",
            "alternative_arms": ["MINI", "PRO", "EXT"],
            "price_version": "专业版",
            "required_options": ["os_pro", "three_way_quick_release", "operation_handle", "fiz_focus"],
            "recommended_options": ["video_capture", "flange_quick_release", "training"],
            "description": "普通 U-MOCO OS Pro 加三向快换、U-MOCO 操作手柄、跟焦电机/跟焦系统等基础拍摄配置。",
        },
        {
            "id": "broadcast",
            "name": "广播版",
            "scenario": "电视台 / 晚会 / 广电演播室",
            "default_arm": "EXT",
            "alternative_arms": ["PRO", "GRA"],
            "price_version": "广播版",
            "required_options": ["os_pro", "channel_camera_hub", "timecode_sync", "freed_xr", "channel_linkage", "broadcast_handle", "broadcast_cage"],
            "recommended_options": ["dmx_control", "hub", "training"],
            "description": "面向广播电视台需求，增加讯道机、虚拟拍摄、timecode 帧同步、FreeD、讯道机联动控制、广播版遥控手柄和广播版兔笼等软硬件。",
        },
        {
            "id": "group_live",
            "name": "团播版",
            "scenario": "团播 / 直播间 / 电商直播",
            "default_arm": "GRA",
            "alternative_arms": ["EXT", "PRO"],
            "excluded_arms": ["AIR", "MINI"],
            "price_version": "专业版",
            "required_options": ["os_pro", "three_way_quick_release", "operation_handle", "fiz_focus", "umoco_live", "stream_deck"],
            "recommended_options": ["dmx_control", "training"],
            "description": "在影视版基础上增加 U-MOCO Live。团播现场可直接打开 U-MOCO Live，用 Stream Deck/可编程键盘一键控制机械臂运镜、镜头变焦和灯光联动；新运镜用 U-MOCO OS Pro 打点后导出给 U-MOCO Live。",
        },
    ],
    "options": [
        {"id": "os_pro", "name": "U-MOCO OS Pro", "category": "software", "unit": "套", "reference_price": "¥28,000", "description": "机械臂专业版控制与运镜设计软件。"},
        {"id": "os_pro_install", "name": "U-MOCO OS Pro 首次安装", "category": "service", "unit": "项", "reference_price": "¥28,000", "description": "专业版首次安装部署。"},
        {"id": "umoco_live", "name": "U-MOCO Live", "category": "software", "unit": "套", "reference_price": "需按最终配置核算", "description": "团播一键运镜、变焦、灯光联动控制软件。"},
        {"id": "stream_deck", "name": "Stream Deck / 直播可编程键盘", "category": "control", "unit": "套", "reference_price": "¥10,000", "description": "团播现场按键控制运镜、变焦、灯光联动。"},
        {"id": "operation_handle", "name": "U-MOCO 操作手柄", "category": "control", "unit": "套", "reference_price": "¥12,500", "description": "现场基础操作控制。"},
        {"id": "three_way_quick_release", "name": "三向快装快拆套件", "category": "mount", "unit": "套", "reference_price": "¥9,900", "description": "影视/TVC 基础快装配置。"},
        {"id": "fiz_focus", "name": "FIZ / 自动跟焦系统", "category": "lens", "unit": "套", "reference_price": "¥19,800", "description": "跟焦、变焦、光圈控制。"},
        {"id": "focus_motor", "name": "电动跟焦器套件", "category": "lens", "unit": "套", "reference_price": "¥12,000", "description": "跟焦电机套件。"},
        {"id": "dmx_control", "name": "DMX 灯光联动 / 控台适配", "category": "lighting", "unit": "套", "reference_price": "¥15,800", "description": "灯光控台联动，需确认现场品牌与协议。"},
        {"id": "film_track", "name": "影视地面轨道", "category": "track", "unit": "米", "reference_price": "¥15,500/米", "description": "仅在客户需要横移、走位、全景/环绕或明确轨道长度时添加。"},
        {"id": "track_motor", "name": "轨道电机", "category": "track", "unit": "套", "reference_price": "¥78,000", "description": "机械臂上轨道时的轨道电机驱动。"},
        {"id": "freed_xr", "name": "XR 虚拟制作 FreeD 协议", "category": "xr", "unit": "套", "reference_price": "¥25,800", "description": "FreeD/XR/虚拟拍摄跟踪协议。"},
        {"id": "timecode_sync", "name": "XR Genlock / Timecode 帧同步模块", "category": "xr", "unit": "套", "reference_price": "¥26,500", "description": "广播/虚拟制作帧同步。"},
        {"id": "channel_camera_hub", "name": "讯道系统集成中枢", "category": "broadcast", "unit": "套", "reference_price": "需按最终配置核算", "description": "广播电视台讯道系统集成。"},
        {"id": "channel_linkage", "name": "讯道机联动控制", "category": "broadcast", "unit": "套", "reference_price": "需按最终配置核算", "description": "与讯道机控制链路联动。"},
        {"id": "broadcast_handle", "name": "广播版遥控手柄", "category": "broadcast", "unit": "套", "reference_price": "需按最终配置核算", "description": "广电级现场控制手柄。"},
        {"id": "broadcast_cage", "name": "广播版兔笼", "category": "broadcast", "unit": "套", "reference_price": "需按最终配置核算", "description": "广播版挂载兔笼。"},
        {"id": "rabbit_cage", "name": "可升降挂载兔笼", "category": "mount", "unit": "套", "reference_price": "¥15,800", "description": "可升降挂载附件。"},
        {"id": "video_capture", "name": "视频信号采集卡（SDI+HDMI）", "category": "video", "unit": "张", "reference_price": "¥1,200", "description": "视频信号采集。"},
        {"id": "flange_quick_release", "name": "法兰转接 + 快拆套装", "category": "mount", "unit": "套", "reference_price": "¥2,300", "description": "基础转接快拆。"},
        {"id": "hub", "name": "多功能接口集线器", "category": "accessory", "unit": "套", "reference_price": "¥25,800", "description": "多接口扩展。"},
        {"id": "training", "name": "上门部署培训", "category": "service", "unit": "项", "reference_price": "需按交付地与排期核算", "description": "安装、按键映射、运镜交付与培训。"},
    ],
    "rules": {
        "manual_review": ["优惠价", "低于标价", "交付时间", "合同条款", "特殊定制", "现场适配", "客户预算不足"],
        "scene_keywords": {
            "group_live": ["团播", "多人直播", "直播间", "电商直播", "带货", "主播", "Stream Deck", "steamdeck", "一键"],
            "broadcast": ["电视台", "广播", "广电", "晚会", "演播室", "讯道", "timecode", "Genlock"],
            "film_pro": ["影视", "TVC", "tvc", "广告", "自媒体", "工作室", "拍摄", "宣传片"],
        },
        "track_keywords": ["轨道", "横移", "推拉", "走位", "全景", "环绕", "空间调度"],
        "track_negative_patterns": ["不需要轨道", "不用轨道", "不要轨道", "暂不考虑轨道", "不确定轨道", "是否需要轨道"],
        "group_live_start_arm": "GRA",
        "group_live_upgrade_arms": ["EXT", "PRO"],
        "group_live_excluded_arms": ["AIR", "MINI"],
    },
    "updated_at": "",
}


class QuoteCatalogService:
    def __init__(self, store: JsonFileRepository):
        self.store = store

    def get(self) -> dict[str, Any]:
        saved = self.store.load_object()
        if saved:
            return self._with_defaults(saved)
        return copy.deepcopy(DEFAULT_QUOTE_CATALOG)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        catalog = self._with_defaults(payload)
        validation = self.validate(catalog)
        if validation["errors"]:
            raise ValueError("；".join(validation["errors"]))
        catalog["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.store.save_object(catalog)
        return catalog

    def validate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        catalog = self._with_defaults(payload or self.get())
        errors: list[str] = []
        warnings: list[str] = []
        arm_ids = {str(item.get("id", "")).upper() for item in catalog.get("arms", []) if item.get("id")}
        option_ids = {str(item.get("id", "")) for item in catalog.get("options", []) if item.get("id")}
        if not arm_ids:
            errors.append("至少需要配置一个臂型")
        if not catalog.get("packages"):
            errors.append("至少需要配置一个版本包")
        for package in catalog.get("packages", []):
            package_name = package.get("name") or package.get("id") or "未命名版本包"
            default_arm = str(package.get("default_arm", "")).upper()
            if default_arm and default_arm not in arm_ids:
                errors.append(f"{package_name} 的默认臂型不存在：{default_arm}")
            for arm_id in package.get("alternative_arms", []) or []:
                if str(arm_id).upper() not in arm_ids:
                    warnings.append(f"{package_name} 的备选臂型不存在：{arm_id}")
            for option_id in (package.get("required_options", []) or []) + (package.get("recommended_options", []) or []):
                if str(option_id) not in option_ids:
                    warnings.append(f"{package_name} 引用了不存在的选配：{option_id}")
        return {"ok": not errors, "errors": errors, "warnings": warnings}

    def scene_for(self, text: str, scenario: str = "") -> str:
        source = f"{scenario} {text}"
        lowered = source.lower()
        rules = self.get().get("rules", {})
        keywords = rules.get("scene_keywords", {})
        if any(word in source for word in ("影视版", "影视版本", "影视场景", "TVC版", "广告版")):
            return "film_pro"
        for scene_id in ("group_live", "broadcast", "film_pro"):
            for word in keywords.get(scene_id, []):
                if str(word).lower() in lowered:
                    return scene_id
        if scenario in {"live_commerce", "group_live"}:
            return "group_live"
        return "film_pro"

    def package_for(self, scene_id: str) -> dict[str, Any]:
        catalog = self.get()
        for item in catalog.get("packages", []):
            if item.get("id") == scene_id:
                return item
        return (catalog.get("packages") or [{}])[0]

    def arm_for(self, arm_id: str) -> dict[str, Any]:
        arm_id = str(arm_id or "").upper()
        for item in self.get().get("arms", []):
            if str(item.get("id", "")).upper() == arm_id:
                return item
        return {}

    def option_for(self, option_id: str) -> dict[str, Any]:
        option_id = str(option_id or "")
        for item in self.get().get("options", []):
            if str(item.get("id", "")) == option_id:
                return item
        return {}

    def recommend_arm(self, text: str, package: dict[str, Any], needs: dict[str, Any]) -> dict[str, Any]:
        explicit = [token.upper() for token in needs.get("explicit_products", []) or []]
        excluded = {str(item).upper() for item in package.get("excluded_arms", []) or []}
        for token in explicit:
            if token not in excluded:
                arm = self.arm_for(token)
                if arm:
                    return arm
        budget = float(needs.get("budget_value") or 0)
        if package.get("id") == "group_live":
            if any(word in text for word in ("大空间", "大场地", "大直播间", "臂展", "大范围")):
                return self.arm_for("EXT") or self.arm_for(package.get("default_arm", "GRA"))
            if any(word in text for word in ("高负载", "重相机", "电影机", "重镜头", "专业拍摄")) or budget >= 700000:
                return self.arm_for("PRO") or self.arm_for(package.get("default_arm", "GRA"))
            return self.arm_for(package.get("default_arm", "GRA"))
        if package.get("id") == "broadcast":
            if "GRA" in explicit:
                return self.arm_for("GRA")
            if "PRO" in explicit:
                return self.arm_for("PRO")
            return self.arm_for(package.get("default_arm", "EXT"))
        if budget and budget <= 350000:
            return self.arm_for("MINI") or self.arm_for(package.get("default_arm", "GRA"))
        if any(word in text for word in ("高负载", "电影机", "重镜头", "TVC", "tvc")):
            return self.arm_for("PRO") or self.arm_for(package.get("default_arm", "GRA"))
        return self.arm_for(package.get("default_arm", "GRA"))

    def needs_track(self, text: str, needs: dict[str, Any]) -> bool:
        if needs.get("track_length"):
            return True
        for pattern in self.get().get("rules", {}).get("track_negative_patterns", []):
            if pattern and pattern in text:
                return False
        if re.search(r"(需要|希望|想要|要|加|上|配|配置|增加|安装).{0,8}轨道", text):
            return True
        return any(word in text for word in self.get().get("rules", {}).get("track_keywords", []))

    def quote_price_for_arm(self, arm: dict[str, Any], package: dict[str, Any]) -> str:
        prices = arm.get("prices") if isinstance(arm.get("prices"), dict) else {}
        version = package.get("price_version", "")
        return str(prices.get(version) or prices.get("专业版") or prices.get("标准版") or "")

    def alternatives_for(self, package: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for arm_id in package.get("alternative_arms", []) or []:
            arm = self.arm_for(arm_id)
            if not arm:
                continue
            rows.append({
                "id": arm.get("id", ""),
                "name": arm.get("name", ""),
                "reference_price": self.quote_price_for_arm(arm, package),
                "description": arm.get("description", ""),
            })
        return rows

    @staticmethod
    def _with_defaults(payload: dict[str, Any]) -> dict[str, Any]:
        catalog = copy.deepcopy(DEFAULT_QUOTE_CATALOG)
        if not isinstance(payload, dict):
            return catalog
        for key in ("version", "currency", "updated_at"):
            if payload.get(key) not in (None, ""):
                catalog[key] = payload[key]
        for key in ("arms", "packages", "options"):
            if isinstance(payload.get(key), list):
                catalog[key] = payload[key]
        if isinstance(payload.get("rules"), dict):
            merged_rules = copy.deepcopy(catalog["rules"])
            merged_rules.update(payload["rules"])
            catalog["rules"] = merged_rules
        return catalog
