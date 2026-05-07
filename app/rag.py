import time
import requests
from qdrant_client import QdrantClient
from config import (
    QDRANT_URL,
    FAQ_COLLECTION,
    DOC_COLLECTION,
    OLLAMA_URL,
    EMBED_MODEL,
    CHAT_MODEL,
    TOP_K_FAQ,
    TOP_K_DOC,
    FAQ_SCORE_THRESHOLD,
    DOC_SCORE_THRESHOLD,
)
from rule_loader import match_priority_rule

client = QdrantClient(url=QDRANT_URL)


def get_embedding(text: str):
    resp = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if "embedding" not in data:
        raise RuntimeError(f"embedding接口返回异常: {data}")
    return data["embedding"]


def search_collection(collection_name: str, query: str, limit: int):
    vec = get_embedding(query)
    result = client.query_points(
        collection_name=collection_name,
        query=vec,
        limit=limit,
    )
    return result.points


def search_faq_rules(query: str):
    return search_collection(FAQ_COLLECTION, query, TOP_K_FAQ)


def search_docs(query: str):
    return search_collection(DOC_COLLECTION, query, TOP_K_DOC)


def build_faq_prompt(user_query: str, hits):
    context_parts = []
    for i, h in enumerate(hits, start=1):
        p = h.payload or {}
        context_parts.append(
            f"[FAQ资料{i}] 来源:{p.get('source','')}\n"
            f"问题:{p.get('question','')}\n"
            f"答案:{p.get('answer','')}\n"
            f"类别:{p.get('category','')}"
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

FAQ规则资料：
{context}
"""


def build_docs_prompt(user_query: str, hits):
    context_parts = []
    for i, h in enumerate(hits, start=1):
        p = h.payload or {}
        context_parts.append(
            f"[文档资料{i}] 文档:{p.get('doc_name','')}\n"
            f"章节:{p.get('section','')}\n"
            f"来源:{p.get('source','')}\n"
            f"内容:{p.get('text','')}"
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

文档资料：
{context}
"""


def format_sources(hits, source_type: str):
    sources = []
    for h in hits:
        p = h.payload or {}
        if source_type == "faq":
            sources.append({
                "type": "faq",
                "question": p.get("question", ""),
                "source": p.get("source", ""),
                "category": p.get("category", ""),
                "score": getattr(h, "score", None),
            })
        else:
            sources.append({
                "type": "doc",
                "doc_name": p.get("doc_name", ""),
                "section": p.get("section", ""),
                "source": p.get("source", ""),
                "score": getattr(h, "score", None),
            })
    return sources


def answer_with_model(prompt: str):
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": CHAT_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def build_handoff_answer(user_query: str, matched_rule: dict | None):
    rule_name = matched_rule.get("rule_name", "") if matched_rule else ""
    if "合同" in user_query or "合同" in rule_name:
        return "涉及合同、协议或正式签约事项时，需要由人工同事进一步确认，我这边不能直接替公司确认或签订。"
    if "报价" in user_query or "价格" in user_query or "报价" in rule_name:
        return "涉及精准报价、商务条款或正式价格承诺时，需要由人工同事进一步确认，我这边先提供通用说明。"
    if "定制" in user_query or "定制" in rule_name:
        return "涉及定制方案或特殊需求时，需要由人工销售或技术同事进一步确认，我这边先提供通用说明。"
    return "这个问题涉及需要人工确认的事项，建议由人工同事进一步确认。"


def answer_question(user_query: str):
    rag_start = time.perf_counter()

    timings = {
        "rule_match_ms": 0,
        "faq_retrieval_ms": 0,
        "doc_retrieval_ms": 0,
        "route_decision_ms": 0,
        "answer_generation_ms": 0,
        "source_format_ms": 0,
        "rag_total_ms": 0,
    }

    faq_hits = []
    doc_hits = []
    matched_rule = None
    faq_top_score = 0
    doc_top_score = 0

    try:
        t = time.perf_counter()
        matched_rule = match_priority_rule(user_query)
        timings["rule_match_ms"] = round((time.perf_counter() - t) * 1000, 1)

        t = time.perf_counter()
        faq_hits = search_faq_rules(user_query)
        timings["faq_retrieval_ms"] = round((time.perf_counter() - t) * 1000, 1)

        t = time.perf_counter()
        doc_hits = search_docs(user_query)
        timings["doc_retrieval_ms"] = round((time.perf_counter() - t) * 1000, 1)

        faq_top_score = (getattr(faq_hits[0], "score", 0) or 0) if faq_hits else 0
        doc_top_score = (getattr(doc_hits[0], "score", 0) or 0) if doc_hits else 0

        t = time.perf_counter()

        route = "fallback"
        selected_hits = []
        selected_source_type = None
        prompt = None
        answer = ""
        sources = []
        need_human = False
        hint = "当前未触发人工接管提示"

        FAQ_DOC_MARGIN = 0.10

        # 1. 只要命中优先规则，就不要再让 DOC 抢路由
        if matched_rule:
            need_human = True
            hint = "本回答建议人工进一步确认"

            if faq_hits:
                route = "faq"
                selected_hits = faq_hits
                selected_source_type = "faq"
                prompt = build_faq_prompt(user_query, faq_hits)
            else:
                route = "handoff"
                answer = build_handoff_answer(user_query, matched_rule)
                sources = []

        # 2. FAQ 明显强于 DOC 时，优先走 FAQ
        elif (
            faq_hits
            and faq_top_score >= FAQ_SCORE_THRESHOLD
            and faq_top_score >= doc_top_score + FAQ_DOC_MARGIN
        ):
            route = "faq"
            selected_hits = faq_hits
            selected_source_type = "faq"
            prompt = build_faq_prompt(user_query, faq_hits)

        # 3. 文档库优先回答事实问题
        elif doc_hits and doc_top_score >= DOC_SCORE_THRESHOLD:
            route = "doc"
            selected_hits = doc_hits
            selected_source_type = "doc"
            prompt = build_docs_prompt(user_query, doc_hits)

        # 4. FAQ 兜底
        elif faq_hits and faq_top_score >= FAQ_SCORE_THRESHOLD:
            route = "faq"
            selected_hits = faq_hits
            selected_source_type = "faq"
            prompt = build_faq_prompt(user_query, faq_hits)

        timings["route_decision_ms"] = round((time.perf_counter() - t) * 1000, 1)

        if route in ("faq", "doc") and prompt:
            t = time.perf_counter()
            answer = answer_with_model(prompt)
            timings["answer_generation_ms"] = round((time.perf_counter() - t) * 1000, 1)

            t = time.perf_counter()
            sources = format_sources(selected_hits, selected_source_type)
            timings["source_format_ms"] = round((time.perf_counter() - t) * 1000, 1)

        elif route == "handoff":
            pass

        else:
            answer = "我暂时无法根据现有文档确认，建议人工进一步确认。"
            sources = []

        timings["rag_total_ms"] = round((time.perf_counter() - rag_start) * 1000, 1)

        return {
            "answer": answer,
            "sources": sources,
            "route": route,
            "matched_rule": matched_rule["rule_name"] if matched_rule else None,
            "faq_top_score": faq_top_score,
            "doc_top_score": doc_top_score,
            "need_human": need_human,
            "hint": hint,
            "timings": timings,
        }

    except Exception as e:
        timings["rag_total_ms"] = round((time.perf_counter() - rag_start) * 1000, 1)

        return {
            "answer": f"系统报错：{type(e).__name__}: {str(e)}",
            "sources": [],
            "route": "error",
            "matched_rule": matched_rule["rule_name"] if matched_rule else None,
            "faq_top_score": faq_top_score,
            "doc_top_score": doc_top_score,
            "need_human": True if matched_rule else False,
            "hint": "本回答建议人工进一步确认" if matched_rule else "系统异常",
            "timings": timings,
        }