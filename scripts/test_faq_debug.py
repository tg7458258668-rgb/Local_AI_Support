# scripts/test_faq_debug.py
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.faq_manager import search_faq, _obj_get, _extract_score, _extract_question, _extract_answer, _extract_rule_from_hit, FAQ_SCORE_THRESHOLD
from rag import match_priority_rule, search_faq_rules

# 测试问题列表
test_questions = [
    "报价问题？",
    "合同问题？",
    "客户问价格能不能直接报？",
    "不存在的问题？",
]

# 输出 Markdown 表格
print("# FAQ 模块复测结果\n")
print("| 序号 | 测试问题 | 候选数量 | raw_score | normalized_score | matched_question | answer | score | matched_rule | 阈值过滤生效 | 备注 |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")

for idx, question in enumerate(test_questions, start=1):
    matched_rule = match_priority_rule(question) or "无"
    faq_hits = search_faq_rules(question) or []
    candidate_count = len(faq_hits)
    raw_scores = [_obj_get(hit, "score", 0.0) for hit in faq_hits]
    max_raw_score = max(raw_scores) if raw_scores else 0.0

    result = search_faq(question)
    threshold_pass = "✅" if result["score"] >= FAQ_SCORE_THRESHOLD else "❌"

    print(
        f"| {idx} | {question} | {candidate_count} | {round(max_raw_score,4)} | "
        f"{round(result['score'],3)} | {result['matched_question']} | {result['answer']} | "
        f"{result['score']} | {result['matched_rule']} | {threshold_pass} |  |"
    )