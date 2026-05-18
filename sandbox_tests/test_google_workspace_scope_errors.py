"""Verify Google API scope-insufficient errors surface a re-login hint."""

import io
import json
import unittest
import urllib.error

from controller.google_workspace_adapter import (
    _google_error_details,
    GoogleWorkspaceAdapter,
)


def _build_http_error(payload: dict) -> urllib.error.HTTPError:
    body = json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError(
        url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=io.BytesIO(body),
    )


class GoogleErrorDetailsTests(unittest.TestCase):
    def test_scope_insufficient_sets_re_login_required_for_gmail_search(self):
        exc = _build_http_error(
            {
                "error": {
                    "code": 403,
                    "message": "Request had insufficient authentication scopes.",
                    "status": "PERMISSION_DENIED",
                    "errors": [{"reason": "insufficientPermissions", "domain": "global"}],
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                            "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
                            "domain": "googleapis.com",
                            "metadata": {"service": "gmail.googleapis.com"},
                        }
                    ],
                }
            }
        )
        details = _google_error_details(exc, operation="search_gmail")
        self.assertTrue(details["re_login_required"])
        self.assertEqual(details["missing_scope"], "https://www.googleapis.com/auth/gmail.readonly")
        self.assertTrue(details["configuration_required"])
        self.assertIn("Re-connect Google", details["next_action"])
        self.assertEqual(details["oauth_start_endpoint"], "/api/cockpit/connectors/google/oauth/start")

    def test_service_disabled_does_not_set_re_login_required(self):
        exc = _build_http_error(
            {
                "error": {
                    "code": 403,
                    "message": "Gmail API has not been used in project 123 before or it is disabled.",
                    "status": "PERMISSION_DENIED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                            "reason": "SERVICE_DISABLED",
                            "domain": "googleapis.com",
                            "metadata": {
                                "service": "gmail.googleapis.com",
                                "activationUrl": "https://console.developers.google.com/apis/api/gmail.googleapis.com/overview",
                            },
                        }
                    ],
                }
            }
        )
        details = _google_error_details(exc, operation="search_gmail")
        self.assertFalse(details["re_login_required"])
        self.assertTrue(details["configuration_required"])
        self.assertIn("Enable", details["next_action"])
        self.assertTrue(details["activation_url"])

    def test_status_reports_missing_capability_scopes(self):
        adapter = GoogleWorkspaceAdapter()

        def fake_token_metadata() -> dict:
            return {
                "exists": True,
                "path": "/tmp/fake_token.json",
                "scopes": ["https://www.googleapis.com/auth/gmail.send"],
                "expires_at": "",
                "secrets_returned": False,
            }

        adapter._token_metadata = fake_token_metadata  # type: ignore[attr-defined]
        status = adapter.status()
        self.assertTrue(status["re_login_required"])
        self.assertFalse(status["capability_ready"]["gmail_search"])
        self.assertTrue(status["capability_ready"]["gmail_send"])
        self.assertIn(
            "https://www.googleapis.com/auth/gmail.readonly",
            status["missing_capability_scopes"],
        )

    def test_status_no_re_login_when_all_scopes_present(self):
        adapter = GoogleWorkspaceAdapter()

        def fake_token_metadata() -> dict:
            return {
                "exists": True,
                "path": "/tmp/fake_token.json",
                "scopes": [
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.send",
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/drive.metadata.readonly",
                ],
                "expires_at": "",
                "secrets_returned": False,
            }

        adapter._token_metadata = fake_token_metadata  # type: ignore[attr-defined]
        status = adapter.status()
        self.assertFalse(status["re_login_required"])
        self.assertEqual(status["missing_capability_scopes"], [])


if __name__ == "__main__":
    unittest.main()
