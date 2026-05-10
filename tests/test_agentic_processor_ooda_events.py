import unittest
from unittest.mock import patch

from controller.agentic_processor import AgenticProcessor


class FakeOllama:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, prompt, model=None, system_prompt=None, history=None):
        return self.responses.pop(0) if self.responses else "synthetisch antwoord"


class FakeAgentTools:
    def status(self):
        return {"available_tools": []}

    def run_tool(self, tool_name, args=None):
        return {"status": "success", "tool_name": tool_name, "stdout": "ok", "stderr": "", "result": {}}


class TestAgenticProcessorOodaEvents(unittest.TestCase):
    def test_agentic_processor_emits_five_ooda_phases_with_one_session(self):
        events = []

        def fake_record(**kwargs):
            events.append(dict(kwargs))
            return {"status": "stored", "stored": True, "event_id": f"event-{len(events)}", "fake_success": False}

        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama(['[{"tool":"prompt_understanding","args":{"prompt":"hi"}}]', "antwoord"]),
        )

        with patch("controller.agentic_processor.record_ooda_event", side_effect=fake_record):
            with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
                processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
                result = processor.run("Vat lokaal samen", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([event["phase"] for event in events], ["observe", "orient", "decide", "act", "reflect"])
        self.assertEqual(len({event["session_id"] for event in events}), 1)
        self.assertTrue(all(event["event_kind"] == "agentic_processor" for event in events))
        self.assertTrue(all(event["route"] == "agentic_processor" for event in events))
        self.assertTrue(all(event["learnable"] is False for event in events))
        self.assertTrue(all(event["audit_only"] is True for event in events))


if __name__ == "__main__":
    unittest.main()
