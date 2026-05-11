# sandbox_tests/test_agent_tools.py

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
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
    ziel = Path(os.environ["WINTRIP_WORKSPACE"]) / ".agents" / "agent_types" / "type_2" / "Ziel.md"
    ziel.parent.mkdir(parents=True)
    ziel.write_text(
        "# Zielenboek\n\n1. **Veerkracht bij Weerstand (Micro-Retries):** Probeer bounded opnieuw.\n2. **Laterale Creativiteit:** Zoek veilige omwegen.\n",
        encoding="utf-8",
    )
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
        self.assertIn("ov9292_travel_advice", names)
        self.assertIn("connector_intent_preview", names)
        self.assertIn("gmail_status", names)
        self.assertIn("gmail_search", names)
        self.assertIn("google_drive_status", names)
        self.assertIn("google_drive_list", names)
        self.assertIn("github_status", names)
        self.assertIn("github_repo", names)
        self.assertIn("github_search_repositories", names)
        self.assertIn("vps_status", names)
        self.assertIn("vps_login_check", names)
        self.assertIn("vps_sync_preview", names)
        self.assertIn("vps_sync_execute", names)
        self.assertIn("vps_ui_sync_preview", names)
        self.assertIn("vps_ui_sync_execute", names)
        self.assertIn("chroma_sync_status", names)
        self.assertIn("chroma_sync_preview", names)
        self.assertIn("chroma_sync_execute", names)
        self.assertIn("roo_apply_patch", names)
        self.assertIn("mail_read_recent", names)
        self.assertIn("social_post_publish", names)
        self.assertIn("codex_job_start", names)
        self.assertIn("resolve_or_build_function", names)
        self.assertIn("agentic_ecosystem_context", names)
        brave = next(schema for schema in schemas if schema["function"]["name"] == "brave_search")
        self.assertIn("query", brave["function"]["parameters"]["properties"])
        self.assertNotIn("approval", brave["function"]["parameters"]["required"])
        ns = next(schema for schema in schemas if schema["function"]["name"] == "ns_travel_advice")
        self.assertIn("from_station", ns["function"]["parameters"]["required"])
        self.assertIn("to_station", ns["function"]["parameters"]["required"])
        self.assertIn("browser_lookup", ns["function"]["parameters"]["properties"])
        ov9292 = next(schema for schema in schemas if schema["function"]["name"] == "ov9292_travel_advice")
        self.assertIn("query", ov9292["function"]["parameters"]["properties"])
        self.assertIn("browser_lookup", ov9292["function"]["parameters"]["properties"])
        self.assertEqual(ov9292["function"]["parameters"]["required"], [])
        connector_preview = next(schema for schema in schemas if schema["function"]["name"] == "connector_intent_preview")
        self.assertIn("prompt", connector_preview["function"]["parameters"]["required"])
        gmail_search = next(schema for schema in schemas if schema["function"]["name"] == "gmail_search")
        self.assertIn("approval", gmail_search["function"]["parameters"]["required"])
        drive_list = next(schema for schema in schemas if schema["function"]["name"] == "google_drive_list")
        self.assertIn("approval", drive_list["function"]["parameters"]["required"])
        github_repo = next(schema for schema in schemas if schema["function"]["name"] == "github_repo")
        self.assertIn("repo", github_repo["function"]["parameters"]["required"])
        github_search = next(schema for schema in schemas if schema["function"]["name"] == "github_search_repositories")
        self.assertIn("query", github_search["function"]["parameters"]["required"])
        vps_execute = next(schema for schema in schemas if schema["function"]["name"] == "vps_sync_execute")
        self.assertIn("approval", vps_execute["function"]["parameters"]["required"])
        ui_execute = next(schema for schema in schemas if schema["function"]["name"] == "vps_ui_sync_execute")
        self.assertIn("approval", ui_execute["function"]["parameters"]["required"])
        chroma_execute = next(schema for schema in schemas if schema["function"]["name"] == "chroma_sync_execute")
        self.assertIn("approval", chroma_execute["function"]["parameters"]["required"])
        mail = next(schema for schema in schemas if schema["function"]["name"] == "mail_read_recent")
        self.assertIn("approval", mail["function"]["parameters"]["required"])
        ecosystem = next(schema for schema in schemas if schema["function"]["name"] == "agentic_ecosystem_context")
        self.assertIn("goal", ecosystem["function"]["parameters"]["properties"])
        self_programming = next(schema for schema in schemas if schema["function"]["name"] == "resolve_or_build_function")
        self.assertIn("requested_capability", self_programming["function"]["parameters"]["required"])
        self.assertIn("execute_after_build", self_programming["function"]["parameters"]["properties"])

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
            {
                "WINTRIP_NS_API_KEY": "",
                "NS_API_KEY": "",
                "NS_APP_API_KEY": "",
                "NS_API_SUBSCRIPTION_KEY": "",
                "WINTRIP_TRAVEL_BROWSER_LOOKUP": "0",
                "WINTRIP_TRAVEL_USE_NS_API": "0",
            },
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
        self.assertTrue(result["result"]["api_skipped"])
        self.assertIn("www.ns.nl/reisplanner", result["result"]["planner_url"])
        self.assertIn("geen officiële treintijden", result["stdout"])
        self.assertNotIn("12:30", result["stdout"])

    def test_ns_travel_advice_can_use_visible_official_planner_text(self):
        registry = make_registry()
        visible = "\n".join(
            [
                "Reisadvies Ermelo naar Utrecht Centraal",
                "Vertrek 12:24 spoor 1",
                "Intercity richting Utrecht Centraal",
                "Aankomst 13:28 spoor 19",
            ]
        )
        with patch.dict(
            os.environ,
            {
                "WINTRIP_NS_API_KEY": "",
                "NS_API_KEY": "",
                "NS_APP_API_KEY": "",
                "NS_API_SUBSCRIPTION_KEY": "",
                "WINTRIP_TRAVEL_BROWSER_LOOKUP": "1",
                "WINTRIP_TRAVEL_USE_NS_API": "0",
            },
            clear=False,
        ):
            with patch(
                "controller.browser_research.read_visible_text",
                return_value={
                    "status": "success",
                    "browser_action_performed": True,
                    "scrubbed_text": visible,
                    "source_url": "https://www.ns.nl/reisplanner/#/",
                    "approval_status": "not_required_readonly",
                },
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
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["result"]["authoritative"])
        self.assertIn("12:24", result["result"]["visible_times"])
        self.assertIn("13:28", result["result"]["visible_times"])
        self.assertIn("Zichtbare officiële plannerdata", result["stdout"])

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

        with patch.dict(os.environ, {"WINTRIP_NS_API_KEY": "test-key", "WINTRIP_TRAVEL_USE_NS_API": "1"}, clear=False):
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

    def test_9292_travel_advice_returns_official_links_without_scraping_or_times(self):
        registry = make_registry()
        result = registry.run_tool(
            "ov9292_travel_advice",
            {
                "from_place": "Ermelo",
                "to_place": "Utrecht Science Park",
                "date": "2026-05-07",
                "time": "13:30",
                "search_for_arrival": True,
                "query": "bus tram metro reisplanner via 9292",
                "browser_lookup": False,
            },
        )

        self.assertToolEnvelope(result, "ov9292_travel_advice")
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["approval_status"], "not_required_readonly")
        self.assertFalse(result["result"]["authoritative"])
        self.assertFalse(result["result"]["scraped"])
        self.assertFalse(result["result"]["session_material_used"])
        self.assertIn("9292.nl", result["result"]["planner_url"])
        self.assertIn("geen officiële", result["stdout"])
        self.assertNotIn("12:30", result["stdout"])

    def test_connector_intent_preview_gates_private_mutating_services_without_execution(self):
        registry = make_registry()
        result = registry.run_tool(
            "connector_intent_preview",
            {
                "prompt": "Upload rapport naar Google Drive en deploy via VPS",
                "services": ["google_drive", "vps"],
                "action_type": "private_mutating",
            },
        )

        self.assertToolEnvelope(result, "connector_intent_preview")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["approval_status"], "pending_philip_akkoord")
        self.assertFalse(result["result"]["executed"])
        self.assertTrue(result["result"]["preview_only"])
        self.assertIn("google_drive", result["result"]["services"])
        self.assertIn("vps", result["result"]["services"])
        self.assertIn("google_drive_connector", result["result"]["blocked_tools"])
        self.assertIn("vps_host_action", result["result"]["blocked_tools"])
        self.assertFalse(result["result"]["secrets_returned"])
        self.assertEqual(result["result"]["ziel_policy"]["status"], "loaded")
        self.assertIn("ToolBridge", result["result"]["ziel_policy"]["guardrail"])
        self.assertIn("ziel_policy_hash", result["metadata_11d"])

    def test_google_connector_statuses_redact_tokens(self):
        registry = make_registry()
        google_status = {
            "status": "connected",
            "token": {"exists": True, "access_token": "ya29.secret", "refresh_token": "refresh-secret", "has_refresh_token": True},
            "fake_success": False,
        }
        rclone_status = {"status": "ready", "tokens_returned": False, "drive_remotes": ["gdrive"], "fake_success": False}

        class FakeGoogle:
            def status(self):
                return google_status

        class FakeRclone:
            def status(self):
                return rclone_status

        with patch("controller.google_workspace_adapter.GoogleWorkspaceAdapter", return_value=FakeGoogle()):
            gmail = registry.run_tool("gmail_status", {})
        with patch("controller.google_workspace_adapter.GoogleWorkspaceAdapter", return_value=FakeGoogle()):
            with patch("controller.rclone_drive_adapter.RcloneDriveAdapter", return_value=FakeRclone()):
                drive = registry.run_tool("google_drive_status", {})

        self.assertToolEnvelope(gmail, "gmail_status")
        self.assertEqual(gmail["status"], "success")
        self.assertEqual(gmail["approval_status"], "not_required_status")
        self.assertEqual(gmail["result"]["ziel_policy"]["status"], "loaded")
        self.assertNotIn("ya29.secret", gmail["stdout"])
        self.assertNotIn("refresh-secret", gmail["stdout"])
        self.assertTrue(gmail["result"]["token"]["has_refresh_token"])
        self.assertToolEnvelope(drive, "google_drive_status")
        self.assertEqual(drive["status"], "success")
        self.assertNotIn("ya29.secret", drive["stdout"])
        self.assertNotIn("refresh-secret", drive["stdout"])

    def test_gmail_search_is_approval_gated_and_sanitizes_results(self):
        registry = make_registry()
        blocked = registry.run_tool("gmail_search", {"query": "in:inbox", "max_results": 2})

        class FakeGoogle:
            def search_gmail(self, query, approval="", max_results=10):
                return {
                    "status": "success",
                    "operation": "search_gmail",
                    "items": [{"id": "m1", "subject": "Hallo", "snippet": "token=SECRET123"}],
                    "access_token": "SHOULD_NOT_RETURN",
                    "fake_success": False,
                }

        with patch("controller.google_workspace_adapter.GoogleWorkspaceAdapter", return_value=FakeGoogle()):
            approved = registry.run_tool("gmail_search", {"query": "in:inbox", "max_results": 2, "approval": "Akkoord"})

        self.assertToolEnvelope(blocked, "gmail_search")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["approval_status"], "pending_philip_akkoord")
        self.assertEqual(blocked["result"]["ziel_policy"]["status"], "loaded")
        self.assertIn("ziel_policy_hash", blocked["metadata_11d"])
        self.assertToolEnvelope(approved, "gmail_search")
        self.assertEqual(approved["status"], "success")
        self.assertEqual(approved["approval_status"], "approved")
        self.assertNotIn("SECRET123", approved["stdout"])
        self.assertNotIn("SHOULD_NOT_RETURN", approved["stdout"])
        self.assertEqual(approved["result"]["access_token"], "[REDACTED]")

    def test_drive_list_is_approval_gated_and_uses_readonly_rclone(self):
        registry = make_registry()
        blocked = registry.run_tool("google_drive_list", {"path": "Reports"})

        class FakeRclone:
            def status(self):
                return {"status": "ready", "drive_remotes": ["gdrive"], "fake_success": False}

            def list_drive_files(self, **kwargs):
                return {
                    "status": "success",
                    "operation": "list_drive_files",
                    "items": [{"Name": "rapport.txt", "Path": "Reports/rapport.txt", "token": "SECRET"}],
                    "fake_success": False,
                }

        with patch("controller.rclone_drive_adapter.RcloneDriveAdapter", return_value=FakeRclone()):
            approved = registry.run_tool("google_drive_list", {"path": "Reports", "approval": "Akkoord", "adapter": "rclone"})

        self.assertToolEnvelope(blocked, "google_drive_list")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["approval_status"], "pending_philip_akkoord")
        self.assertEqual(blocked["result"]["ziel_policy"]["status"], "loaded")
        self.assertIn("ziel_policy_hash", blocked["metadata_11d"])
        self.assertToolEnvelope(approved, "google_drive_list")
        self.assertEqual(approved["status"], "success")
        self.assertEqual(approved["approval_status"], "approved")
        self.assertNotIn("SECRET", approved["stdout"])
        self.assertEqual(approved["result"]["items"][0]["token"], "[REDACTED]")

    def test_github_tools_are_readonly_and_redact_tokens(self):
        registry = make_registry()

        class FakeGithub:
            def status(self):
                return {
                    "status": "configured",
                    "token": {"configured": True, "source": "env:GITHUB_TOKEN", "masked": "ghp_...1234", "secrets_returned": False},
                    "fake_success": False,
                }

            def get_repository(self, repo, approval=""):
                return {
                    "status": "success",
                    "operation": "get_repository",
                    "repo": {"full_name": repo, "private": False, "description": "token=SECRET456"},
                    "approval_status": "not_required_public_readonly",
                    "access_token": "ghp_SECRET",
                    "fake_success": False,
                }

            def search_repositories(self, query, limit=10, approval=""):
                return {
                    "status": "success",
                    "operation": "search_repositories",
                    "query": query,
                    "effective_query": f"{query} is:public",
                    "items": [{"full_name": "octocat/Hello-World", "private": False}],
                    "approval_status": "not_required_public_readonly",
                    "fake_success": False,
                }

        with patch("controller.github_adapter.GitHubAdapter", return_value=FakeGithub()):
            status = registry.run_tool("github_status", {})
            repo = registry.run_tool("github_repo", {"repo": "octocat/Hello-World"})
            search = registry.run_tool("github_search_repositories", {"query": "ouroboros"})

        self.assertToolEnvelope(status, "github_status")
        self.assertEqual(status["status"], "success")
        self.assertNotIn("ghp_SECRET", status["stdout"])
        self.assertToolEnvelope(repo, "github_repo")
        self.assertEqual(repo["status"], "success")
        self.assertNotIn("SECRET456", repo["stdout"])
        self.assertNotIn("ghp_SECRET", repo["stdout"])
        self.assertEqual(repo["result"]["access_token"], "[REDACTED]")
        self.assertToolEnvelope(search, "github_search_repositories")
        self.assertEqual(search["status"], "success")
        self.assertIn("is:public", search["result"]["effective_query"])

    def test_vps_tools_preview_first_and_execute_requires_akkoord(self):
        registry = make_registry()

        class FakeVPS:
            def status(self):
                return {
                    "status": "ready",
                    "profile": {"profile_id": "test", "ssh_host_alias": "vps-alias", "secrets_returned": False},
                    "remote_target": "/var/www/philip-wintrip.nl/html/Ouroboros/",
                    "fake_success": False,
                }

            def login_check(self, timeout_seconds=120):
                return {
                    "status": "success",
                    "operation": "login_check",
                    "login_ok": True,
                    "stdout": "ouroboros-vps-ok token=SECRET",
                    "secrets_returned": False,
                    "fake_success": False,
                }

            def sync_preview(self, remote_path="", source_path="", timeout_seconds=120):
                return {
                    "status": "preview",
                    "operation": "sync_preview",
                    "dry_run": True,
                    "executed": False,
                    "mutated": False,
                    "remote_target": "/var/www/philip-wintrip.nl/html/Ouroboros/",
                    "excluded_patterns": [".secrets/", ".env*"],
                    "stdout": "would sync token=SECRET",
                    "fake_success": False,
                }

            def sync_execute(self, approval="", remote_path="", source_path="", timeout_seconds=120):
                return {
                    "status": "success",
                    "operation": "sync_execute",
                    "dry_run": False,
                    "executed": True,
                    "mutated": True,
                    "remote_target": "/var/www/philip-wintrip.nl/html/Ouroboros/",
                    "stdout": "sent files token=SECRET",
                    "fake_success": False,
                }

        blocked = registry.run_tool("vps_sync_execute", {})
        with patch("controller.vps_deploy_adapter.VPSDeployAdapter", return_value=FakeVPS()):
            status = registry.run_tool("vps_status", {})
            login = registry.run_tool("vps_login_check", {})
            preview = registry.run_tool("vps_sync_preview", {})
            executed = registry.run_tool("vps_sync_execute", {"approval": "Akkoord"})

        self.assertToolEnvelope(blocked, "vps_sync_execute")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["approval_status"], "pending_philip_akkoord")
        self.assertFalse(blocked["result"]["executed"])
        self.assertEqual(blocked["result"]["remote_target"], "/var/www/philip-wintrip.nl/html/Ouroboros/")
        self.assertToolEnvelope(status, "vps_status")
        self.assertEqual(status["status"], "success")
        self.assertEqual(status["result"]["ziel_policy"]["status"], "loaded")
        self.assertNotIn("SECRET", status["stdout"])
        self.assertToolEnvelope(login, "vps_login_check")
        self.assertEqual(login["status"], "success")
        self.assertNotIn("SECRET", login["stdout"])
        self.assertToolEnvelope(preview, "vps_sync_preview")
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(preview["approval_status"], "not_required_dry_run")
        self.assertEqual(preview["result"]["ziel_policy"]["status"], "loaded")
        self.assertIn("ziel_policy_hash", preview["metadata_11d"])
        self.assertFalse(preview["result"]["mutated"])
        self.assertIn(".secrets/", preview["result"]["excluded_patterns"])
        self.assertNotIn("SECRET", preview["stdout"])
        self.assertToolEnvelope(executed, "vps_sync_execute")
        self.assertEqual(executed["status"], "success")
        self.assertEqual(executed["approval_status"], "approved")
        self.assertTrue(executed["result"]["executed"])
        self.assertNotIn("SECRET", executed["stdout"])

    def test_private_and_mutating_agentic_tools_are_approval_gated(self):
        registry = make_registry()

        cases = [
            ("mail_read_recent", {"limit": 3}),
            ("mail_send", {"to": "a@example.com", "subject": "Hoi", "body": "Test"}),
            ("social_post_publish", {"platform": "x", "content": "Ouroboros update"}),
            ("world_grok_ask", {"question": "Wat is Ouroboros?"}),
            ("codex_job_start", {"task": "Wijzig niets, rapporteer status."}),
            ("vps_ui_sync_execute", {}),
            ("chroma_sync_execute", {}),
        ]
        for tool_name, args in cases:
            with self.subTest(tool=tool_name):
                result = registry.run_tool(tool_name, args)
                self.assertToolEnvelope(result, tool_name)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["approval_status"], "pending_philip_akkoord")

    def test_resolve_or_build_function_tool_blocks_missing_capability_without_akkoord(self):
        registry = make_registry()
        with patch(
            "controller.self_programming_loop._fetch_brave_context",
            return_value={"status": "success", "document": "context", "fake_success": False},
        ):
            result = registry.run_tool("resolve_or_build_function", {"requested_capability": "unknown_new_tool"})

        self.assertToolEnvelope(result, "resolve_or_build_function")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["approval_status"], "pending_philip_akkoord")
        self.assertEqual(result["result"]["phase"], "approval_required_for_build")

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
        fake_mail_fetcher = SimpleNamespace(
            fetch_recent_emails=lambda limit=1: [
                {"status": "Success", "from": "sender@example.com", "subject": "Hallo", "body": "API_KEY=SECRET123 moet weg"}
            ]
        )
        with patch.dict(
            sys.modules,
            {"controller.mail_fetcher": fake_mail_fetcher},
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
