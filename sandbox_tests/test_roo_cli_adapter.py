import tempfile
import unittest
from pathlib import Path

from controller.agent_runtime.adapters import roo_cli
from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord


class TestRooCliAdapter(unittest.TestCase):
    def _job(self, root: Path) -> JobRecord:
        return JobRecord(
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

    def test_bridge_transport_error_in_container_fails_without_local_fallback(self):
        tmp = tempfile.TemporaryDirectory(prefix="roo-cli-adapter-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        job = self._job(root)

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

    def test_bridge_result_emits_roo_editor_events_for_cockpit(self):
        tmp = tempfile.TemporaryDirectory(prefix="roo-cli-adapter-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        job = self._job(root)

        original_bridge = roo_cli._bridge_run
        original_status = roo_cli.roo_status
        original_api_key = roo_cli._provider_api_key
        roo_cli._bridge_run = lambda body: {
            "status": "completed",
            "exit_code": 0,
            "category": "ok",
            "command": ["roo", "--provider", "ollama", "--model", "deepseek-coder:latest"],
            "parsed_output": {
                "events": [
                    {"type": "assistant", "content": "Ik bekijk de code."},
                    {"type": "tool", "name": "apply_patch", "content": "Wijzig controller/foo.py"},
                    {"type": "approval", "message": "Vraag toestemming voor bestandshandeling."},
                ]
            },
            "response_preview": "Klaar.",
            "changed_files": ["controller/foo.py"],
            "dirty_files": ["controller/foo.py"],
            "artifacts": [str(root / "roo_output.json")],
        }
        roo_cli.roo_status = lambda prefer_bridge=True: {"status": "available", "available": True, "via_bridge": True}
        roo_cli._provider_api_key = lambda cockpit_provider, cockpit_model="": ""
        progress = []
        try:
            result = roo_cli.run_roo_job(job, EventLog(job.events_file), on_progress=progress.append)
        finally:
            roo_cli._bridge_run = original_bridge
            roo_cli.roo_status = original_status
            roo_cli._provider_api_key = original_api_key

        self.assertEqual(result["status"], "completed")
        events = EventLog(job.events_file).read(limit=50)
        event_types = [event["type"] for event in events]
        self.assertIn("roo_editor_started", event_types)
        self.assertIn("roo_cli_event", event_types)
        self.assertIn("roo_workspace_changes", event_types)
        self.assertTrue(any((event.get("data") or {}).get("approval_required") for event in events if event["type"] == "roo_cli_event"))
        self.assertTrue(any("changed_files" in item for item in progress))
        self.assertTrue(any("roo_permission_prompt" in item.get("service_actions", []) for item in progress))


if __name__ == "__main__":
    unittest.main()
