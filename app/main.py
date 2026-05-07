from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from rag import answer_question
from rule_loader import load_priority_rules, match_priority_rule
from ingest import sync_faq_vectors

import json
import csv
import time
from datetime import datetime
from pathlib import Path
import requests

app = FastAPI(title="Local AI Customer Service MVP")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_CHUNKS_PATH = DATA_DIR / "docs_chunks" / "docs_chunks.json"
FAQ_PATH = DATA_DIR / "faq.json"
RULES_PATH = DATA_DIR / "faq_priority_rules.csv"
CATEGORY_OPTIONS_PATH = DATA_DIR / "category_options.json"
LOG_DIR = DATA_DIR / "logs"


class AskRequest(BaseModel):
    question: str


class FAQItemPayload(BaseModel):
    id: str | None = None
    questions: list[str] = Field(default_factory=list)
    answer: str = ""
    category: str = ""
    source: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "active"
    priority: int = 1


class RuleItemPayload(BaseModel):
    id: str | None = None
    rule_name: str = ""
    keywords: list[str] = Field(default_factory=list)
    category: str = ""
    priority: int = 1
    status: str = "active"
    action: str = "faq_first"
    note: str = ""


class RuleTestPayload(BaseModel):
    text: str


class CategoryPayload(BaseModel):
    name: str


class RuleItemPayload(BaseModel):
    id: str | None = None
    rule_name: str = ""
    keywords: list[str] = Field(default_factory=list)
    category: str = ""
    priority: int = 1
    status: str = "active"
    action: str = "faq_first"
    note: str = ""


class RuleTestPayload(BaseModel):
    text: str
class CategoryPayload(BaseModel):
    name: str

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={}
    )


@app.get("/admin")
def admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={}
    )


@app.post("/ask")
def ask(req: AskRequest):
    start = time.perf_counter()

    result = answer_question(req.question)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

    if isinstance(result, dict):
        result["elapsed_ms"] = elapsed_ms
    else:
        result = {
            "answer": str(result),
            "elapsed_ms": elapsed_ms
        }

    return result


def load_json_list(path: Path):
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def save_json_list(path: Path, items: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def normalize_category_name(value: str):
    return str(value or "").strip()


def load_category_names():
    names = []

    if CATEGORY_OPTIONS_PATH.exists():
        try:
            with open(CATEGORY_OPTIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_items = data.get("items", []) if isinstance(data, dict) else []
            seen = set()

            for item in raw_items:
                name = normalize_category_name(item)
                if not name:
                    continue
                low = name.lower()
                if low in seen:
                    continue
                seen.add(low)
                names.append(name)
        except Exception:
            names = []

    if not names:
        seen = set()

        for item in load_json_list(FAQ_PATH):
            name = normalize_category_name(item.get("category", ""))
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)

        for item in load_rule_items_for_admin():
            name = normalize_category_name(item.get("category", ""))
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)

    return names


def save_category_names(items: list[str]):
    seen = set()
    cleaned = []

    for item in items:
        name = normalize_category_name(item)
        if not name:
            continue
        low = name.lower()
        if low in seen:
            continue
        seen.add(low)
        cleaned.append(name)

    CATEGORY_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATEGORY_OPTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({"items": cleaned}, f, ensure_ascii=False, indent=2)


def build_category_usage_items():
    names = load_category_names()
    faq_count_map = {}
    rule_count_map = {}

    for item in load_json_list(FAQ_PATH):
        name = normalize_category_name(item.get("category", ""))
        if not name:
            continue
        faq_count_map[name] = faq_count_map.get(name, 0) + 1
        if name not in names:
            names.append(name)

    for item in load_rule_items_for_admin():
        name = normalize_category_name(item.get("category", ""))
        if not name:
            continue
        rule_count_map[name] = rule_count_map.get(name, 0) + 1
        if name not in names:
            names.append(name)

    return [
        {
            "name": name,
            "faq_count": faq_count_map.get(name, 0),
            "rule_count": rule_count_map.get(name, 0),
        }
        for name in names
    ]

def load_csv_list(path: Path):
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def check_ollama():
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            return "online"
        return "offline"
    except Exception:
        return "offline"


def check_qdrant():
    try:
        resp = requests.get("http://localhost:6333/collections", timeout=2)
        if resp.status_code == 200:
            return "online"
        return "offline"
    except Exception:
        return "offline"


def read_latest_log():
    if not LOG_DIR.exists():
        return "暂无日志文件"

    files = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "暂无日志文件"

    latest = files[0]
    try:
        text = latest.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        return "\n".join(lines[-80:]) if lines else "日志文件为空"
    except Exception as e:
        return f"读取日志失败: {e}"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_faq_id(existing_items: list):
    max_num = 0
    for item in existing_items:
        raw_id = str(item.get("id", ""))
        if raw_id.startswith("faq_"):
            try:
                num = int(raw_id.split("_")[1])
                max_num = max(max_num, num)
            except Exception:
                pass
    return f"faq_{max_num + 1:03d}"


def normalize_faq_status(value: str):
    return "inactive" if str(value).strip().lower() == "inactive" else "active"


def normalize_priority(value):
    try:
        return max(1, int(value or 1))
    except Exception:
        return 1
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

ALLOWED_RULE_ACTIONS = {
    "faq_first",
    "manual_required",
    "doc_first",
    "block_commitment",
}


def normalize_rule_status(value: str):
    return "inactive" if str(value).strip().lower() == "inactive" else "active"


def normalize_rule_action(value: str):
    raw = str(value or "").strip().lower()
    return raw if raw in ALLOWED_RULE_ACTIONS else "faq_first"


def join_rule_keywords(values: list[str]):
    cleaned = []
    seen = set()

    for item in values:
        text = str(item or "").strip()
        if not text:
            continue

        low = text.lower()
        if low in seen:
            continue

        seen.add(low)
        cleaned.append(text)

    return "|".join(cleaned)


def next_rule_id(existing_items: list):
    max_num = 0
    for item in existing_items:
        raw_id = str(item.get("id", ""))
        if raw_id.startswith("rule_"):
            try:
                num = int(raw_id.split("_")[1])
                max_num = max(max_num, num)
            except Exception:
                pass
    return f"rule_{max_num + 1:03d}"


def sort_rule_items(items: list):
    return sorted(
        items,
        key=lambda x: (
            normalize_priority(x.get("priority", 999)),
            str(x.get("id", "")),
        ),
    )


def save_rule_items(items: list):
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RULES_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RULE_FIELDNAMES)
        writer.writeheader()

        for item in sort_rule_items(items):
            writer.writerow({
                "id": str(item.get("id", "")).strip(),
                "rule_name": str(item.get("rule_name", "")).strip(),
                "keywords": str(item.get("keywords", "")).strip(),
                "category": str(item.get("category", "")).strip(),
                "priority": normalize_priority(item.get("priority", 1)),
                "status": normalize_rule_status(item.get("status", "active")),
                "action": normalize_rule_action(item.get("action", "faq_first")),
                "note": str(item.get("note", "")).strip(),
                "updated_at": str(item.get("updated_at", "")).strip(),
            })


def load_rule_items_for_admin():
    return load_priority_rules(include_inactive=True)

def reindex_faq_or_raise():
    try:
        return sync_faq_vectors()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"FAQ 文件已保存，但 FAQ 向量同步失败：{type(e).__name__}: {str(e)}"
        )


@app.get("/api/admin/status")
def api_admin_status():
    return {
        "backend": "online",
        "ollama": check_ollama(),
        "qdrant": check_qdrant()
    }


@app.get("/api/admin/summary")
def api_admin_summary():
    docs = load_json_list(DOCS_CHUNKS_PATH)
    faqs = load_json_list(FAQ_PATH)
    rules = load_csv_list(RULES_PATH)

    doc_names = sorted({item.get("doc_name", "") for item in docs if item.get("doc_name")})

    return {
        "doc_chunk_count": len(docs),
        "doc_count": len(doc_names),
        "faq_count": len(faqs),
        "rule_count": len(rules),
        "doc_names": doc_names[:20]
    }


@app.get("/api/admin/docs")
def api_admin_docs(q: str = Query(default="")):
    docs = load_json_list(DOCS_CHUNKS_PATH)

    if q:
        keyword = q.strip().lower()
        docs = [
            item for item in docs
            if keyword in json.dumps(item, ensure_ascii=False).lower()
        ]

    return {
        "total": len(docs),
        "items": docs[:200]
    }


@app.get("/api/admin/faqs")
def api_admin_faqs(q: str = Query(default="")):
    faqs = load_json_list(FAQ_PATH)

    if q:
        keyword = q.strip().lower()
        filtered = []
        for item in faqs:
            haystack = json.dumps(item, ensure_ascii=False).lower()
            if keyword in haystack:
                filtered.append(item)
        faqs = filtered

    return {
        "total": len(faqs),
        "items": faqs[:200]
    }


@app.post("/api/admin/faqs")
def api_admin_create_faq(payload: FAQItemPayload):
    faqs = load_json_list(FAQ_PATH)

    questions = [q.strip() for q in payload.questions if q and q.strip()]
    tags = [t.strip() for t in payload.tags if t and t.strip()]

    if not questions:
        raise HTTPException(status_code=400, detail="questions 不能为空")
    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="answer 不能为空")

    new_item = {
        "id": next_faq_id(faqs),
        "questions": questions,
        "answer": payload.answer.strip(),
        "category": payload.category.strip(),
        "source": payload.source.strip(),
        "tags": tags,
        "status": normalize_faq_status(payload.status),
        "updated_at": now_str(),
        "priority": normalize_priority(payload.priority),
    }

    faqs.append(new_item)
    save_json_list(FAQ_PATH, faqs)

    reindex_info = reindex_faq_or_raise()

    return {
        "ok": True,
        "item": new_item,
        "total": len(faqs),
        "reindex": reindex_info
    }


@app.put("/api/admin/faqs/{faq_id}")
def api_admin_update_faq(faq_id: str, payload: FAQItemPayload):
    faqs = load_json_list(FAQ_PATH)

    index = -1
    for i, item in enumerate(faqs):
        if str(item.get("id")) == faq_id:
            index = i
            break

    if index < 0:
        raise HTTPException(status_code=404, detail="FAQ 不存在")

    questions = [q.strip() for q in payload.questions if q and q.strip()]
    tags = [t.strip() for t in payload.tags if t and t.strip()]

    if not questions:
        raise HTTPException(status_code=400, detail="questions 不能为空")
    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="answer 不能为空")

    current = faqs[index]
    updated_item = {
        "id": current.get("id", faq_id),
        "questions": questions,
        "answer": payload.answer.strip(),
        "category": payload.category.strip(),
        "source": payload.source.strip(),
        "tags": tags,
        "status": normalize_faq_status(payload.status),
        "updated_at": now_str(),
        "priority": normalize_priority(payload.priority),
    }

    faqs[index] = updated_item
    save_json_list(FAQ_PATH, faqs)

    reindex_info = reindex_faq_or_raise()

    return {
        "ok": True,
        "item": updated_item,
        "total": len(faqs),
        "reindex": reindex_info
    }


@app.delete("/api/admin/faqs/{faq_id}")
def api_admin_delete_faq(faq_id: str):
    faqs = load_json_list(FAQ_PATH)

    new_faqs = [item for item in faqs if str(item.get("id")) != faq_id]

    if len(new_faqs) == len(faqs):
        raise HTTPException(status_code=404, detail="FAQ 不存在")

    save_json_list(FAQ_PATH, new_faqs)

    reindex_info = reindex_faq_or_raise()

    return {
        "ok": True,
        "deleted_id": faq_id,
        "total": len(new_faqs),
        "reindex": reindex_info
    }


@app.post("/api/admin/faqs/reindex")
def api_admin_reindex_faqs():
    result = reindex_faq_or_raise()
    return {
        "ok": True,
        "reindex": result
    }


@app.get("/api/admin/rules")
def api_admin_rules(q: str = Query(default="")):
    rules = load_rule_items_for_admin()

    if q:
        keyword = q.strip().lower()
        rules = [
            item for item in rules
            if keyword in json.dumps(item, ensure_ascii=False).lower()
        ]

    return {
        "total": len(rules),
        "items": rules[:200]
    }


@app.post("/api/admin/rules")
def api_admin_create_rule(payload: RuleItemPayload):
    rules = load_rule_items_for_admin()

    rule_name = payload.rule_name.strip()
    keywords_list = [x.strip() for x in payload.keywords if x and x.strip()]
    keywords_text = join_rule_keywords(keywords_list)

    if not rule_name:
        raise HTTPException(status_code=400, detail="rule_name 不能为空")

    if not keywords_list:
        raise HTTPException(status_code=400, detail="keywords 不能为空")

    new_item = {
        "id": next_rule_id(rules),
        "rule_name": rule_name,
        "keywords": keywords_text,
        "category": payload.category.strip(),
        "priority": normalize_priority(payload.priority),
        "status": normalize_rule_status(payload.status),
        "action": normalize_rule_action(payload.action),
        "note": payload.note.strip(),
        "updated_at": now_str(),
    }

    rules.append(new_item)
    save_rule_items(rules)

    refreshed = load_rule_items_for_admin()
    created = next((x for x in refreshed if x.get("id") == new_item["id"]), None)

    return {
        "ok": True,
        "item": created,
        "total": len(refreshed),
        "reload": {
            "rule_count": len(refreshed)
        }
    }


@app.put("/api/admin/rules/{rule_id}")
def api_admin_update_rule(rule_id: str, payload: RuleItemPayload):
    rules = load_rule_items_for_admin()

    index = -1
    for i, item in enumerate(rules):
        if str(item.get("id")) == rule_id:
            index = i
            break

    if index < 0:
        raise HTTPException(status_code=404, detail="规则不存在")

    rule_name = payload.rule_name.strip()
    keywords_list = [x.strip() for x in payload.keywords if x and x.strip()]
    keywords_text = join_rule_keywords(keywords_list)

    if not rule_name:
        raise HTTPException(status_code=400, detail="rule_name 不能为空")

    if not keywords_list:
        raise HTTPException(status_code=400, detail="keywords 不能为空")

    current = rules[index]
    updated_item = {
        "id": current.get("id", rule_id),
        "rule_name": rule_name,
        "keywords": keywords_text,
        "category": payload.category.strip(),
        "priority": normalize_priority(payload.priority),
        "status": normalize_rule_status(payload.status),
        "action": normalize_rule_action(payload.action),
        "note": payload.note.strip(),
        "updated_at": now_str(),
    }

    rules[index] = updated_item
    save_rule_items(rules)

    refreshed = load_rule_items_for_admin()
    saved = next((x for x in refreshed if x.get("id") == rule_id), None)

    return {
        "ok": True,
        "item": saved,
        "total": len(refreshed),
        "reload": {
            "rule_count": len(refreshed)
        }
    }


@app.delete("/api/admin/rules/{rule_id}")
def api_admin_delete_rule(rule_id: str):
    rules = load_rule_items_for_admin()
    new_rules = [item for item in rules if str(item.get("id")) != rule_id]

    if len(new_rules) == len(rules):
        raise HTTPException(status_code=404, detail="规则不存在")

    save_rule_items(new_rules)
    refreshed = load_rule_items_for_admin()

    return {
        "ok": True,
        "deleted_id": rule_id,
        "total": len(refreshed),
        "reload": {
            "rule_count": len(refreshed)
        }
    }


@app.post("/api/admin/rules/reload")
def api_admin_reload_rules():
    rules = load_rule_items_for_admin()
    return {
        "ok": True,
        "reload": {
            "rule_count": len(rules)
        }
    }


@app.post("/api/admin/rules/test")
def api_admin_test_rules(payload: RuleTestPayload):
    text = payload.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    matched = match_priority_rule(text)

    return {
        "ok": True,
        "matched": bool(matched),
        "rule": matched
    }
@app.get("/api/admin/categories")
def api_admin_categories():
    items = build_category_usage_items()
    return {
        "total": len(items),
        "items": items
    }


@app.post("/api/admin/categories")
def api_admin_create_category(payload: CategoryPayload):
    name = normalize_category_name(payload.name)

    if not name:
        raise HTTPException(status_code=400, detail="分类名称不能为空")

    items = load_category_names()
    lower_set = {x.lower() for x in items}

    if name.lower() not in lower_set:
        items.append(name)
        save_category_names(items)

    refreshed = build_category_usage_items()

    return {
        "ok": True,
        "items": refreshed
    }


@app.delete("/api/admin/categories/{category_name}")
def api_admin_delete_category(category_name: str):
    target = normalize_category_name(category_name)
    items = load_category_names()

    matched_name = None
    for item in items:
        if item.lower() == target.lower():
            matched_name = item
            break

    if not matched_name:
        raise HTTPException(status_code=404, detail="分类不存在")

    usage_items = build_category_usage_items()
    usage = next((x for x in usage_items if x["name"].lower() == matched_name.lower()), None)

    faq_count = usage["faq_count"] if usage else 0
    rule_count = usage["rule_count"] if usage else 0

    if faq_count > 0 or rule_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该分类正在被 {faq_count} 条 FAQ、{rule_count} 条规则使用，不能删除"
        )

    new_items = [x for x in items if x.lower() != matched_name.lower()]
    save_category_names(new_items)

    refreshed = build_category_usage_items()

    return {
        "ok": True,
        "deleted_name": matched_name,
        "items": refreshed
    }