"""Verify AgenticProcessor emits the Cline-grade event stream."""

import unittest
from unittest.mock import patch

from controller import agentic_event_bus as bus
from controller import agentic_loop_guard as loop_guard
from controller.agentic_processor import AgenticProcessor


class FakeOllama:
    def chat(self, prompt, model=None, system_prompt=None, history=None):
        return ""


class FakeAgentTools:
    def __init__(self):
        self.calls = []

    def run_tool(self, tool_name, args=None):
        self.calls.append((tool_name, dict(args or {})))
        if tool_name == "memory_search":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "hit",
                "result": {"count": 1},
                "metadata_11d": {},
                "approval_status": "not_required",
                "stored_to_memory": False,
                "next_action": "continue",
            }
        if tool_name == "prompt_understanding":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "ok",
                "result": {"intent": "neutral"},
                "metadata_11d": {},
                "approval_status": "not_required",
                "stored_to_memory": False,
                "next_action": "continue",
            }
        if tool_name == "safe_shell":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "",
                "result": {},
                "metadata_11d": {},
                "approval_status": "approved",
                "stored_to_memory": False,
                "next_action": "continue",
            }
        return {"status": "unavailable", "fake_success": False}


def _planner(steps):
    import json

    def _plan(prompt=None, system_prompt=None, model=None, history=None):
        return json.dumps({"steps": steps})

    return _plan


class AgenticEventEmissionTests(unittest.TestCase):
    def setUp(self):
        bus.clear_event_bus()
        bus.disable_event_bus_persistence()
        loop_guard.reset_all()

    def tearDown(self):
        bus.enable_event_bus_persistence()
        bus.clear_event_bus()
        loop_guard.reset_all()

    @patch("controller.agentic_processor.save_agentic_session", lambda state, **_: {"status": "stored", "stored": True, "collection": "test", "item_id": "x"})
    def test_run_emits_session_plan_and_completion_events(self):
        processor = AgenticProcessor(
            ollama_client=FakeOllama(),
            agent_tools=FakeAgentTools(),
            planner=_planner([{"tool": "memory_search", "args": {"query": "wat is X"}}]),
            max_steps=4,
        )
        result = processor.run(
            "Beschrijf wat X is",
            approval="",
            session_id="agentic_event_a",
            plan_mode="act",
            conversation_id="conv_a",
        )
        self.assertEqual(result["session_id"], "agentic_event_a")
        events = bus.list_events("agentic_event_a")
        types = [event["event_type"] for event in events]
        self.assertIn("session_started", types)
        self.assertIn("plan_built", types)
        self.assertIn("tool_planned", types)
        self.assertIn("tool_validated", types)
        self.assertIn("tool_running", types)
        self.assertIn("tool_completed", types)
        self.assertIn("memory_write", types)
        self.assertIn("session_completed", types)
        sessions = bus.list_sessions(limit=5)
        self.assertEqual(sessions[0]["session_id"], "agentic_event_a")

    @patch("controller.agentic_processor.save_agentic_session", lambda state, **_: {"status": "stored", "stored": True, "collection": "test", "item_id": "x"})
    def test_plan_mode_skips_execution(self):
        processor = AgenticProcessor(
            ollama_client=FakeOllama(),
            agent_tools=FakeAgentTools(),
            planner=_planner([{"tool": "memory_search", "args": {"query": "doel"}}]),
            max_steps=4,
        )
        result = processor.run(
            "Plan iets",
            approval="",
            session_id="agentic_event_plan",
            plan_mode="plan",
            conversation_id="conv_plan",
        )
        self.assertEqual(result["plan_mode"], "plan")
        self.assertEqual(result["status"], "planned")
        self.assertFalse(result.get("steps"))
        types = [event["event_type"] for event in bus.list_events("agentic_event_plan")]
        self.assertIn("plan_built", types)
        self.assertNotIn("tool_running", types)
        self.assertNotIn("tool_completed", types)

    @patch("controller.agentic_processor.save_agentic_session", lambda state, **_: {"status": "stored", "stored": True, "collection": "test", "item_id": "x"})
    def test_approval_block_emits_awaiting_approval_event(self):
        processor = AgenticProcessor(
            ollama_client=FakeOllama(),
            agent_tools=FakeAgentTools(),
            planner=_planner([
                {"tool": "memory_search", "args": {"query": "doel"}},
                {"tool": "safe_shell", "args": {"command": "ls"}},
            ]),
            max_steps=4,
        )
        result = processor.run(
            "Doe een gevoelige stap",
            approval="",
            session_id="agentic_event_block",
        )
        self.assertTrue(result.get("approval_required"))
        types = [event["event_type"] for event in bus.list_events("agentic_event_block")]
        self.assertIn("tool_awaiting_approval", types)
        self.assertIn("tool_blocked", types)
        session = bus.get_session("agentic_event_block")
        self.assertTrue(session["approval_required"])
        self.assertIn("safe_shell", session["blocked_tools"])

    @patch("controller.agentic_processor.save_agentic_session", lambda state, **_: {"status": "stored", "stored": True, "collection": "test", "item_id": "x"})
    def test_loop_guard_blocks_repeated_tool_calls(self):
        repeated_step = {"tool": "memory_search", "args": {"query": "loop"}}
        processor = AgenticProcessor(
            ollama_client=FakeOllama(),
            agent_tools=FakeAgentTools(),
            planner=_planner([repeated_step] * 6),
            max_steps=10,
        )
        result = processor.run(
            "Herhaal loop",
            session_id="agentic_event_loop",
        )
        events = bus.list_events("agentic_event_loop")
        types = [event["event_type"] for event in events]
        self.assertIn("loop_warning", types)
        self.assertIn("loop_blocked", types)
        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
