import requests
from fastapi import APIRouter

from support_app.settings import settings

router = APIRouter(prefix="/health", tags=["health"])


def _check(url: str) -> str:
    try:
        resp = requests.get(url, timeout=2)
        return "online" if resp.status_code == 200 else "offline"
    except Exception:
        return "offline"


@router.get("")
def health():
    return {
        "backend": "online",
        "ollama": _check(f"{settings.ollama_url}/api/tags"),
        "qdrant": _check(f"{settings.qdrant_url}/collections"),
    }

