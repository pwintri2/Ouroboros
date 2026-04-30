# sandbox_tests/test_virtual_team_tools.py

import unittest

from controller.virtual_team import VirtualMeeting


class DummyTools:
    def __init__(self):
        self.calls = []

    def run_tool(self, tool_name, args):
        self.calls.append((tool_name, args))
        return {"tool_name": tool_name, "status": "success", "stdout": tool_name, "stored_to_memory": False}


class TestVirtualTeamTools(unittest.TestCase):
    def test_tool_layer_uses_memory_first(self):
        tools = DummyTools()
        meeting = VirtualMeeting(training_context="Selected UI frequency: 432 Hz.", tools=tools)
        results = meeting._run_tool_layer("Wat is de status?")
        self.assertEqual(results[0]["tool_name"], "memory_search")

    def test_approval_runs_tests_and_safe_shell(self):
        tools = DummyTools()
        meeting = VirtualMeeting(training_context="Selected UI frequency: 432 Hz.", tools=tools)
        meeting._run_tool_layer("Akkoord run tests en command: ls")
        names = [name for name, _ in tools.calls]
        self.assertIn("run_tests", names)
        self.assertIn("safe_shell", names)

    def test_approval_training_uses_context_text_and_hz(self):
        tools = DummyTools()
        context = "Current training text: Wintrip AI leert zichzelf.\nSelected UI frequency: 421 Hz."
        meeting = VirtualMeeting(training_context=context, tools=tools)
        meeting._run_tool_layer("Akkoord train deze snapshot")
        calls = dict(tools.calls)
        self.assertIn("training_ingest", calls)
        self.assertEqual(calls["training_ingest"]["target_hz"], 421.0)
        self.assertEqual(calls["training_ingest"]["approval"], "Akkoord")
        self.assertIn("Wintrip AI", calls["training_ingest"]["text"])


if __name__ == "__main__":
    unittest.main()
