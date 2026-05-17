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

    def test_maps_cockpit_provider_to_chatgpt_provider_with_local_fallback(self):
        ollama_selection = roo_cli_runtime.map_cockpit_provider("ollama", "llama3.2:latest")
        self.assertEqual(ollama_selection["roo_provider"], "openai-native")
        self.assertEqual(ollama_selection["cockpit_provider"], "openai")
        self.assertEqual(ollama_selection["cockpit_model"], "gpt-4.1-mini")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("openai", "gpt-4.1")["roo_provider"], "openai-native")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("google", "gemini-2.5-flash")["roo_provider"], "openai-native")
        roo_oauth = roo_cli_runtime.map_cockpit_provider("roo", "anthropic/claude-opus-4.7")
        self.assertEqual(roo_oauth["roo_provider"], "roo")
        self.assertEqual(roo_oauth["cockpit_model"], "anthropic/claude-opus-4.7")
        openrouter = roo_cli_runtime.map_cockpit_provider("openrouter", "openai/gpt-oss-120b")
        self.assertEqual(openrouter["roo_provider"], "openai-native")
        self.assertEqual(openrouter["model_override"], "gpt-4.1-mini")
        self.assertEqual(openrouter["forced_model"], "gpt-4.1-mini")
        fallback = roo_cli_runtime.map_cockpit_provider("ollama", "deepseek-coder:latest")
        self.assertEqual(fallback["roo_provider"], "ollama")
        self.assertEqual(fallback["model_override"], "deepseek-coder:latest")
        self.assertEqual(roo_cli_runtime.map_cockpit_provider("mistral", "mistral-large")["status"], "mapped")

    def test_infers_roo_provider_from_selected_cockpit_model(self):
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "gpt-4.1"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "claude-opus-4-6"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "gemini-2.5-pro"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "anthropic/claude-opus-4.7"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "llama3.2:latest"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "openai/gpt-oss-120b"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("roo", "grok-3"), "roo")
        self.assertEqual(roo_cli_runtime.cockpit_provider_for_roo_selection("ollama", "deepseek-coder:latest"), "ollama")

    def test_build_command_uses_chatgpt_model_and_no_api_key_arg(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-roo-openai-key"
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
        self.assertIn("openai-native", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-4.1-mini", command)
        self.assertNotIn("llama3.2:latest", command)
        self.assertNotIn("--api-key", command)
        self.assertEqual(command[command.index("--reasoning-effort") + 1], "disable")
        self.assertEqual(payload["provider_map"]["cockpit_provider"], "openai")
        self.assertEqual(payload["provider_map"]["forced_model"], "gpt-4.1-mini")

    def test_build_command_can_use_roo_oauth_provider_without_api_key_arg(self):
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo 'roo 1.0.0'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"status\" ]; then echo 'Authenticated as test@example.com'; exit 0; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)
        prompt_file = self.workspace / "prompt.md"
        prompt_file.write_text("doe iets", encoding="utf-8")

        payload = roo_cli_runtime.build_roo_command(
            prompt_file=prompt_file,
            workspace=self.workspace,
            cockpit_provider="roo",
            model="anthropic/claude-opus-4.6",
        )

        self.assertEqual(payload["status"], "success")
        command = payload["command"]
        self.assertIn("roo", command)
        self.assertIn("anthropic/claude-opus-4.6", command)
        self.assertNotIn("--api-key", command)
        self.assertEqual(payload["provider_map"]["roo_provider"], "roo")

    def test_openrouter_command_is_replaced_by_chatgpt_openai(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-roo-openai-key"
        prompt_file = self.workspace / "prompt.md"
        prompt_file.write_text("doe iets", encoding="utf-8")

        payload = roo_cli_runtime.build_roo_command(
            prompt_file=prompt_file,
            workspace=self.workspace,
            cockpit_provider="openrouter",
            model="openai/gpt-oss-120b",
        )

        self.assertEqual(payload["status"], "success")
        command = payload["command"]
        self.assertIn("--provider", command)
        self.assertIn("openai-native", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-4.1-mini", command)
        self.assertNotIn("openrouter", command)
        self.assertEqual(payload["provider_map"]["replaced_provider"], "openrouter")
        self.assertEqual(payload["provider_map"]["forced_provider"], "openai")

    def test_openai_selection_uses_local_fallback_without_key(self):
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
        self.assertIn("ollama", command)
        self.assertIn("deepseek-coder:latest", command)
        self.assertNotIn("openai-native", command)
        self.assertIn("fallback_reason", payload["provider_map"])
        self.assertNotIn("--reasoning-effort", command)

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

    def test_run_uses_subscription_key_for_chatgpt_roo_model(self):
        from controller.subscription_store import save_subscription

        secret = "sk-subscription-test-1234567890"
        save_subscription("openai", auth_mode="api_key_from_subscription", api_key=secret)
        self.fake_roo.write_text(
            "#!/bin/sh\n"
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
        self.assertEqual(result["provider_map"]["forced_model"], "gpt-4.1-mini")
        self.assertIn("gpt-4.1", result["command"])
        self.assertIn("openai-native", result["command"])
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

    def test_run_retries_rate_limited_roo_once(self):
        old_retries = os.environ.get("WINTRIP_ROO_RATE_LIMIT_RETRIES")
        old_sleep = os.environ.get("WINTRIP_ROO_RATE_LIMIT_MAX_SLEEP")
        os.environ["WINTRIP_ROO_RATE_LIMIT_RETRIES"] = "1"
        os.environ["WINTRIP_ROO_RATE_LIMIT_MAX_SLEEP"] = "0"
        self.addCleanup(lambda: self._restore("WINTRIP_ROO_RATE_LIMIT_RETRIES", old_retries))
        self.addCleanup(lambda: self._restore("WINTRIP_ROO_RATE_LIMIT_MAX_SLEEP", old_sleep))
        count_file = self.workspace / "attempts.txt"
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo 'roo 1.0.0'; exit 0; fi\n"
            "if [ \"$1\" = \"list\" ]; then printf '{\"models\":{}}\\n'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ]; then echo 'Not authenticated'; exit 0; fi\n"
            f"COUNT_FILE='{count_file}'\n"
            "count=0\n"
            "[ -f \"$COUNT_FILE\" ] && count=$(cat \"$COUNT_FILE\")\n"
            "count=$((count + 1))\n"
            "echo \"$count\" > \"$COUNT_FILE\"\n"
            "if [ \"$count\" -eq 1 ]; then\n"
            "  echo 'Rate limit reached for gpt-4.1-mini tokens per min. Please try again in 0s.' >&2\n"
            "  exit 1\n"
            "fi\n"
            "printf '{\"result\":\"ok after retry\"}\\n'\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)

        result = roo_cli_runtime.run_roo_cli_task(
            task="test rate limit retry",
            provider="ollama",
            model="deepseek-coder:latest",
            approval="Akkoord",
            workspace=self.workspace,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual([attempt["category"] for attempt in result["attempts"]], ["rate_limited", "ok"])
        self.assertEqual(count_file.read_text(encoding="utf-8").strip(), "2")

    def test_roo_auth_login_returns_oauth_url_for_frontend(self):
        auth_url = "https://app.roocode.com/cli/sign-in?state=test&callback=http%3A%2F%2F127.0.0.1%3A49152%2Fcallback"
        auth_flag = self.workspace / "roo-authenticated.flag"
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo 'roo 1.0.0'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"status\" ]; then\n"
            f"  if [ -f \"{auth_flag}\" ]; then echo 'Authenticated as test@example.com'; else echo 'Not authenticated'; fi\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"login\" ]; then\n"
            "  echo 'Opening browser for authentication...'\n"
            f"  echo \"If the browser doesn't open, visit: {auth_url}\"\n"
            f"  touch \"{auth_flag}\"\n"
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

    def test_roo_auth_login_skips_browserflow_when_already_authenticated(self):
        self.fake_roo.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo 'roo 1.0.0'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"status\" ]; then echo 'Authenticated as test@example.com'; exit 0; fi\n"
            "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"login\" ]; then echo 'unexpected login' >&2; exit 99; fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        self.fake_roo.chmod(0o755)

        result = roo_cli_runtime.roo_auth_login(approval="Akkoord", timeout_seconds=2)

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["logged_in"])
        self.assertEqual(result["auth_url"], "")
        self.assertIsNone(result["frontend_action"])
        self.assertIn("al ingelogd", result["reason"])

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
