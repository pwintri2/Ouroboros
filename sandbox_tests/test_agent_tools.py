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

    def test_registry_advertises_schema_for_every_registered_tool(self):
        registry = make_registry()

        schemas = registry.get_tool_schemas()
        names = [schema["function"]["name"] for schema in schemas]

        self.assertEqual(set(names), set(REGISTERED_TOOLS))
        self.assertIn("brave_search", names)
        self.assertIn("ns_travel_advice", names)
        self.assertIn("roo_apply_patch", names)
        self.assertIn("mail_read_recent", names)
        self.assertIn("social_post_publish", names)
        self.assertIn("codex_job_start", names)
        self.assertIn("agentic_ecosystem_context", names)
        brave = next(schema for schema in schemas if schema["function"]["name"] == "brave_search")
        self.assertIn("query", brave["function"]["parameters"]["properties"])
        self.assertNotIn("approval", brave["function"]["parameters"]["required"])
        ns = next(schema for schema in schemas if schema["function"]["name"] == "ns_travel_advice")
        self.assertIn("from_station", ns["function"]["parameters"]["required"])
        self.assertIn("to_station", ns["function"]["parameters"]["required"])
        mail = next(schema for schema in schemas if schema["function"]["name"] == "mail_read_recent")
        self.assertIn("approval", mail["function"]["parameters"]["required"])
        ecosystem = next(schema for schema in schemas if schema["function"]["name"] == "agentic_ecosystem_context")
        self.assertIn("goal", ecosystem["function"]["parameters"]["properties"])

    def test_agentic_ecosystem_context_reads_only_safe_deepseek_atlas_patterns(self):
        old_deepseek = os.environ.get("WINTRIP_DEEPSEEK_PATH")
        old_atlas = os.environ.get("WINTRIP_ATLAS_PATH")
        try:
            with tempfile.TemporaryDirectory(prefix="deepseek-root-") as deepseek_tmp, tempfile.TemporaryDirectory(prefix="atlas-root-") as atlas_tmp:
                os.makedirs(os.path.join(deepseek_tmp, "docs"), exist_ok=True)
                os.makedirs(os.path.join(atlas_tmp, "context"), exist_ok=True)
                with open(os.path.join(deepseek_tmp, "docs", "SUBAGENTS.md"), "w", encoding="utf-8") as handle:
                    handle.write("subagents")
                with open(os.path.join(atlas_tmp, "context", "project-overview.md"), "w", encoding="utf-8") as handle:
                    handle.write("atlas")
                with open(os.path.join(deepseek_tmp, ".env"), "w", encoding="utf-8") as handle:
                    handle.write("SHOULD_NOT_READ")
                os.environ["WINTRIP_DEEPSEEK_PATH"] = deepseek_tmp
                os.environ["WINTRIP_ATLAS_PATH"] = atlas_tmp

                registry = make_registry()
                result = registry.run_tool(
                    "agentic_ecosystem_context",
                    {"goal": "verrijk agentisch werken met agents", "prefer_bridge": False},
                )

            self.assertToolEnvelope(result, "agentic_ecosystem_context")
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["approval_status"], "not_required_readonly")
            self.assertEqual(result["result"]["sources"], ["deepseek", "atlas"])
            self.assertIn("Sub-agent role taxonomy", result["stdout"])
            self.assertIn("Spec-driven delivery", result["stdout"])
            self.assertNotIn("SHOULD_NOT_READ", str(result))
        finally:
            if old_deepseek is None:
                os.environ.pop("WINTRIP_DEEPSEEK_PATH", None)
            else:
                os.environ["WINTRIP_DEEPSEEK_PATH"] = old_deepseek
            if old_atlas is None:
                os.environ.pop("WINTRIP_ATLAS_PATH", None)
            else:
                os.environ["WINTRIP_ATLAS_PATH"] = old_atlas

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

    def test_brave_search_is_readonly_without_akkoord(self):
        registry = make_registry()
        with patch(
            "controller.brave_search.search_brave_llm_context",
            return_value={"status": "success", "llm_context": "Actuele Brave context", "source_urls": ["https://example.com"]},
        ):
            result = registry.run_tool("brave_search", {"query": "laatste AI nieuws", "limit": 2})

        self.assertToolEnvelope(result, "brave_search")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["approval_status"], "not_required_readonly")
        self.assertIn("Actuele Brave context", result["stdout"])

    def test_ns_travel_advice_without_api_key_never_invents_times(self):
        registry = make_registry()
        with patch.dict(
            os.environ,
            {"WINTRIP_NS_API_KEY": "", "NS_API_KEY": "", "NS_APP_API_KEY": "", "NS_API_SUBSCRIPTION_KEY": ""},
            clear=False,
        ):
            result = registry.run_tool(
                "ns_travel_advice",
                {
                    "from_station": "Ermelo",
                    "to_station": "Utrecht Centraal",
                    "date": "2026-05-07",
                    "time": "13:30",
                    "search_for_arrival": True,
                },
            )

        self.assertToolEnvelope(result, "ns_travel_advice")
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["approval_status"], "not_required_readonly")
        self.assertFalse(result["result"]["authoritative"])
        self.assertTrue(result["result"]["missing_api_key"])
        self.assertIn("www.ns.nl/reisplanner", result["result"]["planner_url"])
        self.assertIn("geen officiële treintijden", result["stdout"])
        self.assertNotIn("12:30", result["stdout"])

    def test_ns_travel_advice_uses_official_api_when_key_is_configured(self):
        registry = make_registry()

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json_bytes

        json_bytes = (
            b'{"trips":[{"status":"NORMAL","transfers":1,"plannedDurationInMinutes":64,'
            b'"legs":[{"name":"Intercity","direction":"Utrecht Centraal",'
            b'"origin":{"name":"Ermelo","plannedDateTime":"2026-05-07T12:24:00+02:00","plannedTrack":"1"},'
            b'"destination":{"name":"Amersfoort Centraal","plannedDateTime":"2026-05-07T12:48:00+02:00","plannedTrack":"4"}},'
            b'{"name":"Sprinter","direction":"Utrecht Centraal",'
            b'"origin":{"name":"Amersfoort Centraal","plannedDateTime":"2026-05-07T12:56:00+02:00","plannedTrack":"6"},'
            b'"destination":{"name":"Utrecht Centraal","plannedDateTime":"2026-05-07T13:28:00+02:00","plannedTrack":"19"}}]}]}'
        )

        with patch.dict(os.environ, {"WINTRIP_NS_API_KEY": "test-key"}, clear=False):
            with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                result = registry.run_tool(
                    "ns_travel_advice",
                    {
                        "from_station": "Ermelo",
                        "to_station": "Utrecht Centraal",
                        "datetime": "2026-05-07T13:30:00",
                        "search_for_arrival": True,
                    },
                )

        self.assertToolEnvelope(result, "ns_travel_advice")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["result"]["authoritative"])
        self.assertEqual(result["result"]["advice"][0]["arrival_time"], "13:28")
        self.assertEqual(result["result"]["advice"][0]["legs"][0]["departure_time"], "12:24")
        request = urlopen.call_args.args[0]
        self.assertIn("fromStation=Ermelo", request.full_url)
        self.assertIn("toStation=Utrecht+Centraal", request.full_url)
        self.assertEqual(request.headers["Ocp-apim-subscription-key"], "test-key")

    def test_private_and_mutating_agentic_tools_are_approval_gated(self):
        registry = make_registry()

        cases = [
            ("mail_read_recent", {"limit": 3}),
            ("mail_send", {"to": "a@example.com", "subject": "Hoi", "body": "Test"}),
            ("social_post_publish", {"platform": "x", "content": "Ouroboros update"}),
            ("world_grok_ask", {"question": "Wat is Ouroboros?"}),
            ("codex_job_start", {"task": "Wijzig niets, rapporteer status."}),
        ]
        for tool_name, args in cases:
            with self.subTest(tool=tool_name):
                result = registry.run_tool(tool_name, args)
                self.assertToolEnvelope(result, tool_name)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["approval_status"], "pending_philip_akkoord")

    def test_mail_and_social_preview_do_not_perform_external_actions(self):
        registry = make_registry()

        mail = registry.run_tool(
            "mail_send_preview",
            {"to": "philip@example.com", "subject": "Ouroboros", "body": "Conceptbericht"},
        )
        social = registry.run_tool(
            "social_post_preview",
            {"platform": "x", "content": "Ouroboros leeft in de cockpit."},
        )

        self.assertToolEnvelope(mail, "mail_send_preview")
        self.assertToolEnvelope(social, "social_post_preview")
        self.assertEqual(mail["status"], "success")
        self.assertEqual(social["status"], "success")
        self.assertFalse(mail["result"]["sent"])
        self.assertFalse(social["result"]["posted"])
        self.assertEqual(mail["approval_status"], "not_required_preview")
        self.assertEqual(social["approval_status"], "not_required_preview")

    def test_mail_read_recent_uses_readonly_fetcher_after_approval(self):
        registry = make_registry()
        with patch(
            "controller.mail_fetcher.fetch_recent_emails",
            return_value=[{"status": "Success", "from": "sender@example.com", "subject": "Hallo", "body": "API_KEY=SECRET123 moet weg"}],
        ):
            result = registry.run_tool("mail_read_recent", {"limit": 1, "approval": "Akkoord"})

        self.assertToolEnvelope(result, "mail_read_recent")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["approval_status"], "approved")
        self.assertTrue(result["result"]["read_only"])
        self.assertNotIn("SECRET123", result["stdout"])

    def test_codex_job_start_uses_agent_runtime_after_approval(self):
        registry = make_registry()
        fake_job = SimpleNamespace(to_dict=lambda: {"job_id": "codex_test_123", "status": "queued"})
        fake_orchestrator = SimpleNamespace(submit=lambda *args, **kwargs: fake_job)
        with patch("controller.agent_runtime.orchestrator.get_orchestrator", return_value=fake_orchestrator):
            result = registry.run_tool("codex_job_start", {"task": "Rapporteer status", "approval": "Akkoord"})

        self.assertToolEnvelope(result, "codex_job_start")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["result"]["job_started"])
        self.assertEqual(result["result"]["job"]["job_id"], "codex_test_123")

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

    def test_browser_research_includes_brave_companion_context(self):
        def fake_browser(query, approval=""):
            return {
                "status": "success",
                "query": query,
                "scrubbed_text": "Browser result text",
                "fake_success": False,
            }

        registry = AgentToolRegistry(kb=DummyKnowledgeBase(), browser_researcher=fake_browser)
        with patch(
            "controller.agent_tools._brave_companion_for_browser_research",
            return_value={
                "status": "success",
                "provider": "brave",
                "document": "Brave LLM context text",
                "source_urls": ["https://example.com/source"],
                "fake_success": False,
            },
        ) as brave:
            result = registry.run_tool("browser_research", {"query": "Ouroboros", "approval": "Akkoord", "limit": 4})

        self.assertToolEnvelope(result, "browser_research")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["brave"]["status"], "success")
        self.assertIn("Brave LLM context text", result["stdout"])
        brave.assert_called_once_with("Ouroboros", approval="Akkoord", limit=4)

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
