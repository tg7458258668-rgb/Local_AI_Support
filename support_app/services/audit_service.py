from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class AuditService:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.path = runtime_dir / "chat_audit.log"

    def record(self, payload: dict) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        event = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **payload}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
