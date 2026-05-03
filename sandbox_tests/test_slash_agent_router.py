import os
import tempfile
import unittest
from pathlib import Path

from controller import slash_agent_router
from controller.slash_agent_router import handle_slash_command, parse_slash_command


class TestSlashAgentRouter(unittest.TestCase):
    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_preapproved = os.environ.get("WINTRIP_SANDBOX_PREAPPROVED")
        self.tmp = tempfile.TemporaryDirectory(prefix="wintrip-slash-agent-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        os.environ.pop("WINTRIP_SANDBOX_PREAPPROVED", None)
        Path(self.tmp.name, "alpha.txt").write_text("hello slash roo\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.old_workspace)
        self._restore("WINTRIP_SANDBOX_PREAPPROVED", self.old_preapproved)

    def test_parse_slash_command(self):
        parsed = parse_slash_command("/codex voeg tests toe")

        self.assertEqual(parsed, {"command": "codex", "task": "voeg tests toe"})
        self.assertIsNone(parse_slash_command("gewone chat"))

    def test_agents_catalog(self):
        result = handle_slash_command("/agents")

        self.assertEqual(result["status"], "online")
        self.assertEqual(result["route"], "slash_agent")
        self.assertTrue(any(command.startswith("/codex") for command in result["commands"]))

    def test_roo_read_uses_roo_adapter(self):
        result = handle_slash_command("/roo read alpha.txt", approval="Akkoord")

        self.assertEqual(result["agent"], "roo")
        self.assertEqual(result["tool"], "roo_read_file")
        self.assertEqual(result["status"], "success")
        self.assertIn("hello slash roo", result["roo_result"]["stdout"])

    def test_codex_without_approval_is_blocked(self):
        result = handle_slash_command("/codex wijzig niets")

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])

    def test_codex_status_does_not_require_approval(self):
        result = handle_slash_command("/codex status")

        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["tool"], "agent_jobs")
        self.assertEqual(result["status"], "success")

    def test_codex_login_status_accepts_stderr_output(self):
        original_exists = slash_agent_router._command_exists
        original_run = slash_agent_router._run_command
        slash_agent_router._command_exists = lambda name: name == "codex"
        slash_agent_router._run_command = lambda *args, **kwargs: {
            "status": "success",
            "stdout": "",
            "stderr": "Logged in using ChatGPT\n",
        }
        try:
            status = slash_agent_router._codex_login_status()
        finally:
            slash_agent_router._command_exists = original_exists
            slash_agent_router._run_command = original_run

        self.assertTrue(status["logged_in"])

    def test_codex_exec_returns_running_instead_of_blocking_forever(self):
        original_exists = slash_agent_router._command_exists
        original_auth = slash_agent_router._codex_login_status
        original_popen = slash_agent_router.subprocess.Popen
        original_monitor = slash_agent_router._monitor_agent_process
        original_foreground = slash_agent_router._codex_foreground_seconds

        class FakePopen:
            pid = 12345

            def wait(self, timeout=None):
                raise slash_agent_router.subprocess.TimeoutExpired("codex", timeout)

        slash_agent_router._command_exists = lambda name: name == "codex"
        slash_agent_router._codex_login_status = lambda: {"logged_in": True, "status": "success"}
        slash_agent_router.subprocess.Popen = lambda *args, **kwargs: FakePopen()
        slash_agent_router._monitor_agent_process = lambda *args, **kwargs: None
        slash_agent_router._codex_foreground_seconds = lambda: 1
        try:
            result = slash_agent_router._run_codex_exec("doe iets traags", timeout_seconds=30)
        finally:
            slash_agent_router._command_exists = original_exists
            slash_agent_router._codex_login_status = original_auth
            slash_agent_router.subprocess.Popen = original_popen
            slash_agent_router._monitor_agent_process = original_monitor
            slash_agent_router._codex_foreground_seconds = original_foreground

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["tool"], "codex_exec")
        self.assertIn("/Codex status", result["response"])

    def _restore(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
