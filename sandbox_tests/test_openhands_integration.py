import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestOpenHandsIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_path = os.environ.get("WINTRIP_OPENHANDS_PATH")
        self.previous_url = os.environ.get("WINTRIP_OPENHANDS_SERVER_URL")
        # Point at an unreachable URL so server_probe returns missing during tests.
        os.environ["WINTRIP_OPENHANDS_SERVER_URL"] = "http://127.0.0.1:1"

    def tearDown(self) -> None:
        for key, value in (
            ("WINTRIP_OPENHANDS_PATH", self.previous_path),
            ("WINTRIP_OPENHANDS_SERVER_URL", self.previous_url),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_status_missing_when_root_absent(self):
        from controller.agent_runtime.adapters.openhands_adapter import openhands_status

        with tempfile.TemporaryDirectory(prefix="openhands-missing-") as tmp:
            os.environ["WINTRIP_OPENHANDS_PATH"] = str(Path(tmp) / "no-openhands")
            status = openhands_status()
            self.assertEqual(status["status"], "missing")
            self.assertFalse(status["root_exists"])
            self.assertFalse(status["server_reachable"])
            self.assertEqual(status["fake_success"], False)

    def test_repo_only_status_does_not_claim_online(self):
        from controller.agent_runtime.adapters.openhands_adapter import openhands_status

        with tempfile.TemporaryDirectory(prefix="openhands-detected-") as tmp:
            root = Path(tmp) / "OpenHands"
            (root / "openhands").mkdir(parents=True)
            (root / "openhands" / "__init__.py").write_text("syntax error here :(", encoding="utf-8")
            os.environ["WINTRIP_OPENHANDS_PATH"] = str(root)

            status = openhands_status()
            self.assertNotEqual(status["status"], "online")
            self.assertFalse(status["server_reachable"])
            # Either degraded (import failed) or detected — never online.
            self.assertIn(status["status"], {"detected", "configured", "degraded", "available"})

    def test_capabilities_lists_present_subsystems(self):
        from controller.agent_runtime.adapters.openhands_adapter import discover_capabilities

        with tempfile.TemporaryDirectory(prefix="openhands-caps-") as tmp:
            root = Path(tmp) / "OpenHands"
            (root / "openhands").mkdir(parents=True)
            (root / "frontend").mkdir()
            (root / "config.template.toml").write_text("[server]\n", encoding="utf-8")
            os.environ["WINTRIP_OPENHANDS_PATH"] = str(root)

            inventory = discover_capabilities()
            self.assertIn("openhands", inventory["capabilities"])
            self.assertIn("frontend", inventory["capabilities"])
            self.assertIn("config.template.toml", inventory["capabilities"])


if __name__ == "__main__":
    unittest.main()
