import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from support_app.services.conversation_state_store import ConversationStateStore


class ConversationStateStoreTests(unittest.TestCase):
    def test_new_conversation_returns_default_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            state = store.get_state("c1", "api")

            self.assertEqual(state["stage"], "")
            self.assertEqual(state["product_anchor"], "")
            self.assertIn("known_needs", state)
            self.assertEqual(state["known_needs"]["room_size"], "")

    def test_update_then_get_returns_written_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            store.update_state("c1", {"product_anchor": "U-MOCO GRA", "scenario_anchor": "团播"}, "api")
            state = store.get_state("c1", "api")

            self.assertEqual(state["product_anchor"], "U-MOCO GRA")
            self.assertEqual(state["scenario_anchor"], "团播")

    def test_conversations_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            store.update_state("a", {"product_anchor": "GRA"}, "api")
            store.update_state("b", {"product_anchor": "PRO"}, "api")

            self.assertEqual(store.get_state("a", "api")["product_anchor"], "GRA")
            self.assertEqual(store.get_state("b", "api")["product_anchor"], "PRO")

    def test_channels_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            store.update_state("abc", {"product_anchor": "GRA"}, "web")
            store.update_state("abc", {"product_anchor": "PRO"}, "api")

            self.assertEqual(store.get_state("abc", "web")["product_anchor"], "GRA")
            self.assertEqual(store.get_state("abc", "api")["product_anchor"], "PRO")
            self.assertEqual(store.make_key("abc", "web"), "web:abc")
            self.assertEqual(store.make_key("abc", "api"), "api:abc")

    def test_known_needs_are_shallow_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStateStore(path=Path(tmp) / "conversation_state.json")
            store.update_state("c1", {"known_needs": {"room_size": "30平"}}, "api")
            store.update_state("c1", {"known_needs": {"camera_count": 2}}, "api")
            state = store.get_state("c1", "api")

            self.assertEqual(state["known_needs"]["room_size"], "30平")
            self.assertEqual(state["known_needs"]["camera_count"], 2)

    def test_expired_state_returns_default_and_cleans_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conversation_state.json"
            store = ConversationStateStore(path=path)
            key = store.make_key("c1", "api")
            expired = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            payload = {
                key: {
                    "state": {
                        **store._default_state(),
                        "product_anchor": "GRA",
                        "state_expire_at": expired,
                    }
                }
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            state = store.get_state("c1", "api")
            raw = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(state["product_anchor"], "")
            self.assertNotIn(key, raw)

    def test_clear_state_removes_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conversation_state.json"
            store = ConversationStateStore(path=path)
            store.update_state("c1", {"product_anchor": "GRA"}, "api")
            store.clear_state("c1", "api")
            state = store.get_state("c1", "api")

            self.assertEqual(state["product_anchor"], "")

    def test_missing_file_is_created_automatically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "conversation_state.json"
            self.assertFalse(path.exists())
            store = ConversationStateStore(path=path)
            self.assertTrue(path.exists())
            state = store.get_state("c1", "api")
            self.assertEqual(state["stage"], "")

    def test_corrupted_json_does_not_crash_and_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conversation_state.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{ bad json", encoding="utf-8")
            store = ConversationStateStore(path=path)
            state = store.get_state("c1", "api")

            self.assertEqual(state["product_anchor"], "")
            self.assertTrue(path.exists())

    def test_update_refreshes_updated_and_expire_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStateStore(path=Path(tmp) / "conversation_state.json", ttl_minutes=60)
            first = store.update_state("c1", {"product_anchor": "GRA"}, "api")
            time.sleep(1.1)
            second = store.update_state("c1", {"scenario_anchor": "团播"}, "api")

            self.assertTrue(first["updated_at"])
            self.assertTrue(first["state_expire_at"])
            self.assertTrue(second["updated_at"])
            self.assertTrue(second["state_expire_at"])
            self.assertNotEqual(first["updated_at"], second["updated_at"])

    def test_tests_use_temp_path_not_real_data_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conversation_state.json"
            store = ConversationStateStore(path=path)
            store.update_state("c1", {"product_anchor": "GRA"}, "api")

            self.assertTrue(path.exists())
            self.assertNotEqual(path.resolve(), Path("data/conversation_state.json").resolve())


if __name__ == "__main__":
    unittest.main()
