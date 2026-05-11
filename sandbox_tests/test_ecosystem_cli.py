import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestEcosystemCliRuntimeEnv(unittest.TestCase):
    def test_deepseek_runtime_env_uses_cockpit_saved_key_without_env_key(self):
        from controller.agent_runtime.adapters import ecosystem_cli
        from controller.api_key_store import save_provider_api_key

        with tempfile.TemporaryDirectory(prefix="ecosystem-cli-keys-") as tmp:
            store_path = Path(tmp) / "keys.json"
            with patch.dict(os.environ, {"WINTRIP_API_KEY_STORE": str(store_path)}, clear=False):
                os.environ.pop("DEEPSEEK_API_KEY", None)
                save_provider_api_key("deepseek", "sk-deepseek-runtime-test-123456")

                env = ecosystem_cli.runtime_env()

        self.assertEqual(env.get("DEEPSEEK_API_KEY"), "sk-deepseek-runtime-test-123456")

    def test_existing_deepseek_env_key_takes_precedence(self):
        from controller.agent_runtime.adapters import ecosystem_cli

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-existing-env-key-123456"}, clear=False):
            env = ecosystem_cli.runtime_env()

        self.assertEqual(env.get("DEEPSEEK_API_KEY"), "sk-existing-env-key-123456")

    def test_completed_deepseek_json_prompt_with_api_key_guardrail_is_not_auth_missing(self):
        from controller.agent_runtime.adapters.ecosystem_cli import classify_result

        stdout = (
            '{"status":"completed","output":"ping","prompt":"Schrijf geen API keys, '
            'OAuth tokens of browser session data naar bestanden/logs."}'
        )

        self.assertEqual(classify_result("completed", 0, stdout, "", False), "ok")

    def test_real_deepseek_auth_error_is_still_auth_missing(self):
        from controller.agent_runtime.adapters.ecosystem_cli import classify_result

        stderr = "Failed to send message: DeepSeek API key not found."

        self.assertEqual(classify_result("completed", 0, "", stderr, False), "auth_missing")

    def test_cli_output_text_prefers_clean_output_field(self):
        from controller.agent_runtime.adapters.ecosystem_cli import _cli_output_text

        payload = {
            "status": "completed",
            "output": "ping",
            "prompt": "lange systeemcontext",
        }

        self.assertEqual(_cli_output_text(payload), "ping")


if __name__ == "__main__":
    unittest.main()
