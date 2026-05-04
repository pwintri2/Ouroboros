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
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        get_quantum_corruption_nexus().reset()
        reset_living_ouroboros_loop(None)

    def tearDown(self):
        reset_living_ouroboros_loop(None)
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace

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


if __name__ == "__main__":
    unittest.main()
