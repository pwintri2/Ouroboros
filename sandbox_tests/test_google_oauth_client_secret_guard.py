"""Guard against accidental overwrites of a saved Google OAuth client_secret."""

import unittest

from controller.google_oauth_setup import _resolve_client_config


VALID_CLIENT_ID = "550556174730-abcdef.apps.googleusercontent.com"
VALID_SECRET = "GOCSPX-1234567890abcdefghij"


class ClientSecretGuardTests(unittest.TestCase):
    def test_empty_input_falls_back_to_saved(self):
        result = _resolve_client_config(
            client_id="",
            client_secret="",
            saved_client={
                "client_id": VALID_CLIENT_ID,
                "client_secret": VALID_SECRET,
                "redirect_uri": "http://127.0.0.1:8010/callback",
                "scopes": ["https://www.googleapis.com/auth/gmail.send"],
            },
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["client_secret"], VALID_SECRET)

    def test_short_input_with_long_saved_is_blocked(self):
        result = _resolve_client_config(
            client_id=VALID_CLIENT_ID,
            client_secret="xy",
            saved_client={
                "client_id": VALID_CLIENT_ID,
                "client_secret": VALID_SECRET,
            },
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Refusing to overwrite", result["reason"])

    def test_short_input_without_saved_is_blocked_with_invalid_reason(self):
        result = _resolve_client_config(
            client_id=VALID_CLIENT_ID,
            client_secret="ab",
            saved_client={"client_id": VALID_CLIENT_ID},
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("less than 8 characters", result["reason"])

    def test_valid_input_succeeds(self):
        new_secret = "GOCSPX-newvalueXYZ123"
        result = _resolve_client_config(
            client_id=VALID_CLIENT_ID,
            client_secret=new_secret,
            saved_client={"client_id": VALID_CLIENT_ID, "client_secret": VALID_SECRET},
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["client_secret"], new_secret)

    def test_missing_both_id_and_secret_is_blocked(self):
        result = _resolve_client_config(
            client_id="",
            client_secret="",
            saved_client={},
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("required", result["reason"])


if __name__ == "__main__":
    unittest.main()
