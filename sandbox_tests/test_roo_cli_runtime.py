import os
import json
import tempfile
import unittest
from pathlib import Path

from controller import roo_cli_runtime


class TestRooCliRuntime(unittest.TestCase):
    def setUp(self):
        self.old_binary = os.environ.get("WINTRIP_ROO_BINARY")
        self.old_workspace = os.environ.get("WINTRIP_HOST_WORKSPACE")
        self.old_subscription_store = os.environ.get("WINTRIP_SUBSCRIPTION_STORE")
        self.old_api_key_store = os.environ.get("WINTRIP_API_KEY_STORE")
        self.old_openai_key = os.environ.get("OPENAI_API_KEY")
        self.tmp = tempfile.TemporaryDirectory(prefix="roo-cli-runtime-")
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.fake_roo = root / "roo"
        self.fake_roo.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.fake_roo.chmod(0o755)
        os.environ["WINTRIP_ROO_BINARY"] = str(self.fake_roo)
        os.environ["WINTRIP_HOST_WORKSPACE"] = str(self.workspace)
        os.environ["WINTRIP_SUBSCRIPTION_STORE"] = str(root / "subscriptions.json")
        os.environ["WINTRIP_API_KEY_STORE"] = str(root / "api_keys.json")
        os.environ.pop("OPENAI_API_KEY", None)
        roo_cli_runtime._ROO_MODELS_CACHE["ts"] = 0.0
        roo_cli_runtime._ROO_MODELS_CACHE["payload"] = None

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_ROO_BINARY", self.old_binary)
        self._restore("WINTRIP_HOST_WORKSPACE", self.old_workspace)
        self._restore("WINTRIP_SUBSCRIPTION_STORE", self.old_subscription_store)
        self._restore("WINTRIP_API_KEY_STORE", self.old_api_key_store)
        self._restore("OPENAI_API_KEY", self.old_openai_key)
        roo_cli_runtime._ROO_MODELS_CACHE["ts"] = 0.0
        roo_cli_runtime._ROO_MODELS_CACHE["payload"] = None

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def test_maps_cockpit_provider_to_roo_provider(self):
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("ollama", "llama3.2:latest")["roo_provider"], "ollama")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("openai", "gpt-4.1")["roo_provider"], "openai-native")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("google", "gemini-2.5-flash")["roo_provider"], "gemini")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("roo", "anthropic/claude-opus-4.7")["roo_provider"], "roo")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("mistral", "mistral-large")["status"], "unsupported")

    def test_infers_roo_provider_from_selected_cockpit_model(self):
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "gpt-4.1"), "openai")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "claude-opus-4-6"), "anthropic")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "gemini-2.5-pro"), "google")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "anthropic/claude-opus-4.7"), "roo")
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

    def test_public_command_redacts_api_key_arg(self):
        public = roo_cli_runtime.public_command(["roo", "--api-key", "sk-test-secret-1234567890", "--model", "gpt-4.1"])

        self.assertEqual(public[public.index("--api-key") + 1], "[REDACTED]")
        self.assertNotIn("sk-test-secret", json.dumps(public))

    def test_roo_cloud_models_reads_catalog_without_returning_secrets(self):
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"list\" ] && [ \"$2\" = \"models\" ]; then\n"
            "  printf '{\"models\":{\"anthropic/claude-opus-4.7\":{},\"roo/code-supernova\":{}}}\\n'\n"
            "  exit 0\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)

        result = roo_cli_runtime.roo_cloud_models(timeout_seconds=2)

        self.assertEqual(result["status"], "online")
        self.assertIn("anthropic/claude-opus-4.7", result["models"])
        self.assertIn("roo/code-supernova", result["models"])
        self.assertFalse(result["secrets_returned"])

    def test_run_resolves_subscription_key_into_roo_env(self):
        from controller.subscription_store import save_subscription

        secret = "sk-subscription-test-1234567890"
        save_subscription("openai", auth_mode="api_key_from_subscription", api_key=secret)
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            f"if [ \"$OPENAI_API_KEY\" != \"{secret}\" ]; then echo missing_key >&2; exit 7; fi\n"
            "printf '{\"result\":\"ok\"}\\n'\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)

        result = roo_cli_runtime.run_roo_cli_task(
            task="test subscription key",
            provider="openai",
            model="gpt-4.1",
            approval="Akkoord",
            workspace=self.workspace,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["api_key_source"], "subscription")
        self.assertTrue(result["api_key_available"])
        self.assertNotIn(secret, json.dumps(result))

    def test_run_extracts_roo_json_content_before_tail_truncation(self):
        self.fake_roo.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "payload = {\n"
            "  'type': 'result',\n"
            "  'success': True,\n"
            "  'content': 'FINAL ROO ANSWER',\n"
            "  'events': [{'type': 'tool_use', 'content': 'x' * 25000}, {'type': 'assistant', 'content': 'FINAL EVENT'}],\n"
            "}\n"
            "print(json.dumps(payload))\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)

        result = roo_cli_runtime.run_roo_cli_task(
            task="test large roo json",
            provider="ollama",
            model="llama3.2:latest",
            approval="Akkoord",
            workspace=self.workspace,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["response_preview"], "FINAL ROO ANSWER")
        self.assertIsInstance(result["parsed_output"], dict)

    def test_classifies_openai_encrypted_content_error(self):
        category = roo_cli_runtime._classify_result(
            status="failed",
            exit_code=1,
            stderr="",
            details="Invalid request - Encrypted content is not supported with this model.",
        )

        self.assertEqual(category, "model_encrypted_content_unsupported")

    def test_roo_auth_login_returns_oauth_url_for_frontend(self):
        auth_url = "https://app.roocode.com/cli/sign-in?state=test&callback=http%3A%2F%2F127.0.0.1%3A49152%2Fcallback"
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo 'roo 1.0.0'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"status\" ]; then echo 'Authenticated as test@example.com'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"login\" ]; then\n"
            "  echo 'Opening browser for authentication...'\n"
            f"  echo \"If the browser doesn't open, visit: {auth_url}\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)

        result = roo_cli_runtime.roo_auth_login(approval="Akkoord", timeout_seconds=2)

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["logged_in"])
        self.assertEqual(result["auth_url"], auth_url)
        self.assertEqual(result["frontend_action"]["type"], "open_url")
        self.assertEqual(result["frontend_action"]["url"], auth_url)
        self.assertIn("[AUTH_URL]", result["stdout_summary"])
        self.assertNotIn(auth_url, result["stdout_summary"])

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
