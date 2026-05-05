import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCodexStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = {
            "WINTRIP_CODEX_PATH": os.environ.get("WINTRIP_CODEX_PATH"),
            "CODEX_HOME": os.environ.get("CODEX_HOME"),
            "WINTRIP_CODEX_HOME": os.environ.get("WINTRIP_CODEX_HOME"),
            "WINTRIP_CODEX_BINARY": os.environ.get("WINTRIP_CODEX_BINARY"),
            "CODEX_BINARY": os.environ.get("CODEX_BINARY"),
        }

    def tearDown(self) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_repo_missing_status_is_truthful(self):
        from controller import codex_status as codex_status_module
        from controller.codex_status import codex_overall_status, discover_codex_capabilities

        with tempfile.TemporaryDirectory(prefix="codex-status-empty-") as tmp:
            missing = Path(tmp) / "no-codex-here"
            os.environ["WINTRIP_CODEX_PATH"] = str(missing)
            os.environ["CODEX_HOME"] = str(missing / "home")

            inventory = discover_codex_capabilities()
            self.assertEqual(inventory["status"], "missing")
            self.assertEqual(inventory["repo_path"], str(missing.resolve()))
            self.assertEqual(inventory["capabilities"], [])

            original_candidates = codex_status_module.candidate_binary_paths
            codex_status_module.candidate_binary_paths = lambda: [missing / "definitely-not-a-binary"]
            try:
                overall = codex_overall_status()
            finally:
                codex_status_module.candidate_binary_paths = original_candidates
            # When there's no binary and no repo, overall should report missing or discoverable.
            self.assertIn(overall["status"], {"missing", "discoverable"})
            self.assertFalse(overall["repo_present"])
            self.assertEqual(overall["fake_success"], False)
            self.assertNotIn(str(missing), str(overall.get("auth", {}).get("auth_path") or ""))

    def test_repo_present_capability_inventory_detects_subsystems(self):
        from controller.codex_status import discover_codex_capabilities

        with tempfile.TemporaryDirectory(prefix="codex-status-fake-repo-") as tmp:
            repo = Path(tmp) / "Codex"
            (repo / "codex-rs" / "cli").mkdir(parents=True)
            (repo / "codex-rs" / "mcp-server").mkdir(parents=True)
            (repo / "codex-rs" / "skills").mkdir(parents=True)
            (repo / "codex-rs" / "sandboxing").mkdir(parents=True)
            (repo / "codex-cli").mkdir(parents=True)
            (repo / "docs").mkdir(parents=True)
            (repo / "codex-rs" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
            (repo / "package.json").write_text('{"name":"codex"}', encoding="utf-8")

            os.environ["WINTRIP_CODEX_PATH"] = str(repo)

            inventory = discover_codex_capabilities()
            self.assertEqual(inventory["status"], "online")
            keys = {item["key"]: item for item in inventory["capabilities"]}

            self.assertTrue(keys["cli_exec"]["detected"])
            self.assertEqual(keys["cli_exec"]["invocation"], "local_cli")
            self.assertTrue(keys["mcp"]["detected"])
            self.assertEqual(keys["mcp"]["invocation"], "library_only")
            self.assertTrue(keys["skills"]["detected"])
            self.assertTrue(keys["sandboxing"]["detected"])
            self.assertTrue(keys["cli_npm"]["detected"])
            self.assertTrue(keys["docs"]["detected"])
            self.assertEqual(keys["docs"]["invocation"], "discoverable")

            # Subsystems that don't exist should not be marked detected.
            self.assertFalse(keys["realtime"]["detected"])
            self.assertEqual(keys["realtime"]["invocation"], "absent")

    def test_binary_missing_returns_clean_payload(self):
        from controller import codex_status as codex_status_module

        with tempfile.TemporaryDirectory(prefix="codex-binary-missing-") as tmp:
            os.environ["WINTRIP_CODEX_PATH"] = str(Path(tmp) / "no-codex")

            original_candidates = codex_status_module.candidate_binary_paths
            codex_status_module.candidate_binary_paths = lambda: [Path(tmp) / "definitely-not-a-binary"]
            try:
                result = codex_status_module.find_codex_binary()
            finally:
                codex_status_module.candidate_binary_paths = original_candidates
            self.assertEqual(result["status"], "missing")
            self.assertIsNone(result["path"])

    def test_auth_summary_does_not_leak_secret_payload(self):
        from controller.codex_status import codex_auth_summary

        with tempfile.TemporaryDirectory(prefix="codex-auth-") as tmp:
            home = Path(tmp) / ".codex"
            home.mkdir()
            (home / "auth.json").write_text(
                '{"OPENAI_API_KEY": "sk-supersecret123456789", "tokens": {"id_token": "ey..."}}',
                encoding="utf-8",
            )
            (home / "config.toml").write_text("[profile]\nname = 'me'\n", encoding="utf-8")
            os.environ["CODEX_HOME"] = str(home)

            summary = codex_auth_summary()
            self.assertEqual(summary["status"], "authenticated")
            self.assertTrue(summary["auth_present"])
            self.assertTrue(summary["config_present"])
            self.assertEqual(summary["auth_mode"], "api_key")
            text = str(summary)
            self.assertNotIn("sk-supersecret123456789", text)
            self.assertNotIn("ey..", text)


if __name__ == "__main__":
    unittest.main()
