import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    FastAPI = None
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""

from controller.ouroboros_agent_architecture import (
    APPROVAL_PHRASE,
    build_critic_review,
    get_agent_architecture_catalog,
)


class TestOuroborosAgentArchitecture(unittest.TestCase):
    def test_catalog_contains_exact_four_agents_with_tools_and_gates(self):
        data = get_agent_architecture_catalog(include_status=False)

        self.assertEqual(data["status"], "online")
        self.assertFalse(data["fake_success"])
        self.assertFalse(data["secrets_returned"])
        self.assertEqual(data["approval_policy"]["approval_phrase"], APPROVAL_PHRASE)

        agents = data["agents"]
        self.assertEqual([agent["id"] for agent in agents], ["codex", "web_scout", "communicator", "criticus"])

        by_id = {agent["id"]: agent for agent in agents}
        self.assertIn("gmail_status", by_id["codex"]["allowed_tools"])
        self.assertIn("google_drive_list", by_id["codex"]["approval_required_for"])
        self.assertIn("brave_search", by_id["web_scout"]["allowed_tools"])
        self.assertIn("browser_research", by_id["web_scout"]["approval_required_for"])
        self.assertIn("browser_open_url", by_id["communicator"]["approval_required_for"])
        self.assertIn("architecture_critic_review", by_id["criticus"]["allowed_tools"])
        self.assertEqual(by_id["criticus"]["readiness"], "klaar")

    def test_criticus_blocks_self_copy_execute_but_returns_dry_run_manifest(self):
        review = build_critic_review(
            {
                "prompt": "Kopieer jezelf en installeer Ouroboros automatisch op Windows en iPhone.",
                "agent_id": "codex",
                "tool": "safe_shell",
                "requested_mode": "execute",
            },
            store_audit=False,
        )

        self.assertEqual(review["status"], "blocked")
        self.assertEqual(review["decision"], "dry_run_manifest_only")
        self.assertFalse(review["execute_allowed"])
        self.assertTrue(review["self_copy_install"])
        self.assertIn("self_copy_install", review["risk_categories"])
        self.assertEqual(review["dry_run_manifest"]["status"], "preview")
        self.assertIn("windows", review["dry_run_manifest"]["target_platforms"])
        self.assertFalse(review["execution_performed"])

    def test_criticus_detects_self_install_tool_and_target_context(self):
        review = build_critic_review(
            {
                "intent": "test self install",
                "agent": "Criticus",
                "tool": "self_install",
                "action": "execute",
                "target": "vps",
                "requested_mode": "execute",
            },
            store_audit=False,
        )

        self.assertEqual(review["status"], "blocked")
        self.assertEqual(review["decision"], "dry_run_manifest_only")
        self.assertTrue(review["self_copy_install"])
        self.assertTrue(review["vps_network"])
        self.assertIn("self_copy_install", review["risk_categories"])
        self.assertIn("vps_or_network", review["risk_categories"])
        self.assertFalse(review["execute_allowed"])

    def test_private_connector_reads_remain_approval_gated(self):
        gmail = build_critic_review(
            {"prompt": "Lees mijn inbox", "tool": "gmail_search", "requested_mode": "execute"},
            store_audit=False,
        )
        drive = build_critic_review(
            {"prompt": "Toon mijn Google Drive bestanden", "tool": "google_drive_list", "requested_mode": "execute"},
            store_audit=False,
        )

        for review in (gmail, drive):
            self.assertEqual(review["status"], "approval_required")
            self.assertTrue(review["approval_required"])
            self.assertFalse(review["execute_allowed"])
            self.assertTrue(review["private_data"])
            self.assertEqual(review["approval_status"], "pending_philip_akkoord")

    def test_playwright_browser_research_remains_approval_gated(self):
        review = build_critic_review(
            {"prompt": "Lees een webpagina met Playwright", "tool": "browser_research", "requested_mode": "execute"},
            store_audit=False,
        )

        self.assertEqual(review["status"], "approval_required")
        self.assertTrue(review["approval_required"])
        self.assertFalse(review["execute_allowed"])
        self.assertTrue(review["external_browser_read"])
        self.assertIn("external_browser_read", review["risk_categories"])

    def test_public_github_and_brave_reads_are_readonly_without_approval(self):
        github = build_critic_review(
            {"prompt": "Bekijk pwintri2/wintripai metadata", "tool": "github_repo", "requested_mode": "execute"},
            store_audit=False,
        )
        brave = build_critic_review(
            {"prompt": "Zoek actuele API documentatie", "tool": "brave_search", "requested_mode": "execute"},
            store_audit=False,
        )

        for review in (github, brave):
            self.assertEqual(review["status"], "review_passed")
            self.assertEqual(review["approval_status"], "not_required_readonly")
            self.assertTrue(review["public_read"])
            self.assertFalse(review["mutating"])
            self.assertTrue(review["execute_allowed"])
            self.assertFalse(review["fake_success"])


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestOuroborosAgentArchitectureRoutes(unittest.TestCase):
    def setUp(self):
        from controller.api.ouroboros_agent_architecture_routes import init_agent_architecture_routes

        self.old_db_path = os.environ.get("WINTRIP_DB_PATH")
        self.db_tmp = tempfile.TemporaryDirectory(prefix="agent-architecture-routes-")
        os.environ["WINTRIP_DB_PATH"] = self.db_tmp.name
        app = FastAPI()
        init_agent_architecture_routes(app)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db_tmp.cleanup()
        if self.old_db_path is None:
            os.environ.pop("WINTRIP_DB_PATH", None)
        else:
            os.environ["WINTRIP_DB_PATH"] = self.old_db_path

    def test_architecture_route_serves_contract_without_live_tokens(self):
        response = self.client.get("/api/ouroboros/agents/architecture")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["agent_count"], 4)
        self.assertFalse(data["fake_success"])
        self.assertFalse(data["secrets_returned"])
        self.assertIn("agent_architecture_review", data["public_interfaces"])
        self.assertEqual([agent["id"] for agent in data["agents"]], ["codex", "web_scout", "communicator", "criticus"])

    def test_review_route_never_executes_requested_action(self):
        response = self.client.post(
            "/api/ouroboros/agents/architecture/review",
            json={
                "prompt": "Verstuur mail vanuit Gmail",
                "tool": "mail_send",
                "requested_mode": "execute",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["status"], {"approval_required", "blocked"})
        self.assertFalse(data["execution_performed"])
        self.assertFalse(data["execute_allowed"])
        self.assertFalse(data["fake_success"])
        self.assertFalse(data["secrets_returned"])
