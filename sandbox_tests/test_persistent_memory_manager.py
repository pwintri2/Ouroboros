import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import persistent_memory_manager as pm
from controller.persistent_memory_manager import save_agentic_session


class FakeCollection:
    def __init__(self):
        self.rows = {}
        self.add_order = []
        self.deleted = []

    def count(self):
        return len(self.rows)

    def add(self, ids, documents, metadatas, embeddings=None):
        for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings or [[] for _ in ids]):
            self.rows[item_id] = {"document": document, "metadata": dict(metadata), "embedding": list(embedding)}
            self.add_order.append(item_id)

    def get(self, limit=100, include=None, ids=None, where=None):
        selected_ids = ids or self.add_order[:limit]
        return {
            "ids": [item_id for item_id in selected_ids if item_id in self.rows],
            "documents": [self.rows[item_id]["document"] for item_id in selected_ids if item_id in self.rows],
            "metadatas": [self.rows[item_id]["metadata"] for item_id in selected_ids if item_id in self.rows],
        }

    def delete(self, ids):
        for item_id in ids:
            self.rows.pop(item_id, None)
            self.deleted.append(item_id)


class BrokenCollection:
    def count(self):
        raise RuntimeError("database disk image is malformed")

    def add(self, ids, documents, metadatas, embeddings=None):
        raise RuntimeError("database disk image is malformed")


class TestPersistentMemoryManager(unittest.TestCase):
    def setUp(self):
        self.old_max = os.environ.get("WINTRIP_AGENTIC_MEMORY_MAX")
        self.old_fallback = os.environ.get("WINTRIP_AGENTIC_SESSION_FALLBACK_PATH")
        self.old_recovery = os.environ.get("WINTRIP_AGENTIC_SESSION_RECOVERY_DB_PATH")
        os.environ["WINTRIP_AGENTIC_MEMORY_MAX"] = "25"

    def tearDown(self):
        if self.old_max is None:
            os.environ.pop("WINTRIP_AGENTIC_MEMORY_MAX", None)
        else:
            os.environ["WINTRIP_AGENTIC_MEMORY_MAX"] = self.old_max
        if self.old_fallback is None:
            os.environ.pop("WINTRIP_AGENTIC_SESSION_FALLBACK_PATH", None)
        else:
            os.environ["WINTRIP_AGENTIC_SESSION_FALLBACK_PATH"] = self.old_fallback
        if self.old_recovery is None:
            os.environ.pop("WINTRIP_AGENTIC_SESSION_RECOVERY_DB_PATH", None)
        else:
            os.environ["WINTRIP_AGENTIC_SESSION_RECOVERY_DB_PATH"] = self.old_recovery

    def test_save_agentic_session_redacts_secrets_and_caps_collection(self):
        collection = FakeCollection()

        for index in range(27):
            result = save_agentic_session(
                {
                    "session_id": f"session-{index}",
                    "goal": "test",
                    "status": "success",
                    "steps": [{"tool": "memory_search", "api_key": "SHOULD_NOT_STORE"}],
                    "stdout": "Authorization: bearer-secret-token",
                },
                collection=collection,
            )

        self.assertEqual(result["status"], "stored")
        self.assertLessEqual(collection.count(), 25)
        self.assertGreaterEqual(len(collection.deleted), 2)
        joined = "\n".join(row["document"] for row in collection.rows.values())
        self.assertNotIn("SHOULD_NOT_STORE", joined)
        self.assertNotIn("bearer-secret-token", joined)
        last_row = collection.rows["session-26"]
        self.assertEqual(len(last_row["embedding"]), 11)
        self.assertEqual(last_row["metadata"]["dimension_count"], 11)
        self.assertEqual(last_row["metadata"]["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(last_row["metadata"]["dream_hz"]), 418.0)
        self.assertLessEqual(float(last_row["metadata"]["dream_hz"]), 432.0)
        self.assertEqual(last_row["metadata"]["phase"], "reflect")
        self.assertFalse(last_row["metadata"]["learnable"])
        self.assertTrue(last_row["metadata"]["audit_only"])

    def test_save_agentic_session_falls_back_when_chroma_is_corrupt(self):
        with tempfile.TemporaryDirectory(prefix="agentic-memory-fallback-") as tmp:
            fallback_path = Path(tmp) / "sessions.jsonl"
            os.environ["WINTRIP_AGENTIC_SESSION_FALLBACK_PATH"] = str(fallback_path)

            result = save_agentic_session(
                {
                    "session_id": "session-corrupt",
                    "goal": "leer Office 365",
                    "status": "success",
                    "api_key": "SHOULD_NOT_STORE",
                },
                collection=BrokenCollection(),
            )

            self.assertEqual(result["status"], "stored_fallback")
            self.assertTrue(result["stored"])
            self.assertIn("database disk image is malformed", result["primary_error"])
            self.assertTrue(fallback_path.exists())
            text = fallback_path.read_text(encoding="utf-8")
            self.assertIn("session-corrupt", text)
            self.assertNotIn("SHOULD_NOT_STORE", text)

    def test_save_agentic_session_uses_recovery_chroma_when_primary_is_corrupt(self):
        recovery = FakeCollection()
        with tempfile.TemporaryDirectory(prefix="agentic-memory-recovery-") as tmp:
            os.environ["WINTRIP_AGENTIC_SESSION_RECOVERY_DB_PATH"] = str(Path(tmp) / "healthy-chroma")
            with patch.object(
                pm,
                "_agentic_collection",
                side_effect=[RuntimeError("database disk image is malformed"), recovery],
            ):
                result = save_agentic_session(
                    {
                        "session_id": "session-recovered",
                        "goal": "leer Office 365",
                        "status": "success",
                    }
                )

        self.assertEqual(result["status"], "stored_recovered")
        self.assertTrue(result["stored"])
        self.assertIn("database disk image is malformed", result["primary_error"])
        self.assertIn("session-recovered", recovery.rows)


if __name__ == "__main__":
    unittest.main()
