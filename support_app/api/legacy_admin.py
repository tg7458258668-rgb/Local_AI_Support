import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from support_app.dependencies import get_admin_service
from support_app.api.upload_utils import parse_upload_files_request
from support_app.schemas import CustomerMemoryItem, FAQItem, RuleItem
from support_app.services.admin_service import AdminService
from support_app.settings import settings

router = APIRouter(prefix="/api/admin", tags=["legacy-admin"])


def _handle_errors(fn):
    try:
        return fn()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _check(url: str) -> str:
    try:
        resp = requests.get(url, timeout=2)
        return "online" if resp.status_code == 200 else "offline"
    except Exception:
        return "offline"


@router.get("/status")
def status():
    return {
        "backend": "online",
        "ollama": _check(f"{settings.ollama_url}/api/tags"),
        "qdrant": _check(f"{settings.qdrant_url}/collections"),
        "base_dir": str(settings.base_dir),
        "log_path": str(settings.base_dir / "runtime" / "support_app.log"),
        "qdrant_storage_dir": str(settings.data_dir / "qdrant_storage"),
    }


@router.get("/summary")
def summary(service: AdminService = Depends(get_admin_service)):
    return service.summary()


@router.get("/docs")
def docs(q: str = Query(default=""), service: AdminService = Depends(get_admin_service)):
    return service.list_docs(q)


@router.post("/docs/upload")
async def upload_doc(
    request: Request,
    service: AdminService = Depends(get_admin_service),
):
    files, fields = await parse_upload_files_request(request)
    return service.upload_docs(files, fields.get("category", ""), fields.get("doc_name", ""))


@router.delete("/docs/{doc_name}")
def delete_doc(doc_name: str, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.delete_doc(doc_name))


@router.post("/docs/delete-batch")
def delete_docs(payload: dict, service: AdminService = Depends(get_admin_service)):
    doc_names = payload.get("doc_names", [])
    if not isinstance(doc_names, list):
        raise HTTPException(status_code=400, detail="doc_names 必须是数组")
    return _handle_errors(lambda: service.delete_docs(doc_names))


@router.get("/faqs")
def faqs(q: str = Query(default=""), service: AdminService = Depends(get_admin_service)):
    return service.list_faqs(q)


@router.post("/faqs")
def create_faq(payload: FAQItem, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.create_faq(payload))


@router.put("/faqs/{faq_id}")
def update_faq(faq_id: str, payload: FAQItem, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_faq(faq_id, payload))


@router.delete("/faqs/{faq_id}")
def delete_faq(faq_id: str, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.delete_faq(faq_id))


@router.post("/faqs/reindex")
def reindex_faqs(service: AdminService = Depends(get_admin_service)):
    return _handle_errors(service.reindex_faqs)


@router.get("/rules")
def rules(q: str = Query(default=""), service: AdminService = Depends(get_admin_service)):
    return service.list_rules(q)


@router.post("/rules")
def create_rule(payload: RuleItem, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.create_rule(payload))


@router.put("/rules/{rule_id}")
def update_rule(rule_id: str, payload: RuleItem, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_rule(rule_id, payload))


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.delete_rule(rule_id))


@router.post("/rules/reload")
def reload_rules(service: AdminService = Depends(get_admin_service)):
    return service.reload_rules()


@router.post("/rules/test")
def test_rule(payload: dict, service: AdminService = Depends(get_admin_service)):
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    return service.test_rule(text)


@router.get("/categories")
def categories(service: AdminService = Depends(get_admin_service)):
    return service.list_categories()


@router.post("/categories")
def create_category(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.create_category(str(payload.get("name", ""))))


@router.delete("/categories/{category_name}")
def delete_category(category_name: str, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.delete_category(category_name))


@router.get("/memories")
def memories(q: str = Query(default=""), service: AdminService = Depends(get_admin_service)):
    return service.list_memories(q)


@router.put("/memories/{channel}/{user_id}")
def update_memory(channel: str, user_id: str, payload: CustomerMemoryItem, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_memory(channel, user_id, payload))


@router.delete("/memories/{channel}/{user_id}")
def delete_memory(channel: str, user_id: str, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.delete_memory(channel, user_id))


@router.get("/learned-knowledge")
def learned_knowledge(q: str = Query(default=""), service: AdminService = Depends(get_admin_service)):
    return service.list_learned_knowledge(q)


@router.delete("/learned-knowledge/{learned_id}")
def delete_learned_knowledge(learned_id: str, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.delete_learned_knowledge(learned_id))


@router.post("/learned-knowledge/reindex")
def reindex_learned_knowledge(service: AdminService = Depends(get_admin_service)):
    return _handle_errors(service.reindex_learned_knowledge)


@router.get("/behavior-rules")
def behavior_rules(service: AdminService = Depends(get_admin_service)):
    return service.get_behavior_rules()


@router.put("/behavior-rules")
def update_behavior_rules(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_behavior_rules(payload))


@router.get("/answer-styles")
def answer_styles(service: AdminService = Depends(get_admin_service)):
    return service.get_answer_styles()


@router.put("/answer-styles")
def update_answer_styles(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_answer_styles(payload))


@router.post("/tuning/draft")
def tuning_draft(payload: dict, service: AdminService = Depends(get_admin_service)):
    instruction = str(payload.get("instruction", "") or "").strip()
    return _handle_errors(lambda: service.create_tuning_draft(instruction))


@router.post("/tuning/apply")
def tuning_apply(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.apply_tuning_draft(payload))


@router.get("/regression-cases")
def regression_cases(service: AdminService = Depends(get_admin_service)):
    return service.list_regression_cases()


@router.put("/regression-cases")
def update_regression_cases(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_regression_cases(payload))


@router.post("/regression-cases/run")
def run_regression_cases(payload: dict | None = None, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.run_regression_cases(payload or {}))


@router.get("/models")
def models(service: AdminService = Depends(get_admin_service)):
    return service.get_models()


@router.put("/models/chat")
def update_chat_model(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_chat_model(payload))


@router.put("/models/embed/rebuild")
def rebuild_embed_model(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.rebuild_embed_model(payload))


@router.get("/quote-policies")
def quote_policies(service: AdminService = Depends(get_admin_service)):
    return service.get_quote_policies()


@router.put("/quote-policies")
def update_quote_policies(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_quote_policies(payload))


@router.get("/pricing-catalog")
def pricing_catalog(service: AdminService = Depends(get_admin_service)):
    return service.get_pricing_catalog()


@router.put("/pricing-catalog")
def update_pricing_catalog(payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_pricing_catalog(payload))


@router.post("/pricing-catalog/rebuild-preview")
def rebuild_pricing_catalog_preview(service: AdminService = Depends(get_admin_service)):
    return _handle_errors(service.rebuild_pricing_catalog_preview)


@router.get("/quote-archives")
def quote_archives(q: str = Query(default=""), service: AdminService = Depends(get_admin_service)):
    return service.list_quote_archives(q)


@router.put("/quote-archives/{channel}/{user_id}/{quote_id}")
def update_quote_archive(channel: str, user_id: str, quote_id: str, payload: dict, service: AdminService = Depends(get_admin_service)):
    return _handle_errors(lambda: service.update_quote_archive(channel, user_id, quote_id, payload))


@router.get("/logs")
def logs():
    candidates = [
        settings.base_dir / "runtime" / "support_app.log",
        settings.base_dir / "runtime" / "requests.log",
    ]
    chunks = []
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()[-80:]
        if lines:
            chunks.append(f"== {path.name} ==\n" + "\n".join(lines))
    if not chunks:
        return {"text": "暂无运行日志。服务由终端直接启动时，启动日志会显示在当前终端窗口。"}
    return {"text": "\n\n".join(chunks)}
