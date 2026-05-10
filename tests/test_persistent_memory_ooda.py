import unittest

from controller.persistent_memory_manager import save_agentic_session
from controller.stream.metadata_11d import missing_11d_layers


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


class TestPersistentMemoryOoda(unittest.TestCase):
    def test_agentic_session_metadata_is_canonical_and_memory_cap_is_preserved(self):
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
        self.assertLessEqual(collection.count(), 300)
        joined = "\n".join(row["document"] for row in collection.rows.values())
        self.assertNotIn("SHOULD_NOT_STORE", joined)
        self.assertNotIn("bearer-secret-token", joined)
        last = collection.rows["session-26"]
        metadata = last["metadata"]
        self.assertEqual(metadata["type"], "agentic_session_11d")
        self.assertEqual(metadata["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(metadata["dream_hz"]), 418.0)
        self.assertLessEqual(float(metadata["dream_hz"]), 432.0)
        self.assertEqual(metadata["phase"], "reflect")
        self.assertEqual(metadata["event_kind"], "agentic_session")
        self.assertFalse(metadata["learnable"])
        self.assertTrue(metadata["audit_only"])
        self.assertEqual(missing_11d_layers(metadata), [])
        self.assertEqual(len(last["embedding"]), 11)


if __name__ == "__main__":
    unittest.main()
