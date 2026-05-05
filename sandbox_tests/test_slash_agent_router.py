import os
import tempfile
import time
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
        self.assertEqual(result["tool"], "codex_status")
        self.assertEqual(result["status"], "success")
        self.assertIn("codex_status", result)
        self.assertIn("repo_path", result["codex_status"])

    def test_codex_jobs_subcommand_lists_jobs(self):
        result = handle_slash_command("/codex jobs")

        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["tool"], "agent_jobs")

    def test_codex_capabilities_subcommand(self):
        result = handle_slash_command("/codex capabilities")

        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["tool"], "codex_capabilities")
        self.assertIn("codex_capabilities", result)
        self.assertIn("subsystems", result["codex_capabilities"])

    def test_agent_prompt_includes_redacted_self_context(self):
        original_status = slash_agent_router.get_self_context_status
        slash_agent_router.get_self_context_status = lambda: {
            "status": "online",
            "state_path": "/tmp/wintrip/.secrets/ouroboros_self_context.json",
            "conversation_count": 2,
            "lesson_count": 3,
            "latest_conversations": [
                {
                    "conversation_id": "cockpit-main",
                    "turn_count": 4,
                    "summary": "Philip vroeg Codex zichzelf te verbeteren.",
                }
            ],
            "recent_lessons": [
                {
                    "text": "Gebruik server-side context. api_key=supersecret123456789",
                    "keywords": ["codex", "self-context"],
                }
            ],
            "ruflo": {"status": "online", "path": "/home/pwintri2/ruflo"},
        }
        try:
            prompt = slash_agent_router._agent_prompt("Codex", "verbeter jezelf")
        finally:
            slash_agent_router.get_self_context_status = original_status

        self.assertIn("Ouroboros self-context", prompt)
        self.assertIn("Conversations: 2", prompt)
        self.assertIn("Lessons: 3", prompt)
        self.assertIn("cockpit-main", prompt)
        self.assertIn("Ruflo status: online", prompt)
        self.assertIn("[REDACTED]", prompt)
        self.assertNotIn("supersecret123456789", prompt)

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

    def test_codex_exec_dispatches_to_agent_runtime_instead_of_blocking(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="agent-runtime-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        adapter_calls: list[str] = []

        def fake_adapter(job, log, on_progress):
            adapter_calls.append(job.job_id)
            log.append("test", {"task": job.task})
            return {"status": "completed", "exit_code": 0, "response_preview": "ok"}

        orchestrator = AgentOrchestrator(store=store, adapters={"codex": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        original_exists = slash_agent_router._command_exists
        original_auth = slash_agent_router._codex_login_status
        slash_agent_router._command_exists = lambda name: name == "codex"
        slash_agent_router._codex_login_status = lambda: {"logged_in": True, "status": "success"}
        try:
            result = slash_agent_router._run_codex_exec("doe iets traags", timeout_seconds=30)
        finally:
            slash_agent_router._command_exists = original_exists
            slash_agent_router._codex_login_status = original_auth

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["tool"], "codex_exec")
        self.assertIn("Codex job", result["response"])
        self.assertIn("job", result)
        job_id = result["job"]["job_id"]
        self.assertTrue(job_id.startswith("codex_"))
        # Wait briefly for the worker thread the orchestrator started.
        for _ in range(50):
            if adapter_calls:
                break
            time.sleep(0.02)
        self.assertEqual(adapter_calls, [job_id])
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "completed":
                break
            time.sleep(0.02)
        self.assertEqual((store.get(job_id) or {}).get("status"), "completed")

    def test_ruflo_defaults_to_handoff_instead_of_host_cli(self):
        original_run = slash_agent_router._run_ruflo_swarm
        calls: list[str] = []

        def fake_ruflo(task: str, timeout_seconds: int):
            calls.append(task)
            return {"status": "success", "response": "ruflo ok"}

        slash_agent_router._run_ruflo_swarm = fake_ruflo
        try:
            result = slash_agent_router.execute_host_agent_command(
                "ruflo",
                "maak plan",
                approval="Akkoord",
                prefer_bridge=False,
            )

            self.assertEqual(result["status"], "handoff")
            self.assertEqual(result["tool"], "ruflo_handoff")
            self.assertIn("handoff", result)
            self.assertEqual(calls, [])
        finally:
            slash_agent_router._run_ruflo_swarm = original_run

    def test_bridge_transport_error_falls_back_to_handoff(self):
        original_bridge = slash_agent_router._bridge_agent_command
        original_run = slash_agent_router._run_claude_code
        calls: list[str] = []
        slash_agent_router._bridge_agent_command = lambda *args, **kwargs: {
            "status": "bridge_unavailable",
            "transport_error": True,
            "reason": "timeout",
        }

        def fake_claude(task: str, timeout_seconds: int):
            calls.append(task)
            return {"status": "success", "response": "claude ok"}

        slash_agent_router._run_claude_code = fake_claude
        try:
            result = slash_agent_router.execute_host_agent_command(
                "claude",
                "review code",
                approval="Akkoord",
                prefer_bridge=True,
            )

            self.assertEqual(result["status"], "handoff")
            self.assertEqual(result["tool"], "claude_handoff")
            self.assertIn("handoff", result)
            self.assertEqual(calls, [])
        finally:
            slash_agent_router._bridge_agent_command = original_bridge
            slash_agent_router._run_claude_code = original_run

    def test_runtime_host_agents_can_be_enabled_explicitly(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="ruflo-runtime-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        orchestrator = AgentOrchestrator(store=store, adapters={})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        old_runtime = os.environ.get("WINTRIP_SLASH_RUNTIME_HOST_AGENTS")
        os.environ["WINTRIP_SLASH_RUNTIME_HOST_AGENTS"] = "1"
        original_run = slash_agent_router._run_ruflo_swarm
        calls: list[str] = []

        def fake_ruflo(task: str, timeout_seconds: int):
            calls.append(task)
            return {"status": "success", "response": "ruflo ok"}

        slash_agent_router._run_ruflo_swarm = fake_ruflo
        try:
            result = slash_agent_router.execute_host_agent_command(
                "ruflo",
                "maak plan",
                approval="Akkoord",
                prefer_bridge=False,
            )
            self.assertEqual(result["status"], "running")
            self.assertEqual(result["tool"], "ruflo_runtime")
            for _ in range(50):
                if calls:
                    break
                time.sleep(0.02)
            self.assertEqual(calls, ["maak plan"])
            job_id = result["job"]["job_id"]
            for _ in range(50):
                if (store.get(job_id) or {}).get("status") == "completed":
                    break
                time.sleep(0.02)
            self.assertEqual((store.get(job_id) or {}).get("status"), "completed")
        finally:
            slash_agent_router._run_ruflo_swarm = original_run
            self._restore("WINTRIP_SLASH_RUNTIME_HOST_AGENTS", old_runtime)

    def _restore(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
