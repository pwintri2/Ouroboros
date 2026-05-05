import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCodexCapabilityDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = {
            "WINTRIP_CODEX_PATH": os.environ.get("WINTRIP_CODEX_PATH"),
            "WINTRIP_CODEX_ALLOWED_SUBDIRS": os.environ.get("WINTRIP_CODEX_ALLOWED_SUBDIRS"),
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
        }

    def tearDown(self) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _build_fake_codex_repo(self, root: Path) -> None:
        (root / "codex-rs" / "cli").mkdir(parents=True)
        (root / "codex-rs" / "tui").mkdir(parents=True)
        (root / "codex-rs" / "app-server").mkdir(parents=True)
        (root / "codex-rs" / "mcp-server").mkdir(parents=True)
        (root / "codex-rs" / "skills").mkdir(parents=True)
        (root / "codex-rs" / "sandboxing").mkdir(parents=True)
        (root / "codex-rs" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
        (root / "codex-cli").mkdir()
        (root / "docs").mkdir()
        (root / "scripts").mkdir()

    def test_layered_capability_inventory_reports_python_and_subsystems(self):
        from controller.codex_registry import get_codex_capability_inventory

        with tempfile.TemporaryDirectory(prefix="codex-cap-disc-") as tmp:
            repo = Path(tmp) / "Codex"
            self._build_fake_codex_repo(repo)
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            (repo / "scripts").mkdir(exist_ok=True)
            (repo / "scripts" / "echo_tools.py").write_text(
                textwrap.dedent(
                    """
                    def echo(value: str) -> str:
                        \"\"\"Return the input unchanged.\"\"\"
                        return value
                    """
                ),
                encoding="utf-8",
            )

            os.environ["WINTRIP_CODEX_PATH"] = str(repo)
            os.environ["WINTRIP_CODEX_ALLOWED_SUBDIRS"] = "scripts"
            os.environ["WINTRIP_WORKSPACE"] = str(workspace)

            inventory = get_codex_capability_inventory()
            self.assertEqual(inventory["status"], "online")
            self.assertEqual(inventory["fake_success"], False)
            self.assertEqual(inventory["repo_path"], str(repo.resolve()))

            # Python helpers from `scripts/`.
            python_layer = inventory["callable_python"]
            python_names = {fn["name"] for fn in python_layer["functions"]}
            self.assertIn("scripts.echo_tools.echo", python_names)
            self.assertGreaterEqual(python_layer["callable_count"], 1)

            # Repo subsystems.
            subsystems = {item["key"]: item for item in inventory["subsystems"]}
            self.assertIn("cli_exec", subsystems)
            self.assertTrue(subsystems["cli_exec"]["detected"])
            self.assertTrue(subsystems["app_mode"]["detected"])
            self.assertTrue(subsystems["mcp"]["detected"])
            self.assertTrue(subsystems["skills"]["detected"])
            self.assertTrue(subsystems["sandboxing"]["detected"])

            # cloud_tasks should not be flagged as locally invokable.
            self.assertFalse(subsystems["cloud_tasks"]["detected"])

    def test_inventory_handles_missing_repo_gracefully(self):
        from controller.codex_registry import get_codex_capability_inventory

        with tempfile.TemporaryDirectory(prefix="codex-cap-empty-") as tmp:
            os.environ["WINTRIP_CODEX_PATH"] = str(Path(tmp) / "nope")
            os.environ["WINTRIP_CODEX_ALLOWED_SUBDIRS"] = ""
            os.environ["WINTRIP_WORKSPACE"] = tmp

            inventory = get_codex_capability_inventory()
            self.assertEqual(inventory["status"], "missing")
            self.assertEqual(inventory["callable_python"]["callable_count"], 0)
            self.assertEqual(inventory["subsystems"], [])
            self.assertEqual(inventory["fake_success"], False)


if __name__ == "__main__":
    unittest.main()
