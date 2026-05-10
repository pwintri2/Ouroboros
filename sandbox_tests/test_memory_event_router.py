import json
import unittest

from controller.memory_event_router import (
    build_trigger_action_record,
    record_trigger_action,
    trigger_action_status,
)


class FakeCollection:
    def __init__(self):
        self.rows = {}
        self.add_order = []

    def count(self):
        return len(self.rows)

    def add(self, ids, documents, metadatas, embeddings=None):
        for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings or [[] for _ in ids]):
            self.rows[item_id] = {"document": document, "metadata": dict(metadata), "embedding": list(embedding)}
            self.add_order.append(item_id)

    def get(self, limit=100, include=None):
        selected = self.add_order[:limit]
        return {
            "ids": selected,
            "documents": [self.rows[item_id]["document"] for item_id in selected],
            "metadatas": [self.rows[item_id]["metadata"] for item_id in selected],
        }


class TestMemoryEventRouter(unittest.TestCase):
    def test_record_trigger_action_redacts_secrets_and_stores_11d_metadata(self):
        collection = FakeCollection()
        result = record_trigger_action(
            trigger="tool_result:run_command",
            action="run_command",
            route="agentic_processor",
            status="success",
            payload={"api_key": "secret-123456789", "command": "pwd"},
            result={"stdout": "Authorization: Bearer abc.def.ghi", "status": "success"},
            approval_required=True,
            approval_status="approved",
            source_trace={"token": "do-not-store", "planner": "unit"},
            collection=collection,
        )

        self.assertEqual(result["status"], "stored")
        self.assertEqual(collection.count(), 1)
        row = next(iter(collection.rows.values()))
        joined = row["document"] + json.dumps(row["metadata"], ensure_ascii=False)
        self.assertNotIn("secret-123456789", joined)
        self.assertNotIn("abc.def.ghi", joined)
        self.assertNotIn("do-not-store", joined)
        self.assertEqual(row["metadata"]["dimension_count"], 11)
        self.assertEqual(row["metadata"]["d3_physical_container"], "wintrip_trigger_actions_11d")
        self.assertEqual(row["metadata"]["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(row["metadata"]["dream_hz"]), 418.0)
        self.assertLessEqual(float(row["metadata"]["dream_hz"]), 432.0)
        self.assertNotEqual(row["metadata"]["d9_resonance_frequency"], "528.000000Hz")
        self.assertEqual(len(row["embedding"]), 11)

    def test_build_record_merges_11d_overrides_without_losing_dimensions(self):
        record = build_trigger_action_record(
            trigger="unknown_tool",
            action="resolve_or_build_function",
            route="agentic_processor",
            metadata_11d={"d5_persona_actor": "codex", "dimension_count": 11},
        )

        self.assertEqual(record.metadata_11d["dimension_count"], 11)
        self.assertEqual(record.metadata_11d["d5_persona_actor"], "codex")
        for index in range(1, 12):
            self.assertIn(f"d{index}_" if index < 10 else f"d{index}_", " ".join(record.metadata_11d.keys()))

    def test_status_returns_recent_event_ids_without_raw_documents(self):
        collection = FakeCollection()
        stored = record_trigger_action(
            trigger="chat",
            action="memory_search",
            route="cockpit",
            collection=collection,
        )

        status = trigger_action_status(collection=collection)

        self.assertEqual(status["status"], "online")
        self.assertEqual(status["count"], 1)
        self.assertEqual(status["recent_event_ids"], [stored["event_id"]])
        self.assertNotIn("documents", status)


if __name__ == "__main__":
    unittest.main()
