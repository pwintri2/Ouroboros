import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestNexusStateTruthful(unittest.TestCase):
    def setUp(self) -> None:
        from controller.nexus_status import get_nexus_state

        get_nexus_state().reset()

    def test_summary_starts_degraded_with_no_events(self):
        from controller.nexus_status import nexus_summary

        summary = nexus_summary(freshness_seconds=10)
        self.assertEqual(summary["status"], "degraded")
        self.assertEqual(summary["ingested_events_total"], 0)
        self.assertEqual(summary["sources_seen"], {})
        self.assertEqual(summary["fake_success"], False)

    def test_ingest_event_advances_status_and_records(self):
        from controller.nexus_status import ingest_event, nexus_recent, nexus_summary

        event = ingest_event("agent_runtime", "job_created", "test event")
        self.assertEqual(event["source"], "agent_runtime")
        events = nexus_recent(limit=10)
        self.assertEqual(len(events), 1)

        summary = nexus_summary(freshness_seconds=300)
        self.assertEqual(summary["sources_seen"], {"agent_runtime": 1})
        # Either online (with QCN responding) or degraded (no QCN); never fakes online from disk.
        self.assertIn(summary["status"], {"online", "degraded"})
        self.assertIn(summary["event_ingestion"], {"healthy", "stale", "idle"})

    def test_summary_does_not_claim_converged_without_qcn_evidence(self):
        from controller.nexus_status import nexus_summary

        summary = nexus_summary(freshness_seconds=60)
        # converged is bool; it must come from QCN omega vector — never assumed True.
        self.assertIn("converged", summary)
        self.assertIsInstance(summary["converged"], bool)
        if summary["converged"]:
            # If reported converged, the QCN status must have told us so.
            self.assertEqual(summary["qcn_status"], "online")


if __name__ == "__main__":
    unittest.main()
