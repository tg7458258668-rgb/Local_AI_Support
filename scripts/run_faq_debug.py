# test_faq_debug.py
import os
from app.faq_manager import search_faq, _obj_get, _extract_score, _extract_question, _extract_answer, _extract_rule_from_hit, FAQ_SCORE_THRESHOLD

# 测试问题列表
test_questions = [
    "报价问题？",
    "合同问题？",
    "客户问价格能不能直接报？",
    "不存在的问题？",
]

# 打印 Markdown 表格头
print("# FAQ 模块复测结果\n")
print("| 序号 | 测试问题 | 候选数量 | raw_score | normalized_score | matched_question | answer | score | matched_rule | 阈值过滤生效 | 备注 |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")

for idx, q in enumerate(test_questions, start=1):
    # 调用 search_faq 获取最终结果
    result = search_faq(q)
    
    # 调试打印，获取候选数量和 raw_scores
    # 因为 faq_hits 是内部私有数据，我们用 _debug_print 的逻辑简化版
    try:
        from rag import search_faq_rules, match_priority_rule
        matched_rule = match_priority_rule(q) or "无"
        faq_hits = search_faq_rules(q) or []
        candidate_count = len(faq_hits)
        raw_scores = [_obj_get(hit, "score", 0.0) for hit in faq_hits]
        max_raw_score = max(raw_scores) if raw_scores else 0.0
    except Exception:
        candidate_count = 0
        max_raw_score = 0.0
        matched_rule = "无"

    # 阈值过滤生效判断
    threshold_pass = "✅" if result["score"] >= FAQ_SCORE_THRESHOLD else "❌"

    print(f"| {idx} | {q} | {candidate_count} | {round(max_raw_score, 4)} | {round(result['score'], 3)} | {result['matched_question']} | {result['answer']} | {result['score']} | {result['matched_rule']} | {threshold_pass} |  |")