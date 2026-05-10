import unittest

from controller.memory_event_router import build_trigger_action_record, record_trigger_action
from controller.stream.metadata_11d import missing_11d_layers


class FakeCollection:
    def __init__(self):
        self.rows = {}

    def add(self, ids, documents, metadatas, embeddings=None):
        for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings or [[] for _ in ids]):
            self.rows[item_id] = {"document": document, "metadata": dict(metadata), "embedding": list(embedding)}

    def count(self):
        return len(self.rows)


class TestMemoryEventRouterOoda(unittest.TestCase):
    def test_trigger_action_metadata_uses_canonical_dreamcycle_not_old_resonance(self):
        record = build_trigger_action_record(
            trigger="tool_result:run_command",
            action="run_command",
            route="agentic_processor",
            status="success",
            approval_required=True,
            approval_status="approved",
            source_trace={"session_id": "agentic-1"},
        )

        metadata = record.metadata_11d
        self.assertEqual(metadata["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(metadata["dream_hz"]), 418.0)
        self.assertLessEqual(float(metadata["dream_hz"]), 432.0)
        self.assertEqual(metadata["frequency_band"], "418-432Hz")
        self.assertNotEqual(metadata["d9_resonance_frequency"], "528.000000Hz")
        self.assertNotIn("528.000000Hz", str(metadata))
        self.assertEqual(metadata["phase"], "act")
        self.assertEqual(metadata["event_kind"], "trigger_action")
        self.assertFalse(metadata["learnable"])
        self.assertTrue(metadata["audit_only"])
        self.assertEqual(missing_11d_layers(metadata), [])

    def test_record_trigger_action_persists_scalar_canonical_metadata(self):
        collection = FakeCollection()
        result = record_trigger_action(
            trigger="chat",
            action="memory_search",
            route="cockpit",
            status="success",
            payload={"authorization": "Bearer secret"},
            collection=collection,
        )

        self.assertEqual(result["status"], "stored")
        row = collection.rows[result["event_id"]]
        metadata = row["metadata"]
        self.assertEqual(metadata["type"], "trigger_action_record")
        self.assertEqual(metadata["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(metadata["dream_hz"]), 418.0)
        self.assertLessEqual(float(metadata["dream_hz"]), 432.0)
        self.assertTrue(all(isinstance(value, (str, int, float, bool)) for value in metadata.values()))
        self.assertNotIn("secret", row["document"].lower())
        self.assertEqual(len(row["embedding"]), 11)


if __name__ == "__main__":
    unittest.main()
