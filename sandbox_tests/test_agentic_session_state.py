"""Schema, redaction and snapshot tests for agentic_session_state."""

import unittest

from controller import agentic_session_state as state


class SessionStateSchemaTests(unittest.TestCase):
    def test_new_session_id_unique(self):
        first = state.new_session_id()
        second = state.new_session_id()
        self.assertTrue(first.startswith("agentic_"))
        self.assertNotEqual(first, second)

    def test_normalize_session_id_uses_existing(self):
        self.assertEqual(state.normalize_session_id("agentic_abc"), "agentic_abc")
        generated = state.normalize_session_id("")
        self.assertTrue(generated.startswith("agentic_"))

    def test_make_session_defaults(self):
        session = state.make_session(
            session_id="agentic_test_1",
            goal="Doe iets nuttigs",
            plan_mode=state.PLAN_MODE_ACT,
            provider="ollama",
            model="qwen3:8b",
            conversation_id="conv_1",
        )
        self.assertEqual(session["session_id"], "agentic_test_1")
        self.assertEqual(session["plan_mode"], state.PLAN_MODE_ACT)
        self.assertEqual(session["status"], state.SESSION_STATUS_RUNNING)
        self.assertFalse(session["approval_required"])
        self.assertEqual(session["approval_status"], "not_required")
        self.assertEqual(session["tool_summary"]["planned"], 0)
        self.assertFalse(session["fake_success"])
        self.assertFalse(session["secrets_returned"])
        self.assertIn("created_at", session)
        self.assertIn("updated_at", session)

    def test_make_event_carries_sequence_and_redaction(self):
        event = state.make_event(
            session_id="agentic_1",
            event_type=state.EVENT_TOOL_PLANNED,
            sequence=3,
            payload={"api_key": "sk-test", "tool": "brave_search"},
            tool="brave_search",
            status="planned",
        )
        self.assertEqual(event["sequence"], 3)
        self.assertEqual(event["event_id"], "agentic_1:000003")
        self.assertEqual(event["payload"]["api_key"], "[REDACTED]")
        self.assertEqual(event["payload"]["tool"], "brave_search")
        self.assertFalse(event["fake_success"])
        self.assertFalse(event["secrets_returned"])

    def test_redact_handles_secrets_in_strings_and_keys(self):
        data = {
            "secret_token": "abc123",
            "nested": {
                "api_key": "leak",
                "ok": "value",
                "value": "authorization=Bearer abcdef",
            },
            "list": ["api_key=hidden", "plain"],
        }
        clean = state.redact(data)
        self.assertEqual(clean["secret_token"], "[REDACTED]")
        self.assertEqual(clean["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(clean["nested"]["ok"], "value")
        self.assertIn("[REDACTED]", clean["nested"]["value"])
        self.assertIn("[REDACTED]", clean["list"][0])
        self.assertEqual(clean["list"][1], "plain")

    def test_compact_event_summary_keeps_only_overview_fields(self):
        event = state.make_event(
            session_id="agentic_x",
            event_type=state.EVENT_TOOL_COMPLETED,
            sequence=1,
            payload={"stdout": "ok"},
            tool="memory_search",
            status="completed",
            duration_seconds=0.123,
        )
        summary = state.compact_event_summary(event)
        self.assertEqual(summary["sequence"], 1)
        self.assertEqual(summary["tool"], "memory_search")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["duration_seconds"], 0.123)
        self.assertIn("stdout", summary["summary"])

    def test_merge_completion_into_session_records_status_and_blocked_tools(self):
        session = state.make_session(
            session_id="agentic_done",
            goal="Test",
            plan_mode=state.PLAN_MODE_ACT,
            provider="ollama",
            model="qwen3:8b",
        )
        merged = state.merge_completion_into_session(
            session,
            {
                "status": "blocked",
                "approval_required": True,
                "blocked_tools": ["safe_shell"],
                "memory_status": {"status": "stored", "collection": "wintrip_agentic_sessions_11d", "item_id": "x"},
                "duration_seconds": 1.234,
            },
        )
        self.assertEqual(merged["status"], state.SESSION_STATUS_BLOCKED)
        self.assertTrue(merged["approval_required"])
        self.assertEqual(merged["approval_status"], "required")
        self.assertEqual(merged["blocked_tools"], ["safe_shell"])
        self.assertEqual(merged["memory_status"]["collection"], "wintrip_agentic_sessions_11d")
        self.assertAlmostEqual(merged["duration_seconds"], 1.234)
        self.assertIn("completed_at", merged)


if __name__ == "__main__":
    unittest.main()
