# sandbox_tests/test_mentor_roles.py

import unittest

from controller.virtual_team import MENTOR_ROLES, REGISTRY_TOOL_NAMES, VirtualMeeting


class DummyOllama:
    def __init__(self):
        self.calls = []

    def select_model(self, requested=None, role=""):
        return requested or f"{role.lower()}-model"

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        self.calls.append(
            {
                "user_input": user_input,
                "model": model,
                "system_prompt": system_prompt,
            }
        )
        return "Ik gebruikte de echte registry-resultaten en geef dit terug aan Ouroboros."


class DummyRegistry:
    def __init__(self):
        self.available_tools = list(REGISTRY_TOOL_NAMES)
        self.calls = []

    def status(self):
        return {"available_tools": self.available_tools}

    def run_tool(self, tool_name, args):
        self.calls.append((tool_name, dict(args)))
        return {
            "tool_name": tool_name,
            "status": "success",
            "result": {"tool": tool_name, "args": dict(args)},
            "stdout": f"real result from {tool_name}",
            "stderr": "",
            "error": "",
            "stored_to_memory": tool_name in {"training_ingest", "safe_shell", "run_tests"},
        }


class TestMentorRoles(unittest.TestCase):
    def test_run_meeting_returns_explicit_structured_mentor_roles(self):
        tools = DummyRegistry()
        ollama = DummyOllama()
        context = "Current training text: Wintrip AI leert veilig.\nSelected UI frequency: 432 Hz."
        meeting = VirtualMeeting(ollama_client=ollama, training_context=context, tools=tools)

        history = meeting.run_meeting("Akkoord train deze snapshot, run tests en command: ls")

        self.assertEqual(meeting.roles, list(MENTOR_ROLES))
        self.assertNotIn("Tester1", history)
        self.assertNotIn("Tester2", history)
        for role in MENTOR_ROLES:
            self.assertIn(role, history)
            self.assertEqual(history[role]["mentor_role"], role)
            self.assertEqual(history[role]["model_used"], f"{role.lower()}-model")
            self.assertIn("tool_calls", history[role])
            self.assertIn("learned", history[role])
            self.assertIn("next_action", history[role])
            self.assertIn("mentor role:", history[role]["content"])
            self.assertIn("model_used:", history[role]["content"])

        self.assertEqual(len(ollama.calls), len(MENTOR_ROLES))
        for call in ollama.calls:
            self.assertIn("[BESCHIKBARE REGISTRY TOOLS]", call["user_input"])
            self.assertIn("[REAL TOOL RESULTS]", call["user_input"])

    def test_akkoord_triggers_real_registry_calls_only(self):
        tools = DummyRegistry()
        context = "Current training text: Wintrip AI traint de Hippocampus.\nSelected UI frequency: 421 Hz."
        meeting = VirtualMeeting(ollama_client=DummyOllama(), training_context=context, tools=tools)

        meeting.run_meeting("Akkoord train deze snapshot, run tests en command: ls")

        names = [name for name, _args in tools.calls]
        self.assertIn("memory_search", names)
        self.assertIn("training_ingest", names)
        self.assertIn("run_tests", names)
        self.assertIn("safe_shell", names)
        self.assertTrue(set(names).issubset(set(REGISTRY_TOOL_NAMES)))

        calls = dict(tools.calls)
        self.assertEqual(calls["training_ingest"]["approval"], "Akkoord")
        self.assertEqual(calls["safe_shell"]["command"], "ls")
        self.assertEqual(calls["safe_shell"]["approval"], "Akkoord")

    def test_structured_tool_calls_are_assigned_to_mentor_roles(self):
        tools = DummyRegistry()
        meeting = VirtualMeeting(
            ollama_client=DummyOllama(),
            training_context="Current training text: Wintrip.\nSelected UI frequency: 421 Hz.",
            tools=tools,
        )

        history = meeting.run_meeting("Akkoord train, run tests en command: ls")

        developer_tools = [call["tool_name"] for call in history["Developer"]["tool_calls"]]
        researcher_tools = [call["tool_name"] for call in history["Researcher"]["tool_calls"]]
        trainer_tools = [call["tool_name"] for call in history["Trainer"]["tool_calls"]]
        tester_tools = [call["tool_name"] for call in history["Tester"]["tool_calls"]]

        self.assertEqual(developer_tools, ["safe_shell"])
        self.assertIn("memory_search", researcher_tools)
        self.assertIn("training_ingest", trainer_tools)
        self.assertEqual(tester_tools, ["run_tests"])
        self.assertEqual(history["Critic"]["tool_calls"], [])


if __name__ == "__main__":
    unittest.main()
