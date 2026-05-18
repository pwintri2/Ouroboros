"""In-memory bus, persistence redaction and cancellation tests."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from controller import agentic_event_bus as bus
from controller import agentic_session_state as state


class EventBusTests(unittest.TestCase):
    def setUp(self):
        bus.clear_event_bus()
        bus.enable_event_bus_persistence()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._log_path = Path(self._tmp_dir.name) / "events.jsonl"
        os.environ["WINTRIP_AGENTIC_SESSION_LOG"] = str(self._log_path)
        self._prior_no_persist = os.environ.pop("WINTRIP_AGENTIC_EVENT_BUS_NO_PERSIST", None)

    def tearDown(self):
        bus.clear_event_bus()
        bus.enable_event_bus_persistence()
        os.environ.pop("WINTRIP_AGENTIC_SESSION_LOG", None)
        if self._prior_no_persist is not None:
            os.environ["WINTRIP_AGENTIC_EVENT_BUS_NO_PERSIST"] = self._prior_no_persist
        self._tmp_dir.cleanup()

    def _register(self, session_id="agentic_test"):
        session = state.make_session(
            session_id=session_id,
            goal="Test goal",
            plan_mode=state.PLAN_MODE_ACT,
            provider="ollama",
            model="qwen3:8b",
        )
        return bus.register_session(session)

    def test_append_event_increments_sequence_and_persists(self):
        self._register()
        first = bus.append_event("agentic_test", event_type=state.EVENT_PLAN_BUILT, payload={"steps": 2})
        second = bus.append_event("agentic_test", event_type=state.EVENT_TOOL_PLANNED, tool="brave_search", payload={"args": {"query": "test"}})
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        events = bus.list_events("agentic_test")
        self.assertEqual([event["sequence"] for event in events], [1, 2])
        log_lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(log_lines), 2)
        for line in log_lines:
            json.loads(line)

    def test_secret_is_redacted_in_event_and_persistence(self):
        self._register()
        bus.append_event(
            "agentic_test",
            event_type=state.EVENT_TOOL_RUNNING,
            tool="safe_shell",
            payload={"api_key": "sk-leak", "command": "ls /tmp"},
        )
        events = bus.list_events("agentic_test")
        self.assertEqual(events[0]["payload"]["api_key"], "[REDACTED]")
        line = self._log_path.read_text(encoding="utf-8").strip().splitlines()[0]
        self.assertNotIn("sk-leak", line)
        self.assertIn("[REDACTED]", line)

    def test_tool_summary_updates_from_events(self):
        self._register()
        bus.append_event("agentic_test", event_type=state.EVENT_TOOL_PLANNED, tool="brave_search")
        bus.append_event("agentic_test", event_type=state.EVENT_TOOL_RUNNING, tool="brave_search")
        bus.append_event("agentic_test", event_type=state.EVENT_TOOL_COMPLETED, tool="brave_search", status="success", duration_seconds=0.1)
        bus.append_event("agentic_test", event_type=state.EVENT_TOOL_BLOCKED, tool="safe_shell", approval_required=True)
        session = bus.get_session("agentic_test")
        self.assertEqual(session["tool_summary"]["planned"], 1)
        self.assertEqual(session["tool_summary"]["completed"], 1)
        self.assertEqual(session["tool_summary"]["blocked"], 1)
        self.assertTrue(session["approval_required"])
        self.assertIn("safe_shell", session["blocked_tools"])

    def test_cancellation_lifecycle(self):
        self._register()
        self.assertFalse(bus.is_cancelled("agentic_test"))
        self.assertTrue(bus.request_cancel("agentic_test"))
        self.assertTrue(bus.is_cancelled("agentic_test"))
        self.assertTrue(bus.consume_cancellation("agentic_test"))
        self.assertFalse(bus.is_cancelled("agentic_test"))

    def test_list_sessions_orders_by_recent_activity(self):
        self._register("agentic_a")
        self._register("agentic_b")
        bus.append_event("agentic_a", event_type=state.EVENT_PLAN_BUILT)
        bus.append_event("agentic_b", event_type=state.EVENT_PLAN_BUILT)
        bus.append_event("agentic_a", event_type=state.EVENT_TOOL_COMPLETED, tool="memory_search", status="success")
        sessions = bus.list_sessions(limit=10)
        ids = [item["session_id"] for item in sessions]
        self.assertEqual(ids[0], "agentic_a")
        self.assertIn("agentic_b", ids)

    def test_disable_persistence_skips_jsonl_writes(self):
        try:
            bus.disable_event_bus_persistence()
            self._register()
            bus.append_event("agentic_test", event_type=state.EVENT_TOOL_PLANNED, tool="brave_search")
            self.assertFalse(self._log_path.exists())
        finally:
            bus.enable_event_bus_persistence()


if __name__ == "__main__":
    unittest.main()
