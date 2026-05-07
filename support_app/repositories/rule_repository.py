from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path


ACTION_LABELS = {
    "faq_first": "优先FAQ",
    "manual_required": "必须转人工",
    "doc_first": "优先文档",
    "block_commitment": "禁止承诺",
}

RULE_FIELDNAMES = [
    "id",
    "rule_name",
    "keywords",
    "category",
    "priority",
    "status",
    "action",
    "note",
    "updated_at",
]


class RuleRepository:
    def __init__(self, rules_path: Path):
        self.rules_path = rules_path

    def load(self, include_inactive: bool = False) -> list[dict]:
        if not self.rules_path.exists():
            return []

        rules = []
        with open(self.rules_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rule = self._build_rule(row)
                if not rule["id"] or not rule["rule_name"]:
                    continue
                if not include_inactive and rule["status"] != "active":
                    continue
                rules.append(rule)

        return sorted(rules, key=lambda item: (item["priority"], item["id"]))

    def match(self, user_query: str) -> dict | None:
        text = self._clean(user_query).lower()
        if not text:
            return None

        for rule in self.load(include_inactive=False):
            for kw in rule["keywords"]:
                if kw and kw in text:
                    matched = dict(rule)
                    matched["matched_keyword"] = kw
                    return matched
        return None

    def create(self, payload: dict) -> dict:
        rules = self.load(include_inactive=True)
        item = self._normalize_payload(payload)
        item["id"] = self._next_id(rules)
        item["updated_at"] = self._now()
        rules.append(item)
        self._save(rules)
        return self._find(item["id"])

    def update(self, rule_id: str, payload: dict) -> dict:
        rules = self.load(include_inactive=True)
        for index, rule in enumerate(rules):
            if str(rule.get("id")) == rule_id:
                item = self._normalize_payload(payload)
                item["id"] = rule_id
                item["updated_at"] = self._now()
                rules[index] = item
                self._save(rules)
                return self._find(rule_id)
        raise KeyError(f"规则不存在: {rule_id}")

    def delete(self, rule_id: str) -> None:
        rules = self.load(include_inactive=True)
        filtered = [rule for rule in rules if str(rule.get("id")) != rule_id]
        if len(filtered) == len(rules):
            raise KeyError(f"规则不存在: {rule_id}")
        self._save(filtered)

    def _build_rule(self, row: dict) -> dict:
        status = "inactive" if self._clean(row.get("status")).lower() == "inactive" else "active"
        action = self._clean(row.get("action")).lower()
        if action not in ACTION_LABELS:
            action = "faq_first"

        return {
            "id": self._clean(row.get("id")),
            "rule_name": self._clean(row.get("rule_name")),
            "keywords": self._split_keywords(row.get("keywords", "")),
            "keywords_text": self._clean(row.get("keywords", "")),
            "category": self._clean(row.get("category")),
            "priority": self._priority(row.get("priority")),
            "status": status,
            "action": action,
            "action_text": ACTION_LABELS.get(action, "优先FAQ"),
            "note": self._clean(row.get("note")),
            "updated_at": self._clean(row.get("updated_at")),
        }

    def _save(self, rules: list[dict]) -> None:
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rules_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=RULE_FIELDNAMES)
            writer.writeheader()
            for item in sorted(rules, key=lambda rule: (self._priority(rule.get("priority")), str(rule.get("id", "")))):
                writer.writerow({
                    "id": self._clean(item.get("id")),
                    "rule_name": self._clean(item.get("rule_name")),
                    "keywords": self._join_keywords(item.get("keywords", [])),
                    "category": self._clean(item.get("category")),
                    "priority": self._priority(item.get("priority")),
                    "status": "inactive" if self._clean(item.get("status")).lower() == "inactive" else "active",
                    "action": self._clean(item.get("action")) if self._clean(item.get("action")) in ACTION_LABELS else "faq_first",
                    "note": self._clean(item.get("note")),
                    "updated_at": self._clean(item.get("updated_at")),
                })

    def _normalize_payload(self, payload: dict) -> dict:
        rule_name = self._clean(payload.get("rule_name"))
        keywords = payload.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = self._split_keywords(keywords)
        keywords = [self._clean(item) for item in keywords if self._clean(item)]

        if not rule_name:
            raise ValueError("rule_name 不能为空")
        if not keywords:
            raise ValueError("keywords 不能为空")

        action = self._clean(payload.get("action")).lower()
        return {
            "rule_name": rule_name,
            "keywords": keywords,
            "category": self._clean(payload.get("category")),
            "priority": self._priority(payload.get("priority")),
            "status": "inactive" if self._clean(payload.get("status")).lower() == "inactive" else "active",
            "action": action if action in ACTION_LABELS else "faq_first",
            "note": self._clean(payload.get("note")),
        }

    def _find(self, rule_id: str) -> dict:
        for rule in self.load(include_inactive=True):
            if str(rule.get("id")) == rule_id:
                return rule
        raise KeyError(f"规则不存在: {rule_id}")

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def _split_keywords(cls, raw_keywords: object) -> list[str]:
        raw = cls._clean(raw_keywords)
        if not raw:
            return []

        parts = re.split(r"[|\n,，]+", raw)
        result = []
        seen = set()
        for item in parts:
            kw = cls._clean(item).strip("'\"[] ").lower()
            if not kw or kw in seen:
                continue
            seen.add(kw)
            result.append(kw)
        return result

    @staticmethod
    def _priority(value: object) -> int:
        try:
            return max(1, int(str(value).strip() or "1"))
        except Exception:
            return 999

    @staticmethod
    def _join_keywords(values: object) -> str:
        if isinstance(values, str):
            return values
        if not isinstance(values, list):
            return ""
        cleaned = []
        seen = set()
        for item in values:
            text = str(item or "").strip()
            if text and text.lower() not in seen:
                seen.add(text.lower())
                cleaned.append(text)
        return "|".join(cleaned)

    @staticmethod
    def _next_id(rules: list[dict]) -> str:
        max_num = 0
        for rule in rules:
            raw_id = str(rule.get("id", ""))
            if raw_id.startswith("rule_"):
                try:
                    max_num = max(max_num, int(raw_id.split("_")[1]))
                except Exception:
                    pass
        return f"rule_{max_num + 1:03d}"

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
