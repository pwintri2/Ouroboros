import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

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

    def test_send_gmail_reports_disabled_gmail_api_as_configuration_required(self):
        from controller.google_workspace_adapter import GoogleWorkspaceAdapter

        body = {
            "error": {
                "code": 403,
                "message": "Gmail API has not been used in project 550556174730 before or it is disabled.",
                "status": "PERMISSION_DENIED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "SERVICE_DISABLED",
                        "domain": "googleapis.com",
                        "metadata": {
                            "activationUrl": "https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=550556174730",
                            "serviceTitle": "Gmail API",
                        },
                    }
                ],
            }
        }
        class _Body:
            def read(self):
                return json.dumps(body).encode("utf-8")

            def close(self):
                return None

        error = HTTPError(
            url="https://gmail.googleapis.com",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=_Body(),
        )

        with patch("controller.google_workspace_adapter.urllib.request.urlopen", side_effect=error):
            result = GoogleWorkspaceAdapter(live_api_enabled=True).send_gmail("user@example.com", "Subject", "Body", approval="Akkoord")

        self.assertEqual(result["status"], "configuration_required")
        self.assertFalse(result["executed"])
        self.assertTrue(result["google_error"]["configuration_required"])
        self.assertIn("gmail.googleapis.com", result["activation_url"])
        self.assertNotIn("secret-token", json.dumps(result))

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
