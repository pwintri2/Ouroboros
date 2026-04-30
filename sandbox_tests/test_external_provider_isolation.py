import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.groq_client import GroqClient
from controller.provider_router import (
    DISABLED_EXTERNAL_PROVIDER_STATUS,
    check_providers,
    disabled_external_provider_payload,
    route_claude,
    route_gemini,
)


class TestExternalProviderIsolation(unittest.TestCase):
    def assertDisabledText(self, text, provider):
        self.assertIn(DISABLED_EXTERNAL_PROVIDER_STATUS, text)
        self.assertIn(provider, text)
        self.assertIn("no", text.lower())
        self.assertIn("call was made", text)

    def test_gemini_and_claude_routes_do_not_call_cli(self):
        with patch("subprocess.run", side_effect=AssertionError("external CLI call attempted")) as run:
            gemini_text = route_gemini("hello", model="gemini-2.5-pro", system_prompt="system")
            claude_text = route_claude("hello", model="claude-opus-4-6", system_prompt="system")

        run.assert_not_called()
        self.assertDisabledText(gemini_text, "gemini")
        self.assertDisabledText(claude_text, "claude")

    def test_provider_status_reports_disabled_without_cli_probe(self):
        with patch("subprocess.run", side_effect=AssertionError("external CLI probe attempted")) as run:
            status = check_providers()

        run.assert_not_called()
        for provider in ("gemini", "claude", "groq"):
            self.assertIn(provider, status)
            self.assertEqual(status[provider]["status"], DISABLED_EXTERNAL_PROVIDER_STATUS)
            self.assertFalse(status[provider]["available"])
            self.assertFalse(status[provider]["enabled"])
            self.assertTrue(status[provider]["legacy"])
            self.assertIn("message", status[provider])

    def test_disabled_provider_payload_is_stable_and_explicit(self):
        payload = disabled_external_provider_payload("gemini", model="gemini-test", transport="cli")

        self.assertEqual(payload["status"], DISABLED_EXTERNAL_PROVIDER_STATUS)
        self.assertEqual(payload["provider"], "gemini")
        self.assertEqual(payload["model"], "gemini-test")
        self.assertEqual(payload["transport"], "cli")
        self.assertIn(DISABLED_EXTERNAL_PROVIDER_STATUS, payload["message"])
        self.assertIn("disabled", payload["reason"])

    def test_groq_chat_does_not_post_even_with_api_key(self):
        previous_key = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = "test-key-that-must-not-be-used"
        try:
            with patch("requests.post", side_effect=AssertionError("Groq HTTP call attempted")) as post:
                client = GroqClient()
                text = client.chat("hello", history=[{"role": "user", "content": "older"}], system_prompt="system")
                status = client.status()
        finally:
            if previous_key is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = previous_key

        post.assert_not_called()
        self.assertIn("CLOUD GROQ ERROR", text)
        self.assertDisabledText(text, "groq")
        self.assertEqual(status["status"], DISABLED_EXTERNAL_PROVIDER_STATUS)
        self.assertEqual(status["provider"], "groq")
        self.assertFalse(status["available"])


if __name__ == "__main__":
    unittest.main()
