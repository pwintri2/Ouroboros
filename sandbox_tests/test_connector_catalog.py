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

from controller.connector_catalog import (
    APPROVAL_PHRASE,
    get_connector_catalog,
    is_tool_enabled,
    set_connector_enabled,
    set_tool_enabled,
)


class TestConnectorCatalog(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_settings_path = os.environ.get("WINTRIP_CONNECTOR_SETTINGS_PATH")
        self.tmp = tempfile.TemporaryDirectory(prefix="connector-catalog-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        os.environ.pop("WINTRIP_CONNECTOR_SETTINGS_PATH", None)

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.previous_workspace)
        self._restore("WINTRIP_CONNECTOR_SETTINGS_PATH", self.previous_settings_path)

    def test_catalog_has_user_facing_connector_surface_without_secrets(self):
        data = get_connector_catalog(include_status=False)

        ids = [connector["id"] for connector in data["connectors"]]
        self.assertIn("gmail", ids)
        self.assertIn("google_drive", ids)
        self.assertIn("microsoft_graph", ids)
        self.assertIn("sharepoint", ids)
        self.assertIn("browser_research", ids)
        self.assertIn("local_computer", ids)
        self.assertEqual(data["approval_phrase"], APPROVAL_PHRASE)
        self.assertFalse(data["secrets_returned"])
        self.assertFalse(data["fake_success"])
        self.assertNotIn("access_token", str(data).lower())

    def test_catalog_exposes_concrete_agent_work_packages(self):
        data = get_connector_catalog(include_status=False)
        packages = data["agent_work_packages"]

        self.assertEqual([item["agent"] for item in packages], ["Codex", "Web-Scout", "Communicator", "Criticus"])
        for package in packages:
            self.assertTrue(package["prompt"])
            self.assertTrue(package["scope"])
            self.assertTrue(package["acceptance"])
            self.assertIn("approval", package)
            self.assertNotIn("access_token", str(package).lower())

    def test_connector_toggle_requires_akkoord_and_blocks_tools(self):
        blocked = set_connector_enabled("gmail", enabled=False, approval="")
        self.assertEqual(blocked["status"], "blocked")

        updated = set_connector_enabled("gmail", enabled=False, approval=APPROVAL_PHRASE)
        self.assertEqual(updated["status"], "updated")
        gate = is_tool_enabled("gmail_search")
        self.assertFalse(gate["enabled"])
        self.assertEqual(gate["connector_id"], "gmail")

        status_gate = is_tool_enabled("gmail_status")
        self.assertTrue(status_gate["enabled"])
        self.assertTrue(status_gate["status_tool"])

    def test_connector_on_clears_stale_tool_overrides(self):
        set_tool_enabled("gmail_search", enabled=False, approval=APPROVAL_PHRASE)
        disabled = is_tool_enabled("gmail_search")
        self.assertFalse(disabled["enabled"])
        self.assertIn("Tool disabled", disabled["reason"])

        updated = set_connector_enabled("gmail", enabled=True, approval=APPROVAL_PHRASE)

        self.assertEqual(updated["status"], "updated")
        gate = is_tool_enabled("gmail_search")
        self.assertTrue(gate["enabled"])
        self.assertIsNone(gate["tool_override"])

    def test_status_tool_enable_is_already_on_not_blocked(self):
        result = set_tool_enabled("gmail_status", enabled=True, approval=APPROVAL_PHRASE)

        self.assertEqual(result["status"], "already_on")
        self.assertTrue(result["tool"]["enabled"])
        self.assertTrue(result["tool"]["status_tool"])

    def test_tool_override_can_disable_single_tool_inside_enabled_connector(self):
        updated = set_tool_enabled("safe_shell", enabled=False, approval=APPROVAL_PHRASE)

        self.assertEqual(updated["status"], "updated")
        safe_shell = is_tool_enabled("safe_shell")
        run_tests = is_tool_enabled("run_tests")
        self.assertFalse(safe_shell["enabled"])
        self.assertTrue(run_tests["enabled"])

    def test_agent_tools_respect_disabled_connector(self):
        from controller.agent_tools import AgentToolRegistry

        set_connector_enabled("gmail", enabled=False, approval=APPROVAL_PHRASE)
        result = AgentToolRegistry().run_tool("gmail_search", {"query": "in:inbox", "approval": APPROVAL_PHRASE})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["source"], "connector_catalog")
        self.assertEqual(result["approval_status"], "connector_disabled")
        self.assertFalse(result["result"]["executed"])

    def test_tool_bridge_respects_disabled_connector(self):
        from controller.tool_bridge import ToolBridge

        set_tool_enabled("safe_shell", enabled=False, approval=APPROVAL_PHRASE)
        result = ToolBridge().run("safe_shell", {"command": "pwd", "approval": APPROVAL_PHRASE})

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["firewall"]["connector_disabled"])
        self.assertFalse(result["fake_success"])

    @staticmethod
    def _restore(key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestConnectorRoutes(unittest.TestCase):
    def setUp(self):
        from controller.api.connector_routes import init_connector_routes

        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="connector-routes-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        app = FastAPI()
        init_connector_routes(app)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_routes_list_toggle_and_report_tool_gate(self):
        listing = self.client.get("/api/cockpit/connectors")
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.json()["connector_count"], 8)
        self.assertEqual(len(listing.json()["agent_work_packages"]), 4)

        blocked = self.client.post("/api/cockpit/connectors/gmail", json={"enabled": False, "approval": ""})
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(blocked.json()["status"], "blocked")

        updated = self.client.post("/api/cockpit/connectors/gmail", json={"enabled": False, "approval": APPROVAL_PHRASE})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "updated")

        gate = self.client.get("/api/cockpit/connectors/tools/gmail_search")
        self.assertEqual(gate.status_code, 200)
        self.assertFalse(gate.json()["tool"]["enabled"])


if __name__ == "__main__":
    unittest.main()
