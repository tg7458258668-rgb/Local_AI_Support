# app/faq_manager.py

import os
from typing import Any, Dict, List, Optional, Tuple

from rag import match_priority_rule, search_faq_rules

# 统一按 0~1 阈值处理
FAQ_SCORE_THRESHOLD = float(os.getenv("FAQ_SCORE_THRESHOLD", "0.6"))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_score(raw_score: Any) -> float:
    """
    将分数统一归一化到 0~1
    - 如果原分数本身是 0~1，直接返回
    - 如果原分数像 60 / 80 / 100 这种，按百分制处理
    """
    score = _to_float(raw_score, 0.0)
    if score > 1:
        score = score / 100.0
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _obj_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    同时兼容 dict / pydantic object / 普通对象
    """
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    if hasattr(obj, key):
        return getattr(obj, key, default)

    return default


def _get_payload(hit: Any) -> Dict[str, Any]:
    """
    从命中结果中提取 payload
    兼容：
    - dict
    - Qdrant ScoredPoint
    """
    if hit is None:
        return {}

    if isinstance(hit, dict):
        payload = hit.get("payload")
        if isinstance(payload, dict):
            return payload
        return hit

    payload = getattr(hit, "payload", None)
    if isinstance(payload, dict):
        return payload

    # 兜底：如果对象可转 dict，可在这里继续扩展
    return {}


def _extract_score(hit: Any) -> float:
    return _normalize_score(_obj_get(hit, "score", 0.0))


def _first_non_empty(data: Dict[str, Any], keys: List[str], default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _extract_question(hit: Any) -> str:
    payload = _get_payload(hit)
    return _first_non_empty(
        payload,
        ["question", "matched_question", "title", "q"],
        "",
    )


def _extract_answer(hit: Any) -> str:
    payload = _get_payload(hit)
    return _first_non_empty(
        payload,
        ["answer", "content", "text", "a"],
        "",
    )


def _extract_metadata(hit: Any) -> Dict[str, Any]:
    payload = _get_payload(hit)

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return metadata

    # 有些数据可能不放在 metadata 下，做兼容回填
    fallback = {}
    for key in ("rule", "matched_rule", "category", "source"):
        if key in payload and payload.get(key) not in (None, ""):
            fallback[key] = payload.get(key)
    return fallback


def _extract_rule_from_hit(hit: Any) -> str:
    metadata = _extract_metadata(hit)
    for key in ("rule", "matched_rule", "category"):
        value = metadata.get(key)
        if value:
            return str(value)
    return "无"


def _rule_matches(hit: Any, matched_rule: str) -> bool:
    if not matched_rule or matched_rule == "无":
        return False

    metadata = _extract_metadata(hit)
    for key in ("rule", "matched_rule", "category"):
        value = metadata.get(key)
        if value and matched_rule in str(value):
            return True
    return False


def _pick_best_hit(
    faq_hits: List[Any],
    matched_rule: str,
) -> Optional[Tuple[Any, float]]:
    """
    先过滤阈值，再选命中规则的最高分；如果没有规则命中，再选整体最高分。
    返回: (best_hit, normalized_score)
    """
    valid_hits: List[Tuple[Any, float]] = []

    for hit in faq_hits or []:
        normalized_score = _extract_score(hit)
        if normalized_score >= FAQ_SCORE_THRESHOLD:
            valid_hits.append((hit, normalized_score))

    if not valid_hits:
        return None

    rule_hits = [(hit, score) for hit, score in valid_hits if _rule_matches(hit, matched_rule)]
    if rule_hits:
        return max(rule_hits, key=lambda item: item[1])

    return max(valid_hits, key=lambda item: item[1])


def search_faq(question: str) -> Dict[str, Any]:
    """
    输入：用户问题文本
    输出：
    {
        "matched_question": str,
        "answer": str,
        "score": float,         # 统一返回 0~1
        "matched_rule": str
    }
    """
    question = (question or "").strip()
    if not question:
        return {
            "matched_question": "",
            "answer": "",
            "score": 0.0,
            "matched_rule": "无",
        }

    matched_rule = match_priority_rule(question) or "无"
    faq_hits = search_faq_rules(question) or []

    picked = _pick_best_hit(faq_hits, matched_rule)
    if not picked:
        return {
            "matched_question": "",
            "answer": "",
            "score": 0.0,
            "matched_rule": matched_rule,
        }

    best_hit, normalized_score = picked
    final_rule = matched_rule if matched_rule != "无" else _extract_rule_from_hit(best_hit)

    return {
        "matched_question": _extract_question(best_hit),
        "answer": _extract_answer(best_hit),
        "score": round(normalized_score, 3),
        "matched_rule": final_rule or "无",
    }


def _debug_print(question: str) -> None:
    """
    仅用于本地调试。
    """
    matched_rule = match_priority_rule(question) or "无"
    faq_hits = search_faq_rules(question) or []

    print("=" * 60)
    print("faq_manager debug v4")
    print(f"问题: {question}")
    print(f"阈值: {FAQ_SCORE_THRESHOLD}")
    print(f"规则命中: {matched_rule}")
    print(f"候选数量: {len(faq_hits)}")

    for idx, hit in enumerate(faq_hits[:10], start=1):
        raw_score = _obj_get(hit, "score", 0.0)
        normalized_score = _extract_score(hit)
        print(
            f"[{idx}] "
            f"question={_extract_question(hit)} | "
            f"raw_score={raw_score} | "
            f"normalized_score={round(normalized_score, 3)} | "
            f"rule={_extract_rule_from_hit(hit)}"
        )

    print("最终结果:", search_faq(question))
    print()


if __name__ == "__main__":
    test_questions = [
        "报价问题？",
        "合同问题？",
        "客户问价格能不能直接报？",
        "不存在的问题？",
    ]

    for q in test_questions:
        _debug_print(q)