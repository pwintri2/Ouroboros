import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAgentSIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_path = os.environ.get("WINTRIP_AGENTS_PATH")

    def tearDown(self) -> None:
        if self.previous_path is None:
            os.environ.pop("WINTRIP_AGENTS_PATH", None)
        else:
            os.environ["WINTRIP_AGENTS_PATH"] = self.previous_path

    def test_status_missing_when_root_absent(self):
        from controller.agent_runtime.adapters.agents_cli import agents_status

        with tempfile.TemporaryDirectory(prefix="agents-missing-") as tmp:
            os.environ["WINTRIP_AGENTS_PATH"] = str(Path(tmp) / "no-agents")
            status = agents_status()
            self.assertEqual(status["status"], "missing")
            self.assertEqual(status["entrypoints_verified"], 0)
            self.assertFalse(status["root_exists"])
            self.assertEqual(status["fake_success"], False)

    def test_repo_only_status_does_not_claim_available(self):
        from controller.agent_runtime.adapters.agents_cli import agents_status

        with tempfile.TemporaryDirectory(prefix="agents-detected-") as tmp:
            root = Path(tmp) / "AgentS"
            (root / "gui_agents").mkdir(parents=True)
            os.environ["WINTRIP_AGENTS_PATH"] = str(root)
            status = agents_status()
            # No cli_app.py module exists, so status must not claim runtime_reachable.
            self.assertFalse(status["runtime_reachable"])
            self.assertNotEqual(status["status"], "available")
            self.assertNotEqual(status["status"], "online")
            self.assertEqual(status["fake_success"], False)

    def test_capabilities_lists_only_present_paths(self):
        from controller.agent_runtime.adapters.agents_cli import discover_capabilities

        with tempfile.TemporaryDirectory(prefix="agents-caps-") as tmp:
            root = Path(tmp) / "AgentS"
            (root / "gui_agents" / "s2_5").mkdir(parents=True)
            (root / "gui_agents" / "s2_5" / "cli_app.py").write_text("pass\n", encoding="utf-8")
            (root / "integrations").mkdir()
            os.environ["WINTRIP_AGENTS_PATH"] = str(root)

            inventory = discover_capabilities()
            self.assertIn("gui_agents", inventory["capabilities"])
            self.assertIn("integrations", inventory["capabilities"])
            self.assertIn("s2_5", inventory["variants"])


if __name__ == "__main__":
    unittest.main()
