from __future__ import annotations

from datetime import datetime
from typing import Any

from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.services.ollama_client import OllamaClient
from support_app.settings import Settings


class ModelSettingsService:
    def __init__(self, settings: Settings, store: JsonFileRepository, ollama: OllamaClient):
        self.settings = settings
        self.store = store
        self.ollama = ollama

    def get(self) -> dict[str, Any]:
        item = self.store.load_object()
        return {
            "chat_model": item.get("chat_model") or self.settings.chat_model,
            "embed_model": item.get("embed_model") or self.settings.embed_model,
            "embed_index_status": item.get("embed_index_status") or "not_rebuilt",
            "embed_index_message": item.get("embed_index_message") or "",
            "updated_at": item.get("updated_at") or "",
        }

    def installed_models(self) -> dict[str, Any]:
        try:
            models = self.ollama.list_models()
            return {"online": True, "models": models, "error": ""}
        except Exception as exc:
            return {"online": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}

    def overview(self) -> dict[str, Any]:
        installed = self.installed_models()
        return {
            "ok": True,
            "settings": self.get(),
            "ollama": installed,
        }

    def save_chat_model(self, model: str) -> dict[str, Any]:
        model = self._validate_installed_model(model)
        item = self.get()
        item["chat_model"] = model
        item["updated_at"] = self._now()
        self.store.save_object(item)
        return item

    def set_embed_rebuilding(self, model: str) -> dict[str, Any]:
        model = self._validate_installed_model(model)
        item = self.get()
        item["embed_model"] = model
        item["embed_index_status"] = "rebuilding"
        item["embed_index_message"] = "正在重建 FAQ 和文档向量库"
        item["updated_at"] = self._now()
        self.store.save_object(item)
        return item

    def mark_embed_result(self, status: str, message: str) -> dict[str, Any]:
        item = self.get()
        item["embed_index_status"] = status
        item["embed_index_message"] = message
        item["updated_at"] = self._now()
        self.store.save_object(item)
        return item

    def _validate_installed_model(self, model: str) -> str:
        model = str(model or "").strip()
        if not model:
            raise ValueError("模型名称不能为空")
        installed = self.installed_models()
        if not installed["online"]:
            raise ValueError(f"Ollama 离线，无法切换模型：{installed['error']}")
        names = {item.get("name") for item in installed["models"]}
        if model not in names and f"{model}:latest" in names:
            model = f"{model}:latest"
        if model not in names:
            raise ValueError(f"模型未安装或不可用：{model}")
        return model

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
