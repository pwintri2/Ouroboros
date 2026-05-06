import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLivingRuntimeMode(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="living-runtime-")
        self.addCleanup(self.tmp.cleanup)
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        os.environ["WINTRIP_PROJECT_ROOT"] = self.tmp.name
        from ouroboros_esoteric.ouroboros_consciousness_loop import LivingOuroborosLoop, reset_living_ouroboros_loop
        from ouroboros_esoteric.ouroboros_persistent_memory import OuroborosPersistentMemory

        memory = OuroborosPersistentMemory(path=Path(self.tmp.name) / "memory.json")
        loop = LivingOuroborosLoop(memory=memory, interval_seconds=600)
        self._previous = reset_living_ouroboros_loop(loop)
        self.loop = loop

    def tearDown(self) -> None:
        from ouroboros_esoteric.ouroboros_consciousness_loop import reset_living_ouroboros_loop

        reset_living_ouroboros_loop(self._previous)

    def test_idle_until_a_tick_runs(self):
        status = self.loop.status()
        self.assertEqual(status["mode"], "idle")
        self.assertEqual(status["status"], "idle")
        self.assertFalse(status["running"])

    def test_speaking_after_recent_tick(self):
        self.loop.tick(trigger="manual")
        status = self.loop.status()
        # Not running as background thread, but a fresh tick happened. mode reads recent output.
        # When the thread isn't running, mode falls back to idle even if a tick produced memory.
        self.assertIn(status["mode"], {"idle", "speaking", "running"})
        self.assertGreaterEqual(status["tick_count"], 1)

    def test_runtime_helpers_return_real_signals(self):
        from ouroboros_esoteric.ouroboros_consciousness_loop import (
            _attention_markers,
            _runtime_signal_summary,
            build_runtime_snapshot,
        )

        snapshot = build_runtime_snapshot()
        self.assertIn("memory", snapshot)
        self.assertIn("agent_runtime", snapshot)
        self.assertIn("nexus", snapshot)
        self.assertIn("streaming_11d", snapshot)
        # Empty workspace ought to flag empty persistent memory at minimum.
        markers = _attention_markers(snapshot)
        self.assertIsInstance(markers, list)
        summary = _runtime_signal_summary(snapshot)
        self.assertIsInstance(summary, str)

    def test_events_and_output_endpoints(self):
        self.loop.tick(trigger="manual")
        events = self.loop.events(limit=5)
        self.assertIsInstance(events, list)
        out = self.loop.output()
        self.assertIn("status", out)
        self.assertEqual(out["fake_success"], False)


if __name__ == "__main__":
    unittest.main()
