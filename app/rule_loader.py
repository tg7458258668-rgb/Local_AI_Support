import csv
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_CSV = BASE_DIR / "data" / "faq_priority_rules.csv"


ACTION_LABELS = {
    "faq_first": "优先FAQ",
    "manual_required": "必须转人工",
    "doc_first": "优先文档",
    "block_commitment": "禁止承诺",
}


STATUS_LABELS = {
    "active": "已启用",
    "inactive": "未启动",
}


def normalize_text(value: str) -> str:
    return (value or "").strip()


def normalize_status(value: str) -> str:
    raw = normalize_text(value).lower()
    return "inactive" if raw == "inactive" else "active"


def normalize_action(value: str) -> str:
    raw = normalize_text(value).lower()
    if raw in {"faq_first", "manual_required", "doc_first", "block_commitment"}:
        return raw
    return "faq_first"


def normalize_priority(value) -> int:
    try:
        return max(1, int(str(value).strip() or "1"))
    except Exception:
        return 999


def split_keywords(raw_keywords: str) -> list[str]:
    """
    兼容以下几种写法：
    1. 关键词1|关键词2|关键词3
    2. 关键词1,关键词2,关键词3
    3. 关键词1，关键词2，关键词3
    4. 一行一个关键词
    """
    raw = normalize_text(raw_keywords)
    if not raw:
        return []

    parts = re.split(r"[|\n,，]+", raw)
    result = []
    seen = set()

    for item in parts:
        kw = normalize_text(item).lower()
        if not kw:
            continue
        if kw in seen:
            continue
        seen.add(kw)
        result.append(kw)

    return result


def build_rule_item(row: dict) -> dict:
    status = normalize_status(row.get("status", "active"))
    action = normalize_action(row.get("action", "faq_first"))
    priority = normalize_priority(row.get("priority", 1))
    keywords = split_keywords(row.get("keywords", ""))

    return {
        "id": normalize_text(row.get("id", "")),
        "rule_name": normalize_text(row.get("rule_name", "")),
        "keywords": keywords,
        "keywords_text": normalize_text(row.get("keywords", "")),
        "category": normalize_text(row.get("category", "")),
        "priority": priority,
        "status": status,
        "status_text": STATUS_LABELS.get(status, "已启用"),
        "action": action,
        "action_text": ACTION_LABELS.get(action, "优先FAQ"),
        "note": normalize_text(row.get("note", "")),
        "updated_at": normalize_text(row.get("updated_at", "")),
    }


def load_priority_rules(include_inactive: bool = False) -> list[dict]:
    rules = []

    if not RULES_CSV.exists():
        return rules

    with open(RULES_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rule = build_rule_item(row)

            if not rule["id"] or not rule["rule_name"]:
                continue

            if not include_inactive and rule["status"] != "active":
                continue

            rules.append(rule)

    rules.sort(key=lambda x: (x["priority"], x["id"]))
    return rules


def match_priority_rule(user_query: str):
    text = normalize_text(user_query).lower()
    if not text:
        return None

    rules = load_priority_rules(include_inactive=False)

    for rule in rules:
        for kw in rule["keywords"]:
            if kw and kw in text:
                matched = dict(rule)
                matched["matched_keyword"] = kw
                return matched

    return None