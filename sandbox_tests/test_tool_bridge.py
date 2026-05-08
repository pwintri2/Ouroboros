import os
import tempfile
import unittest
from pathlib import Path

from controller.tool_bridge import ToolBridge
from ouroboros_esoteric.ouroboros_consciousness_loop import reset_living_ouroboros_loop
from ouroboros_esoteric.quantum_corruption_nexus import get_quantum_corruption_nexus


class TestToolBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tool-bridge-")
        self.addCleanup(self.tmp.cleanup)
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_bridge_url = os.environ.get("WINTRIP_RCLONE_BRIDGE_URL")
        self.old_bridge_token = os.environ.get("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", None)
        get_quantum_corruption_nexus().reset()
        reset_living_ouroboros_loop(None)

    def tearDown(self):
        reset_living_ouroboros_loop(None)
        self._restore("WINTRIP_WORKSPACE", self.old_workspace)
        self._restore("WINTRIP_RCLONE_BRIDGE_URL", self.old_bridge_url)
        self._restore("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", self.old_bridge_token)

    def test_read_file_uses_workspace_guard_and_528_firewall(self):
        Path(self.tmp.name, "README.md").write_text("bridge ok\n", encoding="utf-8")

        result = ToolBridge().run("read_file", {"path": "README.md"})

        self.assertEqual(result["status"], "success")
        self.assertIn("bridge ok", result["stdout"])
        self.assertTrue(result["firewall"]["resonant"])

    def test_write_file_requires_approval_and_logs_blocked_call(self):
        result = ToolBridge().run("write_file", {"path": "x.txt", "content": "x"})

        self.assertEqual(result["status"], "blocked")
        status = get_quantum_corruption_nexus().status()
        self.assertEqual(status["tool_rejections"], 1)
        self.assertEqual(status["sacred_corruptions"], 1)

    def test_non_528_frequency_rejects_before_dispatch(self):
        result = ToolBridge().run("read_file", {"path": "README.md", "frequency": 432.0})

        self.assertEqual(result["status"], "rejected")
        self.assertIn("528.0 Hz", result["reason"])

    def test_run_command_delegates_to_safe_shell_allowlist(self):
        result = ToolBridge().run("run_command", {"command": "pwd", "approval": "Akkoord"})

        self.assertEqual(result["status"], "success")
        self.assertIn(self.tmp.name, result["stdout"])

    def test_computer_registry_adds_list_search_and_test_actions(self):
        Path(self.tmp.name, "alpha.txt").write_text("needle\n", encoding="utf-8")
        Path(self.tmp.name, "test_sample.py").write_text(
            "import unittest\n\n"
            "class TestSample(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )

        listed = ToolBridge().run("list_files", {"path": "."})
        searched = ToolBridge().run("search_files", {"path": ".", "regex": "needle"})
        tested = ToolBridge().run("run_tests", {"selector": "test_sample", "approval": "Akkoord"})

        self.assertEqual(listed["status"], "success")
        self.assertIn("alpha.txt", listed["stdout"])
        self.assertEqual(searched["status"], "success")
        self.assertEqual(searched["result"]["count"], 1)
        self.assertEqual(tested["status"], "success")
        self.assertEqual(tested["result"]["test_command"], "python3 -m unittest test_sample")

    def test_safe_shell_alias_and_secret_redaction(self):
        Path(self.tmp.name, "leak.txt").write_text("token=supersecret123456\n", encoding="utf-8")

        shell = ToolBridge().run("safe_shell", {"command": "pwd", "approval": "Akkoord"})
        read = ToolBridge().run("read_file", {"path": "leak.txt"})

        self.assertEqual(shell["status"], "success")
        self.assertEqual(read["status"], "success")
        self.assertIn("token=[REDACTED]", read["stdout"])
        self.assertNotIn("supersecret123456", str(read))

    def test_status_exposes_computer_actions(self):
        status = ToolBridge().status()

        self.assertEqual(status["status"], "online")
        self.assertIn("list_files", status["tools"])
        self.assertIn("safe_shell", status["tools"])
        self.assertIn("run_tests", status["approval_required_for"])
        self.assertIn("computer_actions", status)
        self.assertFalse(status["secrets_returned"])

    @staticmethod
    def _restore(key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
