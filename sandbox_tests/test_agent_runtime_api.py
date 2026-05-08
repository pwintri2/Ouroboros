import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""

from sandbox_tests.test_api_ouroboros_phase1 import install_main_fakes, restore_modules


def load_main_with_fakes():
    previous_env = {
        "WINTRIP_DB_PATH": os.environ.get("WINTRIP_DB_PATH"),
        "WINTRIP_API_KEY_STORE": os.environ.get("WINTRIP_API_KEY_STORE"),
    }
    os.environ["WINTRIP_DB_PATH"] = tempfile.mkdtemp(prefix="agent-runtime-routes-")
    os.environ["WINTRIP_API_KEY_STORE"] = os.path.join(
        tempfile.mkdtemp(prefix="agent-runtime-keys-"), "keys.json"
    )
    previous_main = sys.modules.pop("controller.main", None)
    originals = install_main_fakes()
    try:
        import controller.main as main
    finally:
        restore_modules(originals)
    return main, previous_main, previous_env


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestAgentRuntimeRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main, cls.previous_main, cls.previous_env = load_main_with_fakes()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        sys.modules.pop("controller.main", None)
        if cls.previous_main is not None:
            sys.modules["controller.main"] = cls.previous_main
        for key, value in cls.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        self.runtime_tmp = tempfile.TemporaryDirectory(prefix="agent-runtime-routes-")
        self.addCleanup(self.runtime_tmp.cleanup)
        self.store = JobStore(
            runtime_root=Path(self.runtime_tmp.name) / "store",
            artifact_root=Path(self.runtime_tmp.name) / "out",
        )

        def fake_adapter(job, log, on_progress):
            log.append("adapter_test", {"task": job.task})
            return {"status": "completed", "exit_code": 0, "response_preview": "all good"}

        self.orchestrator = AgentOrchestrator(store=self.store, adapters={"codex": fake_adapter})
        self._previous_orchestrator = reset_orchestrator(self.orchestrator)
        self.addCleanup(lambda: reset_orchestrator(self._previous_orchestrator))

    def _wait_status(self, job_id: str, status: str, timeout: float = 2.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.store.get(job_id)
            if current and current.get("status") == status:
                return current
            time.sleep(0.02)
        raise AssertionError(f"job {job_id} never reached status {status!r}")

    def test_post_jobs_creates_and_starts_job(self):
        response = self.client.post(
            "/api/agent-runtime/jobs",
            json={"agent": "codex", "task": "voeg test toe", "timeout_seconds": 10},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "running")
        job_id = data["job"]["job_id"]
        self.assertTrue(job_id.startswith("codex_"))

        final = self._wait_status(job_id, "completed")
        self.assertEqual(final["exit_code"], 0)
        self.assertEqual(final["response_preview"], "all good")

    def test_get_jobs_lists_recent_jobs(self):
        self.client.post("/api/agent-runtime/jobs", json={"agent": "codex", "task": "first"})
        second = self.client.post("/api/agent-runtime/jobs", json={"agent": "codex", "task": "second"}).json()
        self._wait_status(second["job"]["job_id"], "completed")

        response = self.client.get("/api/agent-runtime/jobs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        tasks = [job["task"] for job in data["jobs"]]
        self.assertIn("first", tasks)
        self.assertIn("second", tasks)

    def test_get_job_detail_and_events(self):
        created = self.client.post("/api/agent-runtime/jobs", json={"agent": "codex", "task": "details"}).json()
        job_id = created["job"]["job_id"]
        self._wait_status(job_id, "completed")

        detail = self.client.get(f"/api/agent-runtime/jobs/{job_id}").json()
        self.assertEqual(detail["job"]["status"], "completed")

        events = self.client.get(f"/api/agent-runtime/jobs/{job_id}/events").json()
        types = [event["type"] for event in events["events"]]
        self.assertIn("created", types)
        self.assertIn("adapter_test", types)
        self.assertIn("status", types)

    def test_get_job_unknown_returns_404(self):
        response = self.client.get("/api/agent-runtime/jobs/nope")
        self.assertEqual(response.status_code, 404)

    def test_post_jobs_rejects_unknown_agent(self):
        response = self.client.post(
            "/api/agent-runtime/jobs",
            json={"agent": "mystery", "task": "noop"},
        )
        self.assertEqual(response.status_code, 400)

    def test_cancel_endpoint_marks_job_cancelled(self):
        import threading

        from controller.agent_runtime.orchestrator import AgentOrchestrator, reset_orchestrator
        from controller.agent_runtime.store import JobStore

        cancel_tmp = tempfile.TemporaryDirectory(prefix="agent-runtime-cancel-")
        self.addCleanup(cancel_tmp.cleanup)
        store = JobStore(
            runtime_root=Path(cancel_tmp.name) / "store",
            artifact_root=Path(cancel_tmp.name) / "out",
        )
        gate = threading.Event()
        finished = threading.Event()

        def slow_adapter(job, log, on_progress):
            check = getattr(job, "_cancel_check", lambda: False)
            for _ in range(200):
                if check():
                    finished.set()
                    return {"status": "cancelled", "exit_code": None}
                time.sleep(0.02)
                if gate.is_set():
                    break
            finished.set()
            return {"status": "completed", "exit_code": 0}

        slow_orch = AgentOrchestrator(store=store, adapters={"codex": slow_adapter})
        previous = reset_orchestrator(slow_orch)
        try:
            response = self.client.post("/api/agent-runtime/jobs", json={"agent": "codex", "task": "long"}).json()
            job_id = response["job"]["job_id"]
            # wait for adapter to start running
            for _ in range(100):
                current = store.get(job_id)
                if current and current.get("status") == "running":
                    break
                time.sleep(0.02)
            cancel_response = self.client.post(f"/api/agent-runtime/jobs/{job_id}/cancel")
            self.assertEqual(cancel_response.status_code, 200)
            self.assertTrue(cancel_response.json()["job"]["cancel_requested"])

            for _ in range(100):
                current = store.get(job_id)
                if current and current.get("status") == "cancelled":
                    break
                time.sleep(0.02)
            self.assertEqual(store.get(job_id)["status"], "cancelled")
        finally:
            gate.set()
            finished.wait(timeout=2)
            reset_orchestrator(previous)


if __name__ == "__main__":
    unittest.main()
