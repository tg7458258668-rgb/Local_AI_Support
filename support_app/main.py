from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from support_app.api.v1.admin import router as admin_router
from support_app.api.v1.chat import router as chat_router
from support_app.api.v1.health import router as health_router
from support_app.api.v1.integrations import router as integrations_router
from support_app.api.legacy_admin import router as legacy_admin_router
from support_app.api.system import router as system_router
from support_app.dependencies import get_chat_service
from support_app.schemas import ChatRequest, LegacyAskRequest
from support_app.web_pages import router as web_router
from support_app.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local AI Support - Refactored",
        version="2.2.0",
        description="Maintainable API-first local AI customer support service.",
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(legacy_admin_router)
    app.include_router(system_router)
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory=str(settings.base_dir / "app" / "static")), name="static")

    @app.middleware("http")
    async def request_log_middleware(request, call_next):
        start = datetime.now()
        response = await call_next(request)
        runtime_dir = settings.base_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        line = (
            f"{start.strftime('%Y-%m-%d %H:%M:%S')} "
            f"{request.method} {request.url.path} -> {response.status_code}\n"
        )
        with open(runtime_dir / "requests.log", "a", encoding="utf-8") as f:
            f.write(line)
        return response

    @app.post("/ask")
    def legacy_ask(req: LegacyAskRequest):
        response = get_chat_service().answer(ChatRequest(message=req.question, channel="api"))
        data = response.model_dump()
        data["elapsed_ms"] = response.timings.total_ms
        data["timings"]["rag_total_ms"] = response.timings.total_ms
        return data

    return app


app = create_app()
