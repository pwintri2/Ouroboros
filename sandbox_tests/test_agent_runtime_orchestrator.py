import tempfile
import threading
import time
import unittest
from pathlib import Path

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord
from controller.agent_runtime.orchestrator import AgentOrchestrator
from controller.agent_runtime.store import JobStore


class TestAgentOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-runtime-orchestrator-")
        self.addCleanup(self.tmp.cleanup)
        self.store = JobStore(
            runtime_root=Path(self.tmp.name) / "store",
            artifact_root=Path(self.tmp.name) / "out",
        )

    def _wait(self, predicate, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("predicate never became true")

    def test_create_job_writes_prompt_and_initial_event(self):
        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": lambda *a, **k: {"status": "completed"}})

        record = orchestrator.create_job("codex", "voeg test toe", timeout_seconds=15)

        self.assertEqual(record.agent, "codex")
        self.assertEqual(record.status, "queued")
        self.assertTrue(record.job_id.startswith("codex_"))
        self.assertTrue(Path(record.events_file).exists())
        self.assertTrue((Path(record.output_dir) / "prompt.md").exists())
        events = orchestrator.read_events(record.job_id)
        self.assertEqual(events[0]["type"], "created")

    def test_create_job_rejects_unknown_agent(self):
        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": lambda *a, **k: {}})

        with self.assertRaises(ValueError):
            orchestrator.create_job("mystery", "hi")

    def test_create_job_rejects_empty_task(self):
        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": lambda *a, **k: {}})

        with self.assertRaises(ValueError):
            orchestrator.create_job("codex", "   ")

    def test_submit_runs_adapter_in_background_and_marks_completed(self):
        ran = threading.Event()

        def adapter(job: JobRecord, log: EventLog, on_progress) -> dict:
            log.append("test_started", {"task": job.task})
            on_progress({"pid": 1234})
            ran.set()
            return {"status": "completed", "exit_code": 0, "response_preview": "done"}

        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": adapter})
        record = orchestrator.submit("codex", "do work", timeout_seconds=10)

        self.assertTrue(ran.wait(timeout=2))
        self._wait(lambda: (self.store.get(record.job_id) or {}).get("status") == "completed")
        final = self.store.get(record.job_id)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["exit_code"], 0)
        self.assertEqual(final["response_preview"], "done")
        self.assertEqual(final["pid"], 1234)
        result_payload = (Path(record.output_dir) / "result.json").read_text(encoding="utf-8")
        self.assertIn("completed", result_payload)
        events = orchestrator.read_events(record.job_id)
        types = [event["type"] for event in events]
        self.assertIn("created", types)
        self.assertIn("test_started", types)
        self.assertIn("status", types)

    def test_adapter_exception_marks_job_failed(self):
        def adapter(job, log, on_progress):
            raise RuntimeError("boom")

        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": adapter})
        record = orchestrator.submit("codex", "broken")

        self._wait(lambda: (self.store.get(record.job_id) or {}).get("status") == "failed")
        final = self.store.get(record.job_id)
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["result_summary"], "boom")
        events = [event["type"] for event in orchestrator.read_events(record.job_id)]
        self.assertIn("error", events)

    def test_cancel_sets_flag_and_marks_cancelled(self):
        release = threading.Event()
        observed = []

        def adapter(job, log, on_progress):
            check = getattr(job, "_cancel_check", lambda: False)
            for _ in range(50):
                if check():
                    observed.append("cancel-detected")
                    return {"status": "cancelled", "exit_code": None}
                time.sleep(0.02)
                if release.is_set():
                    break
            return {"status": "completed", "exit_code": 0}

        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": adapter})
        record = orchestrator.submit("codex", "run forever")
        # Wait until the worker thread starts polling.
        self._wait(lambda: (self.store.get(record.job_id) or {}).get("status") == "running")

        cancelled = orchestrator.cancel(record.job_id)
        self.assertIsNotNone(cancelled)
        self.assertTrue(cancelled["cancel_requested"])
        # Give the adapter loop time to detect the cancel flag before the safety
        # gate fires; otherwise the test races against the worker thread.
        try:
            self._wait(lambda: bool(observed) or (self.store.get(record.job_id) or {}).get("status") == "cancelled")
        finally:
            release.set()

        self._wait(lambda: (self.store.get(record.job_id) or {}).get("status") == "cancelled")
        self.assertEqual(observed, ["cancel-detected"])

    def test_supported_agents_reflects_registered_adapters(self):
        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": lambda *a, **k: {}})
        orchestrator.register_adapter("CLAUDE", lambda *a, **k: {})

        self.assertEqual(orchestrator.supported_agents(), ["claude", "codex"])

    def test_list_jobs_fails_stale_running_job_after_restart(self):
        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": lambda *a, **k: {}})
        record = orchestrator.create_job("codex", "stale worker", timeout_seconds=1)
        old = "2026-01-01T00:00:00Z"
        self.store.update(
            record.job_id,
            {
                "status": "running",
                "started_at": old,
                "updated_at": old,
                "finished_at": None,
                "result_summary": "",
                "response_preview": "",
            },
        )

        jobs = orchestrator.list_jobs(agent="codex")

        self.assertEqual(jobs[0]["status"], "failed")
        self.assertEqual(jobs[0]["result_summary"], "stale_running_after_runtime_restart")
        self.assertIn("geen levende backend-worker", jobs[0]["response_preview"])
        events = orchestrator.read_events(record.job_id)
        self.assertTrue(any(event["type"] == "stale_after_restart" for event in events))

    def test_list_jobs_keeps_live_running_job_with_cancel_flag(self):
        release = threading.Event()

        def slow_adapter(job, log, on_progress):
            release.wait(timeout=1)
            return {"status": "completed", "exit_code": 0}

        orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": slow_adapter})
        record = orchestrator.submit("codex", "still alive", timeout_seconds=1)
        self._wait(lambda: (self.store.get(record.job_id) or {}).get("status") == "running")
        old = "2026-01-01T00:00:00Z"
        self.store.update(record.job_id, {"started_at": old, "updated_at": old})

        try:
            jobs = orchestrator.list_jobs(agent="codex")
            self.assertEqual(jobs[0]["status"], "running")
        finally:
            release.set()
        self._wait(lambda: (self.store.get(record.job_id) or {}).get("status") == "completed")


if __name__ == "__main__":
    unittest.main()
