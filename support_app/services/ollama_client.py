from typing import Any

import requests

from support_app.settings import Settings


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def embedding(self, text: str) -> list[float]:
        resp = requests.post(
            f"{self.settings.ollama_url}/api/embeddings",
            json={"model": self.settings.embed_model, "prompt": text},
            timeout=120,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "embedding" not in data:
            raise RuntimeError(f"embedding接口返回异常: {data}")
        return data["embedding"]

    def generate(self, prompt: str) -> str:
        resp = requests.post(
            f"{self.settings.ollama_url}/api/generate",
            json={"model": self.settings.chat_model, "prompt": prompt, "stream": False},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

