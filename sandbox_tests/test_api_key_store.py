import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.api_key_store import (
    delete_provider_api_key,
    load_provider_api_keys,
    provider_key_status,
    save_provider_api_key,
)


class TestApiKeyStore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tempdir.name) / "keys.json"
        self.env = patch.dict(
            os.environ,
            {
                "WINTRIP_API_KEY_STORE": str(self.store_path),
                "OPENAI_API_KEY": "",
                "ANTHROPIC_API_KEY": "",
                "CLAUDE_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "GEMINI_API_KEY": "",
                "XAI_API_KEY": "",
                "GROK_API_KEY": "",
                "MISTRAL_API_KEY": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tempdir.cleanup()

    def test_save_load_mask_and_delete_provider_key_without_returning_secret(self):
        saved = save_provider_api_key("grok", "grok-test-secret-123456")

        self.assertEqual(saved["provider"], "xai")
        self.assertTrue(saved["configured"])
        self.assertEqual(saved["source"], "store")
        self.assertNotIn("grok-test-secret-123456", json.dumps(saved))
        self.assertEqual(load_provider_api_keys()["xai"], "grok-test-secret-123456")
        self.assertEqual(oct(self.store_path.stat().st_mode & 0o777), "0o600")

        status = provider_key_status()
        self.assertTrue(status["xai"]["configured"])
        self.assertNotIn("grok-test-secret-123456", json.dumps(status))

        deleted = delete_provider_api_key("xai")
        self.assertFalse(deleted["configured"])
        self.assertNotIn("xai", load_provider_api_keys())

    def test_rejects_short_or_unknown_keys(self):
        with self.assertRaises(ValueError):
            save_provider_api_key("openai", "short")
        with self.assertRaises(ValueError):
            save_provider_api_key("unknown", "long-enough-key")


if __name__ == "__main__":
    unittest.main()
