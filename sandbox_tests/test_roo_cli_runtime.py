import os
import tempfile
import unittest
from pathlib import Path

from controller import roo_cli_runtime


class TestRooCliRuntime(unittest.TestCase):
    def setUp(self):
        self.old_binary = os.environ.get("WINTRIP_ROO_BINARY")
        self.old_workspace = os.environ.get("WINTRIP_HOST_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="roo-cli-runtime-")
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.fake_roo = root / "roo"
        self.fake_roo.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.fake_roo.chmod(0o755)
        os.environ["WINTRIP_ROO_BINARY"] = str(self.fake_roo)
        os.environ["WINTRIP_HOST_WORKSPACE"] = str(self.workspace)

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_ROO_BINARY", self.old_binary)
        self._restore("WINTRIP_HOST_WORKSPACE", self.old_workspace)

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def test_maps_cockpit_provider_to_roo_provider(self):
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("ollama", "llama3.2:latest")["roo_provider"], "ollama")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("openai", "gpt-4.1")["roo_provider"], "openai-native")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("google", "gemini-2.5-flash")["roo_provider"], "gemini")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("mistral", "mistral-large")["status"], "unsupported")

    def test_infers_roo_provider_from_selected_cockpit_model(self):
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "gpt-4.1"), "openai")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "claude-opus-4-6"), "anthropic")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "gemini-2.5-pro"), "google")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "llama3.2:latest"), "ollama")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "grok-3"), "xai")

    def test_build_command_uses_prompt_file_selected_model_and_no_api_key_arg(self):
        prompt_file = self.workspace / "prompt.md"
        prompt_file.write_text("doe iets", encoding="utf-8")

        payload = roo_cli_runtime.build_roo_command(
            prompt_file=prompt_file,
            workspace=self.workspace,
            cockpit_provider="ollama",
            model="llama3.2:latest",
        )

        self.assertEqual(payload["status"], "success")
        command = payload["command"]
        self.assertIn("--provider", command)
        self.assertIn("ollama", command)
        self.assertIn("--model", command)
        self.assertIn("llama3.2:latest", command)
        self.assertNotIn("--api-key", command)
        self.assertEqual(payload["provider_map"]["cockpit_provider"], "ollama")

    def test_openai_gpt_4_1_disables_roo_reasoning_effort(self):
        prompt_file = self.workspace / "prompt.md"
        prompt_file.write_text("doe iets", encoding="utf-8")

        payload = roo_cli_runtime.build_roo_command(
            prompt_file=prompt_file,
            workspace=self.workspace,
            cockpit_provider="openai",
            model="gpt-4.1",
        )

        self.assertEqual(payload["status"], "success")
        command = payload["command"]
        self.assertIn("--provider", command)
        self.assertIn("openai-native", command)
        self.assertIn("--reasoning-effort", command)
        index = command.index("--reasoning-effort")
        self.assertEqual(command[index + 1], "disabled")

    def test_classifies_openai_encrypted_content_error(self):
        category = roo_cli_runtime._classify_result(
            status="failed",
            exit_code=1,
            stderr="",
            details="Invalid request - Encrypted content is not supported with this model.",
        )

        self.assertEqual(category, "model_encrypted_content_unsupported")

    def test_run_blocks_without_exact_approval_before_binary_execution(self):
        result = roo_cli_runtime.run_roo_cli_task(
            task="wijzig bestand",
            provider="ollama",
            model="llama3.2:latest",
            approval="akkoord",
            workspace=self.workspace,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["fake_success"])

    def test_redacts_secret_like_values(self):
        redacted = roo_cli_runtime.redact("OPENAI_API_KEY=sk-test-secret-123456 token: abcdefghijklmnop")

        self.assertIn("[REDACTED]", redacted)
        self.assertNotIn("sk-test-secret", redacted)
        self.assertNotIn("abcdefghijklmnop", redacted)


if __name__ == "__main__":
    unittest.main()
