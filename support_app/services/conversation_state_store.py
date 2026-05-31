from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class ConversationStateStore:
    def __init__(self, path: str | Path | None = None, ttl_minutes: int = 60):
        self.path = Path(path) if path else Path("data/conversation_state.json")
        self.ttl_minutes = max(1, int(ttl_minutes or 60))
        self._ensure_file()

    def make_key(self, conversation_id: str, channel: str = "default") -> str:
        conversation = str(conversation_id or "").strip()
        scoped_channel = str(channel or "default").strip() or "default"
        if not conversation:
            return ""
        return f"{scoped_channel}:{conversation}"

    def get_state(self, conversation_id: str, channel: str = "default") -> dict:
        try:
            key = self.make_key(conversation_id, channel)
            if not key:
                return self._default_state()
            data = self._load_data()
            record = data.get(key, {})
            if not isinstance(record, dict):
                return self._default_state()
            if self.is_expired(record):
                data.pop(key, None)
                self._save_data(data)
                return self._default_state()
            state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
            return self._merge_state(self._default_state(), state)
        except Exception:
            return self._default_state()

    def update_state(self, conversation_id: str, state_updates: dict, channel: str = "default") -> dict:
        try:
            key = self.make_key(conversation_id, channel)
            if not key:
                return self._default_state()
            data = self._load_data()
            record = data.get(key, {})
            existing_state = record.get("state", {}) if isinstance(record, dict) and isinstance(record.get("state"), dict) else {}
            state = self._merge_state(self._default_state(), existing_state)
            updates = state_updates if isinstance(state_updates, dict) else {}
            for field, value in updates.items():
                if field == "known_needs" and isinstance(value, dict) and isinstance(state.get("known_needs"), dict):
                    state["known_needs"] = {**state["known_needs"], **value}
                else:
                    state[field] = value
            state["updated_at"] = self._now()
            state["state_expire_at"] = self._expire_at()
            data[key] = {"state": state}
            self._save_data(data)
            return state
        except Exception:
            return self._default_state()

    def clear_state(self, conversation_id: str, channel: str = "default") -> None:
        try:
            key = self.make_key(conversation_id, channel)
            if not key:
                return
            data = self._load_data()
            data.pop(key, None)
            self._save_data(data)
        except Exception:
            return

    def is_expired(self, record: dict) -> bool:
        if not isinstance(record, dict):
            return False
        state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
        raw = state.get("state_expire_at") or record.get("state_expire_at")
        if not raw:
            return False
        parsed = self._parse_time(str(raw))
        if not parsed:
            return True
        return parsed <= datetime.now()

    def _default_state(self) -> dict[str, Any]:
        return {
            "stage": "",
            "product_anchor": "",
            "scenario_anchor": "",
            "known_needs": {
                "room_size": "",
                "camera_count": "",
                "budget": "",
                "need_track": "",
                "camera_weight": "",
            },
            "missing_fields": [],
            "last_user_intent": "",
            "last_assistant_route": "",
            "last_recommendation": "",
            "recommended_products": [],
            "quote_readiness": "",
            "risk_flags": [],
            "human_handoff_required": False,
            "last_need_human_reason": "",
            "pending_questions": [],
            "updated_at": "",
            "state_expire_at": "",
        }

    def _merge_state(self, base: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in (state or {}).items():
            if key == "known_needs" and isinstance(value, dict) and isinstance(merged.get("known_needs"), dict):
                merged["known_needs"] = {**merged["known_needs"], **value}
            else:
                merged[key] = value
        return merged

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _load_data(self) -> dict[str, Any]:
        self._ensure_file()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            self._backup_corrupted_file()
            try:
                self.path.write_text("{}", encoding="utf-8")
            except Exception:
                pass
            return {}

    def _save_data(self, data: dict[str, Any]) -> None:
        self._ensure_file()
        payload = data if isinstance(data, dict) else {}
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def _backup_corrupted_file(self) -> None:
        try:
            if not self.path.exists():
                return
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup = self.path.with_name(f"{self.path.name}.broken.{stamp}.bak")
            backup.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            return

    def _expire_at(self) -> str:
        return (datetime.now() + timedelta(minutes=self.ttl_minutes)).strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _parse_time(raw: str) -> datetime | None:
        text = str(raw or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None
