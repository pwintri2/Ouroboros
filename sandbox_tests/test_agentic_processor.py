import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.agent_tools import REGISTERED_TOOLS
from controller.agentic_processor import AgenticProcessor


class FakeOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, prompt, model=None, system_prompt=None, history=None):
        self.calls.append({"prompt": prompt, "model": model, "system_prompt": system_prompt, "history": history or []})
        return self.responses.pop(0) if self.responses else "synthetisch antwoord"


class FakeAgentTools:
    def __init__(self):
        self.calls = []

    def run_tool(self, tool_name, args=None):
        self.calls.append((tool_name, dict(args or {})))
        if tool_name == "brave_search":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "Brave: AI nieuws item 1. AI nieuws item 2.",
                "stderr": "",
                "result": {"query": args.get("query"), "response": {"status": "success"}},
                "metadata_11d": {"dimension_count": 11, "source_type": "brave_search"},
                "approval_status": "approved",
                "stored_to_memory": False,
                "next_action": "synthesize",
            }
        if tool_name == "memory_search":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "Memory match",
                "stderr": "",
                "result": {"count": 1},
                "metadata_11d": {},
                "approval_status": "not_required",
                "stored_to_memory": False,
                "next_action": "continue",
            }
        return {"status": "success", "tool_name": tool_name, "stdout": "ok", "stderr": "", "result": {}}


class TestAgenticProcessor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agentic-processor-")
        self.addCleanup(self.tmp.cleanup)
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace

    def test_discovery_includes_all_agent_tools_and_bridge_tools(self):
        processor = AgenticProcessor(agent_tools=FakeAgentTools(), ollama_client=FakeOllama([]))

        catalog = processor.discover_tools()
        names = set(catalog["tool_names"])

        self.assertTrue(set(REGISTERED_TOOLS).issubset(names))
        self.assertIn("read_file", names)
        self.assertIn("write_file", names)
        self.assertIn("run_command", names)
        self.assertIn("brave_search", names)

    def test_executes_plan_with_brave_then_write_file_through_pocket(self):
        plan = (
            '[{"tool":"brave_search","args":{"query":"laatste AI nieuws","limit":2,"approval":"Akkoord"}},'
            '{"tool":"write_file","args":{"path":"news.txt","content":"<summary from search>","approval":"Akkoord"}}]'
        )
        bridge_calls = []

        def fake_bridge(tool, args):
            bridge_calls.append((tool, dict(args)))
            Path(self.tmp.name, args["path"]).write_text(args["content"], encoding="utf-8")
            return {"status": "success", "stdout": "written", "stderr": "", "result": {"path": args["path"]}}

        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama([plan, "Antwoord uit gekozen model rond de pocket."]),
            tool_bridge_runner=fake_bridge,
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "voice": {"symbolic_frame": "11D"}, "fake_success": False}
            result = processor.run("Zoek de laatste AI-nieuwtjes en schrijf een samenvatting naar news.txt", approval="Akkoord", model="ouroboros:latest")

        self.assertEqual(result["status"], "success")
        self.assertEqual([call[0] for call in bridge_calls], ["write_file"])
        self.assertIn("Brave: AI nieuws", Path(self.tmp.name, "news.txt").read_text(encoding="utf-8"))
        self.assertEqual([step["tool"] for step in result["steps"][:2]], ["memory_search", "brave_search"])
        self.assertEqual(result["steps"][1]["pocket"]["trigger"], "tool_result:brave_search")
        self.assertTrue(result["provenance"]["brave_search_used"])
        self.assertTrue(result["provenance"]["brave_search_success"])
        self.assertEqual(result["provenance"]["tools_used"], ["memory_search", "brave_search", "write_file"])
        self.assertIn("Brave Search: gebruikt", result["response"])
        self.assertIn("Antwoord uit gekozen model rond de pocket.", result["response"])

    def test_brave_search_runs_without_approval_before_mutating_step_blocks(self):
        plan = (
            '[{"tool":"brave_search","args":{"query":"laatste AI nieuws","limit":2}},'
            '{"tool":"write_file","args":{"path":"news.txt","content":"<summary from search>"}}]'
        )
        bridge_calls = []
        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama([plan, "Samenvatting uit gekozen model."]),
            tool_bridge_runner=lambda tool, args: bridge_calls.append((tool, args)) or {"status": "success"},
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Zoek de laatste AI-nieuwtjes en schrijf een samenvatting naar news.txt", model="gemma4")

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(bridge_calls, [])
        self.assertEqual([step["tool"] for step in result["steps"]], ["memory_search", "brave_search", "write_file"])
        self.assertEqual(result["steps"][0]["status"], "success")
        self.assertEqual(result["steps"][1]["status"], "success")
        self.assertEqual(result["steps"][2]["status"], "blocked")
        self.assertTrue(result["provenance"]["brave_search_used"])
        self.assertTrue(result["provenance"]["brave_search_success"])
        self.assertEqual(result["provenance"]["mutating_tools_attempted"], ["write_file"])
        self.assertIn("Brave Search: gebruikt", result["response"])
        self.assertIn("write_file(blocked)", result["response"])

    def test_guardrail_inserts_brave_when_llm_omits_it_for_web_goal(self):
        plan = '[{"tool":"prompt_understanding","args":{"prompt":"losjes plan zonder webtool"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Synthese uit gekozen model."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Zoek op internet naar het laatste AI agents nieuws", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"][:2]], ["memory_search", "brave_search"])
        self.assertEqual([call[0] for call in fake_tools.calls[:2]], ["memory_search", "brave_search"])
        self.assertEqual(result["planner"]["source"], "llm_with_guardrails")
        self.assertIn("inserted_memory_search", result["planner"]["guardrails_applied"])
        self.assertIn("inserted_brave_search", result["planner"]["guardrails_applied"])
        self.assertTrue(result["provenance"]["brave_search_used"])
        self.assertEqual(result["provenance"]["planner_guardrails_applied"], ["inserted_memory_search", "inserted_brave_search"])

    def test_guardrail_does_not_duplicate_existing_brave_step(self):
        plan = (
            '[{"tool":"memory_search","args":{"query":"ai nieuws","limit":5}},'
            '{"tool":"brave_search","args":{"query":"ai nieuws","limit":3,"llm_context":true}}]'
        )
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Synthese uit gekozen model."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Zoek op internet naar het laatste AI nieuws", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"]].count("brave_search"), 1)
        self.assertEqual([call[0] for call in fake_tools.calls].count("brave_search"), 1)
        self.assertEqual(result["planner"]["source"], "llm")
        self.assertNotIn("guardrails_applied", result["planner"])

    def test_guardrail_forces_ns_tool_for_train_schedule_and_removes_irrelevant_voice_step(self):
        plan = (
            '[{"tool":"memory_search","args":{"query":"trein Ermelo Utrecht","limit":5}},'
            '{"tool":"brave_search","args":{"query":"trein Ermelo Utrecht","limit":5}},'
            '{"tool":"voice_chat_status","args":{}}]'
        )
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Neem de trein volgens de NS-output."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {
                "status": "success",
                "trigger": trigger,
                "voice": {"symbolic_frame": "SHOULD_NOT_LEAK_IN_SYNTHESIS_PROMPT"},
                "quantum": {"debug": "SHOULD_NOT_LEAK_IN_SYNTHESIS_PROMPT"},
                "fake_success": False,
            }
            result = processor.run(
                "Kun je opzoeken hoe laat ik de trein in Ermelo moet nemen als ik om 13:30 een afspraak op Utrecht centraal heb?",
                model="gemma4",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"]], ["memory_search", "ns_travel_advice"])
        self.assertEqual([call[0] for call in fake_tools.calls], ["memory_search", "ns_travel_advice"])
        ns_args = fake_tools.calls[1][1]
        self.assertEqual(ns_args["from_station"], "Ermelo")
        self.assertEqual(ns_args["to_station"], "Utrecht centraal")
        self.assertEqual(ns_args["time"], "13:30")
        self.assertTrue(ns_args["search_for_arrival"])
        self.assertIn("inserted_ns_travel_advice", result["planner"]["guardrails_applied"])
        self.assertIn("removed_transit_brave_search", result["planner"]["guardrails_applied"])
        self.assertIn("removed_irrelevant_voice_chat_status", result["planner"]["guardrails_applied"])
        self.assertFalse(result["provenance"]["brave_search_used"])
        self.assertIn("ns_travel_advice", result["provenance"]["external_tools_used"])
        self.assertIn("Brave Search: niet gebruikt", result["response"])
        self.assertNotIn("SHOULD_NOT_LEAK_IN_SYNTHESIS_PROMPT", fake_tools.calls[1][1]["query"])
        self.assertNotIn("SHOULD_NOT_LEAK_IN_SYNTHESIS_PROMPT", processor.ollama.calls[1]["prompt"])

    def test_guardrail_keeps_voice_step_for_real_voice_status_goal(self):
        plan = '[{"tool":"voice_chat_status","args":{}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Spraakchat status samengevat."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Wat is de spraakchat status?", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"]], ["voice_chat_status"])
        self.assertEqual([call[0] for call in fake_tools.calls], ["voice_chat_status"])
        self.assertEqual(result["planner"]["source"], "llm")

    def test_blocks_mutating_step_without_approval_and_stores_session(self):
        plan = '[{"tool":"write_file","args":{"path":"blocked.txt","content":"x"}}]'
        bridge_calls = []
        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama([plan, "unused"]),
            tool_bridge_runner=lambda tool, args: bridge_calls.append((tool, args)) or {"status": "success"},
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}) as save_session:
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Schrijf x naar blocked.txt")

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertEqual(bridge_calls, [])
        self.assertFalse(result["provenance"]["brave_search_used"])
        self.assertIn("Brave Search: niet gebruikt", result["response"])
        save_session.assert_called_once()

    def test_blocks_agentic_mail_social_and_codex_actions_without_approval(self):
        plan = (
            '[{"tool":"mail_read_recent","args":{"limit":2}},'
            '{"tool":"social_post_publish","args":{"platform":"x","content":"update"}},'
            '{"tool":"codex_job_start","args":{"task":"pas jezelf aan"}}]'
        )
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "unused"]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Lees mijn mail, post op social en laat Codex aanpassen")

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["steps"][0]["tool"], "mail_read_recent")
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual(fake_tools.calls, [])
        self.assertEqual(result["provenance"]["external_tools_used"], ["mail_read_recent"])
        self.assertEqual(result["provenance"]["mutating_tools_attempted"], [])
        self.assertEqual(result["provenance"]["blocked_tools"], ["mail_read_recent"])

    def test_quantum_foam_birth_tool_resonance_and_collapse_are_recorded(self):
        plan = '[{"tool":"voice_chat_status","args":{}}]'
        fake_tools = FakeAgentTools()

        def fake_foam(goal, *, phase, tool=None, result=None, collapse=False):
            return {
                "status": "collapsed" if collapse else "online",
                "phase": phase,
                "tool": tool,
                "active": not collapse,
                "coherence": 73.5 if not collapse else 0.0,
                "field_coherence_percent": 73.5 if not collapse else 0.0,
                "node_count": 6,
                "active_nodes": 6 if not collapse else 0,
                "dominant_dimensions": ["d11_field=0.8"],
                "collapse_event": collapse,
                "ram_released_estimate_nodes": 6 if collapse else 0,
                "summary": "Quantum Foam test field",
                "nodes": [{"type": "ToolNode", "weight": 0.7, "coherence": 0.8, "connection_count": 2}],
                "fake_success": False,
            }

        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Spraakchat status samengevat."]),
        )
        with patch("controller.agentic_processor.agentic_foam_event", side_effect=fake_foam) as foam:
            with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
                processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "payload": payload, "fake_success": False}
                result = processor.run("Wat is de spraakchat status?", model="gemma4")

        phases = [call.kwargs["phase"] for call in foam.call_args_list]
        self.assertIn("agentic_start", phases)
        self.assertIn("tool:voice_chat_status", phases)
        self.assertIn("agentic_success", phases)
        self.assertTrue(result["quantum_foam"]["active"])
        self.assertTrue(result["quantum_foam_collapse"]["collapse_event"])
        self.assertTrue(result["provenance"]["quantum_foam_collapsed"])
        self.assertEqual(result["provenance"]["quantum_foam_ram_released_estimate_nodes"], 6)
        self.assertIn("Quantum Foam: collapsed", result["response"])


if __name__ == "__main__":
    unittest.main()
