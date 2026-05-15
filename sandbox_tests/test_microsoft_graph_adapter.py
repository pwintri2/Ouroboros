import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMicrosoftGraphAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_token = os.environ.get("WINTRIP_MICROSOFT_GRAPH_TOKEN_PATH")
        self.previous_live = os.environ.get("WINTRIP_ALLOW_LIVE_MICROSOFT_GRAPH")
        self.tmp = tempfile.TemporaryDirectory(prefix="graph-adapter-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        self.token_path = Path(self.tmp.name) / "graph_token.json"
        self.token_path.write_text(
            json.dumps({"access_token": "secret-token", "scopes": ["User.Read"], "tenant_id": "tenant-1"}),
            encoding="utf-8",
        )
        os.environ["WINTRIP_MICROSOFT_GRAPH_TOKEN_PATH"] = str(self.token_path)
        os.environ.pop("WINTRIP_ALLOW_LIVE_MICROSOFT_GRAPH", None)

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.previous_workspace)
        self._restore("WINTRIP_MICROSOFT_GRAPH_TOKEN_PATH", self.previous_token)
        self._restore("WINTRIP_ALLOW_LIVE_MICROSOFT_GRAPH", self.previous_live)

    def test_status_redacts_token(self):
        from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

        status = MicrosoftGraphAdapter().status()
        self.assertEqual(status["status"], "connected")
        self.assertFalse(status["token"]["secrets_returned"])
        self.assertNotIn("secret-token", json.dumps(status))

    def test_fixtures_return_11d_records(self):
        from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

        adapter = MicrosoftGraphAdapter(
            fixtures={
                "teams": [{"id": "team-1", "displayName": "Ouroboros"}],
                "outlook_messages": [{"id": "msg-1", "subject": "Hallo", "bodyPreview": "read-only"}],
            }
        )
        teams = adapter.list_teams()
        outlook = adapter.read_outlook_messages(max_results=1)
        self.assertEqual(teams["status"], "success")
        self.assertEqual(teams["source"], "fixture")
        self.assertEqual(len(teams["records_11d"][0]["11d"]["vector"]), 11)
        self.assertEqual(outlook["status"], "success")
        self.assertEqual(outlook["operation"], "outlook_messages")
        self.assertEqual(outlook["count"], 1)

    def test_live_reads_and_power_automate_are_approval_gated(self):
        from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

        adapter = MicrosoftGraphAdapter(fixtures={})
        self.assertEqual(adapter.get_me(approval="")["status"], "blocked")
        self.assertEqual(adapter.read_outlook_messages(approval="")["status"], "blocked")
        blocked = adapter.run_power_automate_flow("flow-1", approval="")
        self.assertEqual(blocked["status"], "blocked")
        approved = adapter.run_power_automate_flow("flow-1", approval="Akkoord")
        self.assertEqual(approved["status"], "approval_recorded")
        self.assertFalse(approved["executed"])

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
