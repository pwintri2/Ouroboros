import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import slash_agent_router
from controller.slash_agent_router import handle_slash_command, parse_slash_command


class TestSlashAgentRouter(unittest.TestCase):
    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_preapproved = os.environ.get("WINTRIP_SANDBOX_PREAPPROVED")
        self.old_deepseek = os.environ.get("WINTRIP_DEEPSEEK_PATH")
        self.old_atlas = os.environ.get("WINTRIP_ATLAS_PATH")
        self.old_roo_code = os.environ.get("WINTRIP_ROO_CODE_PATH")
        self.old_bridge_url = os.environ.get("WINTRIP_RCLONE_BRIDGE_URL")
        self.old_bridge_token = os.environ.get("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
        self.old_openai_key = os.environ.get("OPENAI_API_KEY")
        self.tmp = tempfile.TemporaryDirectory(prefix="wintrip-slash-agent-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        os.environ["WINTRIP_DEEPSEEK_PATH"] = str(Path(self.tmp.name) / "deepseek")
        os.environ["WINTRIP_ATLAS_PATH"] = str(Path(self.tmp.name) / "atlas")
        os.environ["WINTRIP_ROO_CODE_PATH"] = str(Path(self.tmp.name) / "Roo-code")
        os.environ.pop("WINTRIP_SANDBOX_PREAPPROVED", None)
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", None)
        os.environ.pop("OPENAI_API_KEY", None)
        Path(self.tmp.name, "alpha.txt").write_text("hello slash roo\n", encoding="utf-8")
        Path(self.tmp.name, "deepseek", "docs").mkdir(parents=True)
        Path(self.tmp.name, "deepseek", "docs", "SUBAGENTS.md").write_text("# subagents\n", encoding="utf-8")
        Path(self.tmp.name, "atlas", "packages", "cli", "src").mkdir(parents=True)
        Path(self.tmp.name, "atlas", "packages", "cli", "src", "app.ts").write_text("// atlas\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.old_workspace)
        self._restore("WINTRIP_SANDBOX_PREAPPROVED", self.old_preapproved)
        self._restore("WINTRIP_DEEPSEEK_PATH", self.old_deepseek)
        self._restore("WINTRIP_ATLAS_PATH", self.old_atlas)
        self._restore("WINTRIP_ROO_CODE_PATH", self.old_roo_code)
        self._restore("WINTRIP_RCLONE_BRIDGE_URL", self.old_bridge_url)
        self._restore("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", self.old_bridge_token)
        self._restore("OPENAI_API_KEY", self.old_openai_key)

    def test_parse_slash_command(self):
        parsed = parse_slash_command("/codex voeg tests toe")

        self.assertEqual(parsed, {"command": "codex", "task": "voeg tests toe"})
        self.assertIsNone(parse_slash_command("gewone chat"))

    def test_agents_catalog(self):
        result = handle_slash_command("/agents")

        self.assertEqual(result["status"], "online")
        self.assertEqual(result["route"], "slash_agent")
        self.assertTrue(any(command.startswith("/codex") for command in result["commands"]))
        self.assertTrue(any(command.startswith("/deepseek") for command in result["commands"]))
        self.assertTrue(any(command.startswith("/atlas") for command in result["commands"]))

    def test_roo_read_uses_roo_adapter(self):
        result = handle_slash_command("/roo read alpha.txt", approval="Akkoord")

        self.assertEqual(result["agent"], "roo")
        self.assertEqual(result["tool"], "roo_read_file")
        self.assertEqual(result["status"], "success")
        self.assertIn("hello slash roo", result["roo_result"]["stdout"])

    def test_roo_agentic_task_requires_approval(self):
        result = handle_slash_command("/roo maak een plan", provider="ollama", model="llama3.2:latest")

        self.assertEqual(result["agent"], "roo")
        self.assertEqual(result["tool"], "roo_cli")
        self.assertEqual(result["route"], "roo_runtime")
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertIn("roo_cli", result["blocked_tools"])

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

    def test_deepseek_status_subcommand(self):
        result = handle_slash_command("/deepseek status")

        self.assertEqual(result["agent"], "deepseek")
        self.assertEqual(result["tool"], "deepseek_status")
        self.assertIn(result["status"], {"detected", "configured", "available", "missing"})
        self.assertIn("ecosystem_status", result)

    def test_atlas_capabilities_subcommand(self):
        result = handle_slash_command("/atlas capabilities")

        self.assertEqual(result["agent"], "atlas")
        self.assertEqual(result["tool"], "atlas_capabilities")
        self.assertEqual(result["status"], "success")
        self.assertIn("ecosystem_capabilities", result)

    def test_atlas_ask_without_approval_is_blocked(self):
        result = handle_slash_command("/atlas ask vat de status samen")

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])

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

    def test_roo_exec_dispatches_to_agent_runtime_with_selected_cockpit_model(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="roo-runtime-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        seen: list[dict] = []

        def fake_adapter(job, log, on_progress):
            seen.append(job.metadata)
            return {"status": "completed", "exit_code": 0, "response_preview": "roo ok"}

        orchestrator = AgentOrchestrator(store=store, adapters={"roo": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        result = handle_slash_command(
            "/roo maak een plan",
            approval="Akkoord",
            provider="ollama",
            model="llama3.2:latest",
        )

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["tool"], "roo_cli")
        self.assertEqual(result["route"], "roo_runtime")
        self.assertIn("job", result)
        job_id = result["job"]["job_id"]
        for _ in range(50):
            if seen:
                break
            time.sleep(0.02)
        self.assertEqual(seen[0]["cockpit_provider"], "ollama")
        self.assertEqual(seen[0]["cockpit_model"], "llama3.2:latest")
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "completed":
                break
            time.sleep(0.02)
        self.assertEqual((store.get(job_id) or {}).get("status"), "completed")

    def test_roo_slash_uses_selected_cloud_cockpit_model_when_key_exists(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        os.environ["OPENAI_API_KEY"] = "sk-test-roo-cloud-key"
        runtime_tmp = tempfile.TemporaryDirectory(prefix="roo-cloud-runtime-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        seen: list[dict] = []

        def fake_adapter(job, log, on_progress):
            seen.append(job.metadata)
            return {"status": "completed", "exit_code": 0, "response_preview": "roo cloud ok"}

        orchestrator = AgentOrchestrator(store=store, adapters={"roo": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        result = handle_slash_command(
            "/roo maak een cloud plan",
            approval="Akkoord",
            provider="openai",
            model="gpt-4.1",
        )

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["route"], "roo_runtime")
        self.assertFalse(result["local_only"])
        for _ in range(50):
            if seen:
                break
            time.sleep(0.02)
        self.assertEqual(seen[0]["cockpit_provider"], "openai")
        self.assertEqual(seen[0]["cockpit_model"], "gpt-4.1")
        self.assertEqual(seen[0]["roo_provider_map"]["roo_provider"], "openai-native")
        job_id = result["job"]["job_id"]
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "completed":
                break
            time.sleep(0.02)
        self.assertEqual((store.get(job_id) or {}).get("status"), "completed")

    def test_roo_slash_uses_roo_cloud_login_for_catalog_model_without_api_key(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="roo-cloud-auth-runtime-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        seen: list[dict] = []

        def fake_adapter(job, log, on_progress):
            seen.append(job.metadata)
            return {"status": "completed", "exit_code": 0, "response_preview": "roo cloud auth ok"}

        orchestrator = AgentOrchestrator(store=store, adapters={"roo": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))
        original_auth_ready = slash_agent_router._roo_cloud_auth_ready
        slash_agent_router._roo_cloud_auth_ready = lambda: True
        self.addCleanup(lambda: setattr(slash_agent_router, "_roo_cloud_auth_ready", original_auth_ready))

        result = handle_slash_command(
            "/roo maak een cloud plan",
            approval="Akkoord",
            provider="roo",
            model="anthropic/claude-sonnet-4.6",
        )

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["route"], "roo_runtime")
        self.assertFalse(result["local_only"])
        for _ in range(50):
            if seen:
                break
            time.sleep(0.02)
        self.assertEqual(seen[0]["cockpit_provider"], "roo")
        self.assertEqual(seen[0]["cockpit_model"], "anthropic/claude-sonnet-4.6")
        self.assertEqual(seen[0]["roo_provider_map"]["roo_provider"], "roo")

    def test_roo_slash_blocks_cloud_model_without_api_key(self):
        result = handle_slash_command(
            "/roo maak een cloud plan",
            approval="Akkoord",
            provider="openai",
            model="gpt-4.1",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["route"], "roo_runtime")
        self.assertTrue(result["configuration_required"])
        self.assertIn("API key", result["response"])

    def test_roo_jobs_subcommand_hides_completed_preview(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="roo-jobs-preview-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )

        def fake_adapter(job, log, on_progress):
            return {
                "status": "completed",
                "exit_code": 0,
                "response_preview": '{"type":"result","content":"FINAL CLEAN SUMMARY","events":[{"type":"assistant","content":"NOISY"}]}',
            }

        orchestrator = AgentOrchestrator(store=store, adapters={"roo": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        started = handle_slash_command("/roo doe iets", approval="Akkoord", provider="ollama", model="llama3.2:latest")
        job_id = started["job"]["job_id"]
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "completed":
                break
            time.sleep(0.02)

        result = handle_slash_command("/roo jobs")

        self.assertEqual(result["status"], "success")
        self.assertIn(job_id, result["response"])
        self.assertNotIn("FINAL CLEAN SUMMARY", result["response"])
        self.assertNotIn('"events"', result["response"])

    def test_roo_jobs_subcommand_shows_short_failed_reason(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="roo-jobs-failed-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )

        def fake_adapter(job, log, on_progress):
            return {"status": "failed", "exit_code": 1, "response_preview": "429"}

        orchestrator = AgentOrchestrator(store=store, adapters={"roo": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        started = handle_slash_command("/roo doe iets", approval="Akkoord", provider="ollama", model="llama3.2:latest")
        job_id = started["job"]["job_id"]
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "failed":
                break
            time.sleep(0.02)

        result = handle_slash_command("/roo jobs")

        self.assertEqual(result["status"], "success")
        self.assertIn(job_id, result["response"])
        self.assertIn("provider rate limit (HTTP 429)", result["response"])

    def test_roo_travel_question_uses_readonly_transit_tool_without_approval(self):
        calls = []

        class FakeRegistry:
            def run_tool(self, tool_name, args=None):
                calls.append((tool_name, dict(args or {})))
                return {
                    "status": "preview",
                    "tool_name": tool_name,
                    "stdout": "NS planner link fallback",
                    "stderr": "",
                    "result": {"planner_url": "https://www.ns.nl/reisplanner/#/", "authoritative": False},
                }

        with patch("controller.agent_tools.AgentToolRegistry", lambda: FakeRegistry()):
            result = handle_slash_command(
                "/roo vertrek Ermelo, aankomst Utrecht Centraal, aankomsttijd woensdag 07:40",
                provider="anthropic",
                model="claude-sonnet-4-6",
            )

        self.assertEqual(result["route"], "agentic_processor")
        self.assertEqual(result["tool"], "ns_travel_advice")
        self.assertEqual(result["status"], "preview")
        self.assertNotIn("approval_required", result)
        self.assertEqual(calls[0][0], "ns_travel_advice")
        self.assertEqual(calls[0][1]["from_station"], "Ermelo")
        self.assertEqual(calls[0][1]["to_station"], "Utrecht Centraal")
        self.assertEqual(calls[0][1]["time"], "07:40")
        self.assertTrue(calls[0][1]["search_for_arrival"])
        self.assertIn("NS planner link fallback", result["response"])

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

    def test_deepseek_dispatches_to_agent_runtime_when_launchable(self):
        from controller.agent_runtime.adapters import ecosystem_cli
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        runtime_tmp = tempfile.TemporaryDirectory(prefix="deepseek-runtime-test-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        adapter_calls: list[str] = []

        def fake_adapter(job, log, on_progress):
            adapter_calls.append(job.task)
            return {"status": "completed", "exit_code": 0, "response_preview": "deepseek ok"}

        orchestrator = AgentOrchestrator(store=store, adapters={"deepseek": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        original_status = ecosystem_cli.ecosystem_agent_status
        ecosystem_cli.ecosystem_agent_status = lambda agent, prefer_bridge=True: {
            "status": "available",
            "runtime_reachable": True,
            "root": os.environ["WINTRIP_DEEPSEEK_PATH"],
            "reason": "test launcher",
            "fake_success": False,
        }
        try:
            result = slash_agent_router.execute_host_agent_command(
                "deepseek",
                "maak context",
                approval="Akkoord",
                prefer_bridge=False,
            )
        finally:
            ecosystem_cli.ecosystem_agent_status = original_status

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["tool"], "deepseek_runtime")
        job_id = result["job"]["job_id"]
        for _ in range(50):
            if adapter_calls:
                break
            time.sleep(0.02)
        self.assertEqual(adapter_calls, ["maak context"])
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "completed":
                break
            time.sleep(0.02)
        self.assertEqual((store.get(job_id) or {}).get("status"), "completed")

    def _restore(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
