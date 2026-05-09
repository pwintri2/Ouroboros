import tempfile
import unittest
from pathlib import Path

from controller.agent_runtime.adapters import roo_cli
from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord


class TestRooCliAdapter(unittest.TestCase):
    def test_bridge_transport_error_in_container_fails_without_local_fallback(self):
        tmp = tempfile.TemporaryDirectory(prefix="roo-cli-adapter-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        job = JobRecord(
            job_id="roo_test",
            agent="roo",
            task="doe iets",
            workspace_root=str(root),
            output_dir=str(root),
            stdout_file=str(root / "stdout.log"),
            stderr_file=str(root / "stderr.log"),
            output_file=str(root / "output.md"),
            events_file=str(root / "events.jsonl"),
            metadata={"approval": "Akkoord", "cockpit_provider": "ollama", "cockpit_model": "llama3.2:latest"},
        )

        original_bridge = roo_cli._bridge_run
        original_container = roo_cli._running_in_container
        original_status = roo_cli.roo_status
        original_local = roo_cli.run_roo_cli_task
        roo_cli._bridge_run = lambda body: {
            "status": "bridge_unavailable",
            "reason": "Host bridge Roo call failed: boom",
            "transport_error": True,
        }
        roo_cli._running_in_container = lambda: True
        roo_cli.roo_status = lambda prefer_bridge=True: {"status": "available", "available": True, "via_bridge": True}
        roo_cli.run_roo_cli_task = lambda **kwargs: self.fail("local fallback should not run inside Docker")
        try:
            result = roo_cli.run_roo_job(job, EventLog(job.events_file))
        finally:
            roo_cli._bridge_run = original_bridge
            roo_cli._running_in_container = original_container
            roo_cli.roo_status = original_status
            roo_cli.run_roo_cli_task = original_local

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["category"], "bridge_unavailable")
        self.assertIn("Host bridge Roo call failed", result["reason"])


if __name__ == "__main__":
    unittest.main()
