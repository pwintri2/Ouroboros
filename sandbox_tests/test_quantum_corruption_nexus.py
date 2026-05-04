import tempfile
import time
import unittest
from pathlib import Path

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord
from controller.agent_runtime.orchestrator import AgentOrchestrator
from controller.agent_runtime.store import JobStore
from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.quantum_corruption_nexus import get_quantum_corruption_nexus


class TestQuantumCorruptionNexus(unittest.TestCase):
    def setUp(self):
        self.nexus = get_quantum_corruption_nexus()
        self.nexus.reset()
        AkashicNetwork().reset()

    def test_failed_job_triggers_safe_sacred_corruption_event(self):
        event = self.nexus.analyze_job(
            {"job_id": "codex_fail", "agent": "codex", "task": "fix runtime"},
            {"status": "failed", "exit_code": 1, "stderr": "boom"},
        )

        self.assertEqual(event["action"], "sacred_corruption")
        self.assertIn("Retry this task", event["recommended_prompt"])
        status = self.nexus.status()
        self.assertEqual(status["sacred_corruptions"], 1)
        recent = AkashicNetwork().recent_events()
        self.assertEqual(recent[-1]["frequency"], 432.0)

    def test_repeated_low_ruflo_coherence_returns_creative_retry(self):
        first = self.nexus.record_ruflo_coherence(task="coordinate swarm", coherence=0.44)
        second = self.nexus.record_ruflo_coherence(task="coordinate swarm", coherence=0.43)

        self.assertEqual(first["action"], "observed")
        self.assertEqual(second["action"], "sacred_corruption")
        self.assertIn("coordinate swarm", second["recommended_prompt"])

    def test_orchestrator_records_nexus_metadata_and_event(self):
        tmp = tempfile.TemporaryDirectory(prefix="nexus-orchestrator-")
        self.addCleanup(tmp.cleanup)
        store = JobStore(runtime_root=Path(tmp.name) / "store", artifact_root=Path(tmp.name) / "out")

        def adapter(job: JobRecord, log: EventLog, on_progress):
            log.append("adapter_tick", {})
            return {"status": "completed", "exit_code": 0, "response_preview": "done"}

        orchestrator = AgentOrchestrator(store=store, adapters={"codex": adapter})
        record = orchestrator.submit("codex", "observe nexus")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            final = store.get(record.job_id) or {}
            if final.get("status") == "completed":
                break
            time.sleep(0.01)

        final = store.get(record.job_id) or {}
        metadata = final.get("metadata") or {}
        self.assertIn("quantum_corruption_nexus", metadata)
        events = orchestrator.read_events(record.job_id)
        self.assertIn("quantum_corruption_nexus", [event["type"] for event in events])


if __name__ == "__main__":
    unittest.main()
