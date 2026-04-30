# sandbox_tests/test_agent_tools.py

import os
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.agent_tools import AgentToolRegistry, REGISTERED_TOOLS
from controller.stream.storage import StreamStorage


REQUIRED_TOOL_KEYS = {
    "status",
    "tool_name",
    "stdout",
    "stderr",
    "result",
    "source",
    "approval_status",
    "stored_to_memory",
    "metadata_11d",
    "next_action",
}


class MockCollection:
    def __init__(self):
        self._store = {}

    def count(self):
        return len(self._store)

    def add(self, documents, metadatas, ids, embeddings=None):
        for doc, meta, item_id in zip(documents, metadatas, ids):
            self._store[item_id] = {
                "document": doc,
                "metadata": dict(meta),
                "embedding": embeddings[0] if embeddings else None,
            }

    def get(self, where=None, limit=100, ids=None, include=None):
        results = {"ids": [], "documents": [], "metadatas": []}
        rows = self._store.items()
        if ids is not None:
            rows = [(item_id, self._store[item_id]) for item_id in ids if item_id in self._store]
        for item_id, entry in rows:
            if where and not all(entry["metadata"].get(key) == value for key, value in where.items()):
                continue
            results["ids"].append(item_id)
            results["documents"].append(entry["document"])
            results["metadatas"].append(entry["metadata"])
            if len(results["ids"]) >= limit:
                break
        return results


class DummyKnowledgeBase:
    def __init__(self):
        self.collection = MockCollection()

    def search(self, query, n_results=5):
        return [
            {
                "text": f"Ouroboros memory match for {query}",
                "metadata": {"type": "dummy"},
                "tier": "dummy",
            }
        ]


def make_registry():
    os.environ["WINTRIP_DB_PATH"] = tempfile.mkdtemp(prefix="wintrip-agent-tools-")
    os.environ["WINTRIP_TRAINING_COLLECTION"] = f"agent_tools_{uuid.uuid4().hex}"
    os.environ["WINTRIP_WORKSPACE"] = tempfile.mkdtemp(prefix="wintrip-agent-workspace-")
    storage = StreamStorage(collection=MockCollection())
    app = SimpleNamespace(state=SimpleNamespace(training_storage=storage, training_events=[]))
    return AgentToolRegistry(kb=DummyKnowledgeBase(), storage=storage, app=app)


class TestAgentTools(unittest.TestCase):
    def assertToolEnvelope(self, result, tool_name):
        self.assertTrue(REQUIRED_TOOL_KEYS.issubset(result.keys()))
        self.assertEqual(result["tool_name"], tool_name)
        self.assertIsInstance(result["stdout"], str)
        self.assertIsInstance(result["stderr"], str)
        self.assertIsInstance(result["metadata_11d"], dict)

    def test_registry_exposes_only_real_registered_tools_and_blocks_unknown(self):
        registry = make_registry()
        self.assertEqual(tuple(registry.status()["available_tools"]), REGISTERED_TOOLS)
        self.assertNotIn("training_preview", registry.status()["available_tools"])
        self.assertNotIn("training_approve", registry.status()["available_tools"])
        self.assertNotIn("train_cycle", registry.status()["available_tools"])

        result = registry.run_tool("fake_tool", {})
        self.assertToolEnvelope(result, "fake_tool")
        self.assertEqual(result["status"], "error")

    def test_prompt_understanding_detects_missing_browser_knowledge(self):
        registry = make_registry()
        result = registry.run_tool(
            "prompt_understanding",
            {"prompt": "Philip opdracht: onderzoek het laatste nieuws over ChromaDB en leer wat ontbreekt."},
        )
        self.assertToolEnvelope(result, "prompt_understanding")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["result"]["needs_browser_research"])
        self.assertTrue(result["result"]["missing_knowledge"])
        self.assertEqual(result["result"]["missing_knowledge"][0]["tool"], "browser_research")

    def test_training_ingest_requires_philip_approval(self):
        registry = make_registry()
        result = registry.run_tool(
            "training_ingest",
            {"text": "Wintrip AI traint de 11D kern.", "target_hz": 432.0, "approval": "nee"},
        )
        self.assertToolEnvelope(result, "training_ingest")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["approval_status"], "pending_philip_akkoord")
        self.assertFalse(result["stored_to_memory"])
        self.assertEqual(result["metadata_11d"]["d9_resonance_frequency"], "432.000000Hz")

    def test_training_ingest_stores_approved_learning_in_11d_collection_when_available(self):
        registry = make_registry()
        training_collection = MockCollection()
        with patch("controller.agent_tools._training_collection", return_value=training_collection):
            result = registry.run_tool(
                "training_ingest",
                {
                    "text": "Wintrip AI leert veilig via approval gated ChromaDB training.",
                    "target_hz": 421.0,
                    "approval": "Akkoord",
                },
            )

        self.assertToolEnvelope(result, "training_ingest")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["stored_to_memory"])
        self.assertEqual(training_collection.count(), 1)
        stored_meta = next(iter(training_collection._store.values()))["metadata"]
        self.assertEqual(stored_meta["dimension_count"], 11)
        self.assertEqual(stored_meta["tool_name"], "training_ingest")
        self.assertTrue(stored_meta["geometry_11d_available"])
        self.assertGreater(stored_meta["geometry_11d_volume"], 0)
        self.assertGreater(stored_meta["geometry_11d_oppervlakte"], 0)

    def test_memory_search_returns_local_matches_even_without_training_chromadb(self):
        registry = make_registry()
        result = registry.run_tool("memory_search", {"query": "Ouroboros", "limit": 3})
        self.assertToolEnvelope(result, "memory_search")
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["result"]["count"], 1)
        self.assertEqual(result["result"]["matches"][0]["source"], "wintrip_knowledge")

    def test_self_training_plan_uses_expected_phases_and_tools(self):
        registry = make_registry()
        result = registry.run_tool(
            "self_training_plan",
            {"prompt": "Philip opdracht: leer het laatste nieuws over Python packaging."},
        )
        self.assertToolEnvelope(result, "self_training_plan")
        self.assertEqual(result["status"], "success")
        self.assertIn("memory_search", [step["tool"] for step in result["result"]["steps"]])
        self.assertIn("browser_research", [step["tool"] for step in result["result"]["steps"]])
        self.assertIn("approval_gated_action", result["result"]["phases"])

    def test_run_tests_blocks_bad_selector(self):
        registry = make_registry()
        result = registry.run_tool(
            "run_tests",
            {"test_selector": "sandbox_tests.test_safe_shell; rm -rf /", "approval": "Akkoord"},
        )
        self.assertToolEnvelope(result, "run_tests")
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
