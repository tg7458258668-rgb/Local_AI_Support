def build_faq_prompt(user_query: str, hits, memory_context: str = "") -> str:
    context_parts = []
    for i, hit in enumerate(hits, start=1):
        payload = hit.payload or {}
        context_parts.append(
            f"[FAQ资料{i}] 来源:{payload.get('source','')}\n"
            f"问题:{payload.get('question','')}\n"
            f"答案:{payload.get('answer','')}\n"
            f"类别:{payload.get('category','')}"
        )

    context = "\n\n".join(context_parts)
    return f"""
你是公司客服助手。你必须严格基于提供的FAQ规则内容回答。
如果涉及报价、合同、定制、特殊售后、退款、赔偿、交期、商务承诺等敏感问题，
必须明确提示“建议人工进一步确认”，不要替公司做承诺。

要求：
1. 回答简短、准确、礼貌。
2. 不要编造政策，不要编造价格，不要替公司签约或承诺。
3. 如果FAQ本身就是“需要人工确认”，请直接按FAQ语义明确回复。
4. 不要输出“根据FAQ资料1”这类机械表述。

用户问题：
{user_query}

{memory_context}

FAQ规则资料：
{context}
"""


def build_docs_prompt(user_query: str, hits, memory_context: str = "") -> str:
    context_parts = []
    for i, hit in enumerate(hits, start=1):
        payload = hit.payload or {}
        context_parts.append(
            f"[文档资料{i}] 文档:{payload.get('doc_name','')}\n"
            f"章节:{payload.get('section','')}\n"
            f"来源:{payload.get('source','')}\n"
            f"内容:{payload.get('text','')}"
        )

    context = "\n\n".join(context_parts)
    return f"""
你是公司客服助手。你只能根据提供的文档资料回答。

要求：
1. 用自然、简洁、客服化的中文回答。
2. 不要写“根据文档资料1”“依据资料2”“文档资料3显示”等机械表述。
3. 可以直接说结论，例如“电池保修期为3个月”。
4. 只有在确实需要补充说明时，才自然补一句“如涉及特殊情况，建议人工进一步确认”。
5. 不要编造文档中没有的信息。
6. 如果资料不足以明确回答，请直接说：
“我暂时无法根据现有文档确认，建议人工进一步确认。”

用户问题：
{user_query}

{memory_context}

文档资料：
{context}
"""


def build_handoff_answer(user_query: str, matched_rule: dict | None) -> str:
    rule_name = matched_rule.get("rule_name", "") if matched_rule else ""
    if "合同" in user_query or "合同" in rule_name:
        return "涉及合同、协议或正式签约事项时，需要由人工同事进一步确认，我这边不能直接替公司确认或签订。"
    if "报价" in user_query or "价格" in user_query or "报价" in rule_name:
        return "涉及精准报价、商务条款或正式价格承诺时，需要由人工同事进一步确认，我这边先提供通用说明。"
    if "定制" in user_query or "定制" in rule_name:
        return "涉及定制方案或特殊需求时，需要由人工销售或技术同事进一步确认，我这边先提供通用说明。"
    return "这个问题涉及需要人工确认的事项，建议由人工同事进一步确认。"
