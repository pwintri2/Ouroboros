import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    FastAPI = None
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""


class TestCodexAgent(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="codex-agent-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_agent_remembers_and_recalls_chat_memory(self):
        from controller.codex_agent import codex_agent_chat, get_codex_agent_memory

        remembered = codex_agent_chat("onthoud: Philip wil browser-acties zichtbaar gelogd hebben.")
        self.assertEqual(remembered["status"], "success")
        self.assertEqual(remembered["tool"], "remember")

        recalled = codex_agent_chat("wat weet je nog over browser acties?")
        self.assertEqual(recalled["status"], "success")
        self.assertTrue(recalled["memory_matches"])

        memory = get_codex_agent_memory()
        self.assertEqual(memory["memory_count"], 1)

    def test_open_browser_returns_frontend_action_and_records_event(self):
        from controller.codex_agent import codex_agent_chat, get_codex_agent_status, record_frontend_event

        blocked = codex_agent_chat("open een browser naar https://example.com", approval="")
        self.assertEqual(blocked["status"], "approval_required")

        result = codex_agent_chat("open een browser naar https://example.com", approval="Akkoord")
        self.assertEqual(result["status"], "requires_frontend")
        self.assertEqual(result["frontend_action"]["type"], "open_url")

        recorded = record_frontend_event(result["action_id"], "opened", payload={"url": "https://example.com"})
        self.assertEqual(recorded["status"], "success")
        status = get_codex_agent_status()
        self.assertGreaterEqual(len(status["recent_events"]), 2)

    def test_safe_shell_and_capability_gap_are_real_artifacts(self):
        from controller.codex_agent import codex_agent_backlog_path, codex_agent_chat

        shell = codex_agent_chat("run: pwd", approval="Akkoord")
        self.assertEqual(shell["tool"], "safe_shell")
        self.assertEqual(shell["shell_result"]["status"], "success")

        gap = codex_agent_chat("maak een compleet nieuwe holografische planner", approval="Akkoord", auto_extend=True)
        self.assertEqual(gap["status"], "capability_gap")
        self.assertTrue(Path(codex_agent_backlog_path()).exists())
        self.assertEqual(gap["extension_plan"]["status"], "written")
        self.assertTrue(Path(gap["extension_plan"]["path"]).exists())

    def test_codex_runtime_is_approval_gated_and_submits_job(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore
        from controller.codex_agent import codex_agent_chat, get_codex_agent_status

        runtime_tmp = tempfile.TemporaryDirectory(prefix="codex-agent-runtime-")
        self.addCleanup(runtime_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(runtime_tmp.name) / "store",
            artifact_root=Path(runtime_tmp.name) / "out",
        )
        adapter_calls: list[tuple[str, dict]] = []

        def fake_adapter(job, log, on_progress):
            adapter_calls.append((job.task, dict(job.metadata)))
            log.append("test_codex_runtime", {"source": job.metadata.get("source")})
            return {"status": "completed", "exit_code": 0, "response_preview": "ok"}

        orchestrator = AgentOrchestrator(store=store, adapters={"codex": fake_adapter})
        previous = reset_orchestrator(orchestrator)
        self.addCleanup(lambda: reset_orchestrator(previous))

        blocked = codex_agent_chat("codex: voeg een test toe", approval="")
        self.assertEqual(blocked["status"], "approval_required")
        self.assertEqual(blocked["tool"], "codex_runtime")
        self.assertEqual(adapter_calls, [])

        planned = codex_agent_chat("codex: voeg een test toe", approval="Akkoord", execute=False)
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(adapter_calls, [])

        result = codex_agent_chat("codex: voeg een test toe", approval="Akkoord")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["tool"], "codex_runtime")
        self.assertIn("job", result)
        job_id = result["job"]["job_id"]
        for _ in range(50):
            if adapter_calls:
                break
            time.sleep(0.02)
        self.assertEqual(adapter_calls[0][0], "voeg een test toe")
        self.assertEqual(adapter_calls[0][1]["source"], "codex_agent")
        self.assertIn("prompt", adapter_calls[0][1])
        for _ in range(50):
            if (store.get(job_id) or {}).get("status") == "completed":
                break
            time.sleep(0.02)
        self.assertEqual((store.get(job_id) or {}).get("status"), "completed")
        self.assertIn("codex_runtime", get_codex_agent_status()["tools"])

    def test_secret_like_memory_is_redacted_before_persistence(self):
        from controller.codex_agent import codex_agent_chat, get_codex_agent_memory

        codex_agent_chat("onthoud: api_key=supersecret123456789", approval="")

        memory = get_codex_agent_memory()
        serialized = str(memory)
        self.assertIn("[REDACTED]", serialized)
        self.assertNotIn("supersecret123456789", serialized)


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestCodexAgentRoutes(unittest.TestCase):
    def test_agent_routes_are_registered(self):
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="codex-agent-routes-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                status = client.get("/trainer/codex/agent/status")
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.json()["fake_success"], False)

                chat = client.post(
                    "/trainer/codex/agent/chat",
                    json={"message": "onthoud: route-test geheugen", "approval": ""},
                )
                self.assertEqual(chat.status_code, 200)
                self.assertEqual(chat.json()["tool"], "remember")

                memory = client.get("/trainer/codex/agent/memory")
                self.assertEqual(memory.status_code, 200)
                self.assertEqual(memory.json()["memory_count"], 1)
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
