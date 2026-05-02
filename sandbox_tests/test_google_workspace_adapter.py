import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGoogleWorkspaceAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_token = os.environ.get("WINTRIP_GOOGLE_TOKEN_PATH")
        self.previous_live = os.environ.get("WINTRIP_ALLOW_LIVE_GOOGLE_API")
        self.tmp = tempfile.TemporaryDirectory(prefix="google-adapter-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        self.token_path = Path(self.tmp.name) / "google_token.json"
        self.token_path.write_text(
            json.dumps({"access_token": "secret-token", "scopes": ["drive.readonly"], "expiry": "2099-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        os.environ["WINTRIP_GOOGLE_TOKEN_PATH"] = str(self.token_path)
        os.environ.pop("WINTRIP_ALLOW_LIVE_GOOGLE_API", None)

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.previous_workspace)
        self._restore("WINTRIP_GOOGLE_TOKEN_PATH", self.previous_token)
        self._restore("WINTRIP_ALLOW_LIVE_GOOGLE_API", self.previous_live)

    def test_status_redacts_token_and_reports_connection(self):
        from controller.google_workspace_adapter import GoogleWorkspaceAdapter

        status = GoogleWorkspaceAdapter().status()
        self.assertEqual(status["status"], "connected")
        self.assertFalse(status["token"]["secrets_returned"])
        self.assertNotIn("secret-token", json.dumps(status))

    def test_fixture_drive_files_map_to_11d_records(self):
        from controller.google_workspace_adapter import GoogleWorkspaceAdapter

        adapter = GoogleWorkspaceAdapter(fixtures={"drive_files": [{"id": "1", "name": "Ouroboros Doc", "shared": True}]})
        result = adapter.list_drive_files()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "fixture")
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["records_11d"][0]["11d"]["vector"]), 11)

    def test_live_and_write_operations_are_approval_gated(self):
        from controller.google_workspace_adapter import GoogleWorkspaceAdapter

        adapter = GoogleWorkspaceAdapter(fixtures={})
        blocked_read = adapter.list_drive_files(approval="")
        self.assertEqual(blocked_read["status"], "blocked")
        blocked_write = adapter.send_gmail("user@example.com", "Subject", "Body", approval="")
        self.assertEqual(blocked_write["status"], "blocked")
        approved = adapter.send_gmail("user@example.com", "Subject", "Body", approval="Akkoord")
        self.assertEqual(approved["status"], "approval_recorded")
        self.assertFalse(approved["executed"])

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
