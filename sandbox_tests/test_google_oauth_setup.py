import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

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

from controller.google_oauth_setup import (
    DEFAULT_GOOGLE_SCOPES,
    exchange_google_oauth_code,
    google_oauth_client_path,
    google_oauth_status,
    store_google_oauth_callback_code,
    start_google_oauth_flow,
)


APPROVAL = "Akkoord"
VALID_CLIENT_ID = "123456789012-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com"


class _FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestGoogleOAuthSetup(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_token_path = os.environ.get("WINTRIP_GOOGLE_TOKEN_PATH")
        self.previous_client_path = os.environ.get("WINTRIP_GOOGLE_OAUTH_CLIENT_PATH")
        self.tmp = tempfile.TemporaryDirectory(prefix="google-oauth-setup-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        os.environ.pop("WINTRIP_GOOGLE_TOKEN_PATH", None)
        os.environ.pop("WINTRIP_GOOGLE_OAUTH_CLIENT_PATH", None)

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.previous_workspace)
        self._restore("WINTRIP_GOOGLE_TOKEN_PATH", self.previous_token_path)
        self._restore("WINTRIP_GOOGLE_OAUTH_CLIENT_PATH", self.previous_client_path)

    def test_status_is_safe_without_token(self):
        status = google_oauth_status()

        self.assertEqual(status["status"], "not_configured")
        self.assertFalse(status["setup_ready"])
        self.assertFalse(status["can_send_gmail"])
        self.assertFalse(status["secrets_returned"])
        self.assertEqual(set(status["missing_scopes"]), set(DEFAULT_GOOGLE_SCOPES))
        self.assertNotIn("access_token", str(status).lower())

    def test_start_requires_akkoord_and_stores_client_without_returning_secret(self):
        blocked = start_google_oauth_flow(client_id=VALID_CLIENT_ID, client_secret="secret-abc", approval="")
        self.assertEqual(blocked["status"], "blocked")

        result = start_google_oauth_flow(client_id=VALID_CLIENT_ID, client_secret="secret-abc", approval=APPROVAL)

        self.assertEqual(result["status"], "authorization_url_ready")
        self.assertIn("access_type=offline", result["authorization_url"])
        self.assertIn(".apps.googleusercontent.com", result["authorization_url"])
        self.assertTrue(google_oauth_client_path().exists())
        self.assertNotIn("secret-abc", str(result))
        self.assertFalse(result["secrets_returned"])

    def test_start_blocks_malformed_client_id_before_google_401(self):
        result = start_google_oauth_flow(client_id="project-id-not-client", client_secret="secret-abc", approval=APPROVAL)

        self.assertEqual(result["status"], "blocked")
        self.assertIn(".apps.googleusercontent.com", result["reason"])
        self.assertFalse(google_oauth_client_path().exists())

    def test_start_accepts_downloaded_google_client_json(self):
        client_json = json.dumps(
            {
                "installed": {
                    "client_id": VALID_CLIENT_ID,
                    "project_id": "ouroboros-project",
                    "client_secret": "secret-abc",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )

        result = start_google_oauth_flow(client_id="", client_secret="", client_json=client_json, approval=APPROVAL)

        self.assertEqual(result["status"], "authorization_url_ready")
        self.assertTrue(result["project_id_configured"])
        self.assertEqual(result["client_type"], "installed")
        self.assertNotIn("secret-abc", str(result))

    def test_exchange_code_saves_token_and_redacts_response(self):
        start_google_oauth_flow(client_id=VALID_CLIENT_ID, client_secret="secret-abc", approval=APPROVAL)
        fake_payload = {
            "access_token": "access-abc",
            "refresh_token": "refresh-abc",
            "expires_in": 3600,
            "scope": " ".join(DEFAULT_GOOGLE_SCOPES),
            "token_type": "Bearer",
        }

        with patch("controller.google_oauth_setup.urllib.request.urlopen", return_value=_FakeHTTPResponse(fake_payload)):
            result = exchange_google_oauth_code(code="http://127.0.0.1/callback?code=code-123&scope=x", approval=APPROVAL)

        self.assertEqual(result["status"], "token_saved")
        self.assertTrue(result["token_saved"])
        self.assertTrue(result["has_refresh_token"])
        self.assertTrue(result["can_send_gmail"])
        self.assertFalse(result["secrets_returned"])
        self.assertNotIn("access-abc", str(result))
        self.assertNotIn("refresh-abc", str(result))
        self.assertNotIn("secret-abc", str(result))

    def test_pending_callback_code_can_be_exchanged_without_returning_code(self):
        start_google_oauth_flow(client_id=VALID_CLIENT_ID, client_secret="secret-abc", approval=APPROVAL)
        stored = store_google_oauth_callback_code(code="http://127.0.0.1/callback?code=callback-code")
        status = google_oauth_status()
        fake_payload = {
            "access_token": "access-abc",
            "refresh_token": "refresh-abc",
            "expires_in": 3600,
            "scope": " ".join(DEFAULT_GOOGLE_SCOPES),
            "token_type": "Bearer",
        }

        self.assertEqual(stored["status"], "stored")
        self.assertTrue(status["pending_code"]["available"])
        self.assertEqual(status["last_exchange"]["status"], "never")
        self.assertNotIn("callback-code", str(status))

        with patch("controller.google_oauth_setup.urllib.request.urlopen", return_value=_FakeHTTPResponse(fake_payload)):
            result = exchange_google_oauth_code(code="", use_pending_code=True, approval=APPROVAL)

        self.assertEqual(result["status"], "token_saved")
        final_status = google_oauth_status()
        self.assertFalse(final_status["pending_code"]["available"])
        self.assertEqual(final_status["last_exchange"]["status"], "token_saved")
        self.assertNotIn("callback-code", str(result))

    def test_exchange_error_is_visible_without_secrets(self):
        start_google_oauth_flow(client_id=VALID_CLIENT_ID, client_secret="secret-abc", approval=APPROVAL)
        store_google_oauth_callback_code(code="http://127.0.0.1/callback?code=callback-code")

        result = exchange_google_oauth_code(code="", use_pending_code=True, approval="")
        status = google_oauth_status()

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(status["last_exchange"]["status"], "blocked")
        self.assertIn("Akkoord", status["last_exchange"]["reason"])
        self.assertNotIn("callback-code", str(status))
        self.assertNotIn("secret-abc", str(status))

    @staticmethod
    def _restore(key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestGoogleOAuthRoutes(unittest.TestCase):
    def setUp(self):
        from controller.api.google_oauth_routes import init_google_oauth_routes

        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="google-oauth-routes-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        app = FastAPI()
        init_google_oauth_routes(app)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_oauth_routes_status_and_start(self):
        status = self.client.get("/api/cockpit/connectors/google/oauth/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "not_configured")

        start = self.client.post(
            "/api/cockpit/connectors/google/oauth/start",
            json={"client_id": VALID_CLIENT_ID, "client_secret": "secret-abc", "approval": APPROVAL},
        )
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.json()["status"], "authorization_url_ready")
        self.assertNotIn("secret-abc", str(start.json()))

    def test_callback_route_stores_pending_code_without_echoing_it(self):
        response = self.client.get("/api/cockpit/connectors/google/oauth/callback?code=callback-code")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Save Callback Code", response.text)
        self.assertNotIn("callback-code", response.text)
        status = self.client.get("/api/cockpit/connectors/google/oauth/status").json()
        self.assertTrue(status["pending_code"]["available"])
        self.assertNotIn("callback-code", str(status))


if __name__ == "__main__":
    unittest.main()
