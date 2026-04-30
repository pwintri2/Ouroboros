# sandbox_tests/test_self_training_loop.py

import os
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.agent_tools import AgentToolRegistry
from controller.self_training import build_self_training_plan, self_training_loop, self_training_step
from controller.stream.storage import StreamStorage


class MockCollection:
    def __init__(self):
        self._store = {}

    def count(self):
        return len(self._store)

    def add(self, documents, metadatas, ids, embeddings=None):
        for doc, meta, item_id in zip(documents, metadatas, ids):
            self._store[item_id] = {"document": doc, "metadata": dict(meta)}

    def get(self, where=None, limit=100, ids=None, include=None):
        results = {"ids": [], "documents": [], "metadatas": []}
        for item_id, entry in list(self._store.items())[:limit]:
            results["ids"].append(item_id)
            results["documents"].append(entry["document"])
            results["metadatas"].append(entry["metadata"])
        return results


class EmptyKnowledgeBase:
    def __init__(self):
        self.collection = MockCollection()

    def search(self, query, n_results=5):
        return []


class MemoryKnowledgeBase:
    def __init__(self):
        self.collection = MockCollection()

    def search(self, query, n_results=5):
        return [{"text": "Local self-training policy memory", "metadata": {"type": "policy"}, "tier": "policy"}]


def make_registry(kb=None, browser_researcher=None):
    os.environ["WINTRIP_DB_PATH"] = tempfile.mkdtemp(prefix="wintrip-self-training-")
    os.environ["WINTRIP_TRAINING_COLLECTION"] = f"self_training_{uuid.uuid4().hex}"
    storage = StreamStorage(collection=MockCollection())
    app = SimpleNamespace(state=SimpleNamespace(training_storage=storage, training_events=[]))
    return AgentToolRegistry(
        kb=kb or EmptyKnowledgeBase(),
        storage=storage,
        app=app,
        browser_researcher=browser_researcher,
    )


class TestSelfTrainingLoop(unittest.TestCase):
    def test_build_self_training_plan_names_required_loop_phases(self):
        plan = build_self_training_plan(
            "Philip opdracht: onderzoek het laatste nieuws over ChromaDB.",
            understanding={
                "needs_browser_research": True,
                "research_query": "ChromaDB laatste nieuws",
                "candidate_actions": [{"tool": "browser_research", "approval_required": True}],
            },
        )
        self.assertEqual(
            plan["phases"],
            [
                "observe_prompt",
                "determine_missing_knowledge",
                "memory_search",
                "browser_research_request",
                "plan",
                "approval_gated_action",
                "reflect",
            ],
        )
        self.assertTrue(plan["approval_required"])
        self.assertEqual(plan["steps"][3]["tool"], "browser_research")

    def test_self_training_step_searches_memory_then_requests_browser_approval(self):
        registry = make_registry(kb=EmptyKnowledgeBase())
        result = self_training_step(
            "Philip opdracht: onderzoek het laatste nieuws over ChromaDB.",
            registry=registry,
        )

        phases = [entry["phase"] for entry in result["trace"]]
        self.assertIn("observe_prompt", phases)
        self.assertIn("memory_search", phases)
        self.assertIn("determine_missing_knowledge", phases)
        self.assertIn("browser_research_request", phases)
        self.assertIn("approval_gated_action", phases)
        self.assertIn("reflect", phases)
        self.assertEqual(result["status"], "blocked")

        browser_entries = [entry for entry in result["trace"] if entry["phase"] == "browser_research_request"]
        self.assertEqual(browser_entries[0]["tool_result"]["status"], "blocked")
        self.assertEqual(browser_entries[0]["tool_result"]["approval_status"], "pending_philip_akkoord")

    def test_self_training_loop_can_complete_with_memory_only_prompt(self):
        registry = make_registry(kb=MemoryKnowledgeBase())
        result = self_training_loop(
            "Philip opdracht: maak een self-training plan vanuit lokale policies.",
            registry=registry,
            approval="Akkoord",
            max_steps=2,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["steps"]), 1)
        self.assertFalse(result["steps"][0]["missing_knowledge"]["needs_browser_research"])
        self.assertIn("plan", [entry["phase"] for entry in result["steps"][0]["trace"]])


if __name__ == "__main__":
    unittest.main()
