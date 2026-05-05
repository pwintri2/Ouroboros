import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStatusContracts(unittest.TestCase):
    def test_evidence_status_promotes_only_with_evidence(self):
        from controller.status_contracts import evidence_status

        self.assertEqual(evidence_status(root_exists=False), "missing")
        self.assertEqual(evidence_status(root_exists=True), "detected")
        self.assertEqual(evidence_status(root_exists=True, config_present=True), "configured")
        self.assertEqual(evidence_status(root_exists=True, runtime_reachable=True), "available")
        self.assertEqual(evidence_status(root_exists=True, process_running=True), "running")
        self.assertEqual(
            evidence_status(root_exists=True, runtime_reachable=True, healthy=True),
            "online",
        )
        self.assertEqual(evidence_status(root_exists=True, blocked=True), "blocked")
        self.assertEqual(evidence_status(root_exists=True, errored=True), "error")

    def test_freshness_helpers_truthful(self):
        from controller.status_contracts import degrade_if_stale, freshness_seconds, is_fresh

        now = time.time()
        self.assertGreaterEqual(freshness_seconds(now - 30), 30)
        self.assertIsNone(freshness_seconds(None))
        self.assertTrue(is_fresh(now - 5, max_age_seconds=60))
        self.assertFalse(is_fresh(now - 600, max_age_seconds=60))

        status, reason = degrade_if_stale("online", last_seen=now - 9999, max_age_seconds=60)
        self.assertEqual(status, "degraded")
        self.assertIn("stalled", (reason or "").lower())

        status, reason = degrade_if_stale("online", last_seen=now - 5, max_age_seconds=60)
        self.assertEqual(status, "online")
        self.assertIsNone(reason)

    def test_run_probe_handles_missing_command(self):
        from controller.status_contracts import run_probe

        result = run_probe(["this-binary-does-not-exist-zzz"])
        self.assertEqual(result.status, "missing")

    def test_run_probe_returns_available_for_zero_exit(self):
        from controller.status_contracts import run_probe

        result = run_probe(["/bin/sh", "-c", "exit 0"])
        self.assertEqual(result.status, "available")
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
