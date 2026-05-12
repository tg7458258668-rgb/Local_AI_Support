from typing import Any

import requests

from support_app.settings import Settings


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def list_models(self) -> list[dict[str, Any]]:
        resp = requests.get(f"{self.settings.ollama_url}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        items = []
        for item in models:
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            items.append({
                "name": name,
                "size": item.get("size", 0),
                "modified_at": item.get("modified_at", ""),
                "details": item.get("details", {}),
            })
        return sorted(items, key=lambda x: x["name"])

    def current_chat_model(self) -> str:
        return self._model_settings().get("chat_model") or self.settings.chat_model

    def current_embed_model(self) -> str:
        return self._model_settings().get("embed_model") or self.settings.embed_model

    def embedding(self, text: str, model: str | None = None) -> list[float]:
        model_name = model or self.current_embed_model()
        resp = requests.post(
            f"{self.settings.ollama_url}/api/embeddings",
            json={"model": model_name, "prompt": text},
            timeout=120,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "embedding" not in data:
            raise RuntimeError(f"embedding接口返回异常: {data}")
        return data["embedding"]

    def generate(self, prompt: str, model: str | None = None) -> str:
        model_name = model or self.current_chat_model()
        resp = requests.post(
            f"{self.settings.ollama_url}/api/generate",
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    def _model_settings(self) -> dict[str, Any]:
        path = self.settings.data_dir / "model_settings.json"
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
