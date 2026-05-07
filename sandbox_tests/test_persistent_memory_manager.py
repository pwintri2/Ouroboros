import os
import unittest

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


class TestPersistentMemoryManager(unittest.TestCase):
    def setUp(self):
        self.old_max = os.environ.get("WINTRIP_AGENTIC_MEMORY_MAX")
        os.environ["WINTRIP_AGENTIC_MEMORY_MAX"] = "25"

    def tearDown(self):
        if self.old_max is None:
            os.environ.pop("WINTRIP_AGENTIC_MEMORY_MAX", None)
        else:
            os.environ["WINTRIP_AGENTIC_MEMORY_MAX"] = self.old_max

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


if __name__ == "__main__":
    unittest.main()
