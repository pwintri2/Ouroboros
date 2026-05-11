import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.api_key_store import (
    delete_provider_api_key,
    key_store_path,
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
                "DEEPSEEK_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "GEMINI_API_KEY": "",
                "XAI_API_KEY": "",
                "GROK_API_KEY": "",
                "MISTRAL_API_KEY": "",
                "BRAVE_SEARCH_API_KEY": "",
                "BRAVE_API_KEY": "",
                "GITHUB_TOKEN": "",
                "GH_TOKEN": "",
                "GITHUB_API_TOKEN": "",
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

        brave = save_provider_api_key("brave_search", "brave-test-secret-123456")
        self.assertEqual(brave["provider"], "brave")
        self.assertTrue(provider_key_status()["brave"]["configured"])
        self.assertEqual(load_provider_api_keys()["brave"], "brave-test-secret-123456")
        self.assertNotIn("brave-test-secret-123456", json.dumps(provider_key_status()))

        deepseek = save_provider_api_key("deekseek", "deepseek-test-secret-123456")
        self.assertEqual(deepseek["provider"], "deepseek")
        self.assertTrue(provider_key_status()["deepseek"]["configured"])
        self.assertEqual(load_provider_api_keys()["deepseek"], "deepseek-test-secret-123456")
        self.assertNotIn("deepseek-test-secret-123456", json.dumps(provider_key_status()))

        github = save_provider_api_key("gh", "github-test-secret-123456")
        self.assertEqual(github["provider"], "github")
        self.assertTrue(provider_key_status()["github"]["configured"])
        self.assertEqual(load_provider_api_keys()["github"], "github-test-secret-123456")
        self.assertNotIn("github-test-secret-123456", json.dumps(provider_key_status()))

    def test_rejects_short_or_unknown_keys(self):
        with self.assertRaises(ValueError):
            save_provider_api_key("openai", "short")
        with self.assertRaises(ValueError):
            save_provider_api_key("unknown", "long-enough-key")

    def test_default_store_path_prefers_current_workspace_over_host_workspace_mount(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="api-key-cwd-") as tmp:
            with patch.dict(
                os.environ,
                {
                    "WINTRIP_API_KEY_STORE": "",
                    "OUROBOROS_API_KEY_STORE": "",
                    "WINTRIP_WORKSPACE": "",
                    "WORKSPACE_ROOT": "",
                    "WINTRIP_PROJECT_ROOT": "",
                },
                clear=False,
            ):
                os.chdir(tmp)
                try:
                    self.assertEqual(key_store_path(), Path(tmp, ".secrets", "ouroboros_api_keys.json").resolve())
                finally:
                    os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
