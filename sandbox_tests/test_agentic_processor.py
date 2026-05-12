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
        if tool_name == "agentic_ecosystem_context":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "DeepSeek/Atlas: Sub-agent role taxonomy, Spec-driven delivery.",
                "stderr": "",
                "result": {"sources": ["deepseek", "atlas"], "visible_summary": "deepseek + atlas"},
                "metadata_11d": {"source_type": "local_agentic_ecosystem"},
                "approval_status": "not_required_readonly",
                "stored_to_memory": False,
                "next_action": "continue",
            }
        if tool_name == "ov9292_travel_advice":
            return {
                "status": "preview",
                "tool_name": tool_name,
                "stdout": "9292 official planner link fallback. Exacte tijden vereisen autoritatieve bron.",
                "stderr": "",
                "result": {"planner_url": "https://9292.nl/", "authoritative": False, "scraped": False},
                "metadata_11d": {"dimension_count": 11, "source_type": "ov9292_travel_advice"},
                "approval_status": "not_required_readonly",
                "stored_to_memory": False,
                "next_action": "open official planner",
            }
        if tool_name == "connector_intent_preview":
            return {
                "status": "blocked",
                "tool_name": tool_name,
                "stdout": "connector intent gated preview",
                "stderr": "blocked",
                "result": {"executed": False, "preview_only": True, "blocked_tools": ["gmail_connector"]},
                "metadata_11d": {"dimension_count": 11, "source_type": "connector_intent_preview"},
                "approval_status": "pending_philip_akkoord",
                "stored_to_memory": False,
                "next_action": "separate adapter subtask",
            }
        if tool_name == "gmail_search":
            return {
                "status": "blocked",
                "tool_name": tool_name,
                "stdout": "gmail private read gated",
                "stderr": "blocked",
                "result": {"approval_required": True, "executed": False, "read_only": True},
                "metadata_11d": {"dimension_count": 11, "source_type": "gmail_private_read_gate"},
                "approval_status": "pending_philip_akkoord",
                "stored_to_memory": False,
                "next_action": "ask for Akkoord",
            }
        if tool_name == "mail_send":
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "mail sent",
                "stderr": "",
                "result": {"sent": True, "to": args.get("to"), "subject": args.get("subject")},
                "metadata_11d": {"dimension_count": 11, "source_type": "gmail_send"},
                "approval_status": "approved",
                "stored_to_memory": False,
                "next_action": "done",
            }
        if tool_name == "google_drive_list":
            return {
                "status": "blocked",
                "tool_name": tool_name,
                "stdout": "drive private read gated",
                "stderr": "blocked",
                "result": {"approval_required": True, "executed": False, "read_only": True},
                "metadata_11d": {"dimension_count": 11, "source_type": "google_drive_private_read_gate"},
                "approval_status": "pending_philip_akkoord",
                "stored_to_memory": False,
                "next_action": "ask for Akkoord",
            }
        if tool_name in {"github_status", "github_repo", "github_search_repositories"}:
            return {
                "status": "success",
                "tool_name": tool_name,
                "stdout": "GitHub public readonly metadata",
                "stderr": "",
                "result": {"read_only": True, "items": [{"full_name": "octocat/Hello-World", "private": False}]},
                "metadata_11d": {"dimension_count": 11, "source_type": "github_repository_metadata"},
                "approval_status": "not_required_public_readonly",
                "stored_to_memory": False,
                "next_action": "continue",
            }
        if tool_name in {"vps_status", "vps_login_check", "vps_sync_preview", "vps_sync_execute"}:
            status = "preview" if tool_name == "vps_sync_preview" else "success"
            if tool_name == "vps_sync_execute":
                status = "blocked"
            return {
                "status": status,
                "tool_name": tool_name,
                "stdout": "VPS dry-run preview" if status == "preview" else "VPS status",
                "stderr": "" if status != "blocked" else "approval required",
                "result": {
                    "remote_target": "/var/www/philip-wintrip.nl/html/Ouroboros/",
                    "dry_run": tool_name == "vps_sync_preview",
                    "executed": False,
                    "mutated": False,
                    "excluded_patterns": [".secrets/", ".env*"],
                },
                "metadata_11d": {"dimension_count": 11, "source_type": "vps_sync_preview"},
                "approval_status": "not_required_dry_run" if tool_name == "vps_sync_preview" else "not_required_status",
                "stored_to_memory": False,
                "next_action": "review preview",
            }
        return {"status": "success", "tool_name": tool_name, "stdout": "ok", "stderr": "", "result": {}}


class TestAgenticProcessor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agentic-processor-")
        self.addCleanup(self.tmp.cleanup)
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        ziel = Path(self.tmp.name) / ".agents" / "agent_types" / "type_2" / "Ziel.md"
        ziel.parent.mkdir(parents=True)
        ziel.write_text(
            "# Zielenboek\n\n1. **Veerkracht bij Weerstand (Micro-Retries):** Probeer bounded opnieuw.\n2. **Zelf-Synthese (Gereedschap Maken):** Bouw alleen via veilige middelen.\n",
            encoding="utf-8",
        )

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
        self.assertIn("list_files", names)
        self.assertIn("search_files", names)
        self.assertIn("browser_open_url", names)
        self.assertIn("host_status", names)
        self.assertIn("brave_search", names)
        self.assertEqual(catalog["ziel_policy"]["status"], "loaded")
        self.assertEqual(catalog["ziel_policy"]["principle_count"], 2)

    def test_planning_prompt_includes_ziel_guardrails_without_bypass(self):
        captured = {}

        def planner(prompt, system_prompt=None, model=None, history=None):
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            return '[{"tool":"prompt_understanding","args":{"prompt":"x"}}]'

        processor = AgenticProcessor(agent_tools=FakeAgentTools(), planner=planner)
        catalog = processor.discover_tools()
        plan = processor.plan(
            "Bedenk een creatieve workaround voor een geblokkeerde VPS deploy",
            approval="",
            tool_catalog=catalog,
            model="gemma4",
            system_prompt=None,
            history=[],
            pocket_context={"status": "success"},
        )

        self.assertEqual(plan["planner"]["ziel_policy"]["status"], "loaded")
        self.assertIn("Ziel runtime policy/context", captured["prompt"])
        self.assertIn("maximaal drie vergelijkbare mislukte pogingen", captured["prompt"])
        self.assertIn("ToolBridge", captured["prompt"])
        self.assertIn("Akkoord", captured["prompt"])
        self.assertIn("connector/VPS gates", captured["prompt"])
        self.assertIn("Ziel policy hash=", captured["system_prompt"])
        self.assertIn("geen bypass", captured["system_prompt"])

    def test_guardrail_opens_url_from_free_language_without_slash(self):
        plan = '[{"tool":"prompt_understanding","args":{"prompt":"open een site"}}]'
        bridge_calls = []

        def fake_bridge(tool, args):
            bridge_calls.append((tool, dict(args)))
            return {"status": "opened", "stdout": "opened", "stderr": "", "result": {"url": args.get("url")}}

        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama([plan, "Ik heb de URL geopend."]),
            tool_bridge_runner=fake_bridge,
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Open ns.nl", approval="Akkoord", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"]], ["browser_open_url"])
        self.assertEqual(bridge_calls[0][0], "browser_open_url")
        self.assertEqual(bridge_calls[0][1]["url"], "https://ns.nl")
        self.assertEqual(bridge_calls[0][1]["approval"], "Akkoord")
        self.assertIn("inserted_browser_open_url", result["planner"]["guardrails_applied"])

    def test_heuristic_fallback_opens_url_from_free_language_without_slash(self):
        bridge_calls = []

        def fake_bridge(tool, args):
            bridge_calls.append((tool, dict(args)))
            return {"status": "opened", "stdout": "opened", "stderr": "", "result": {"url": args.get("url")}}

        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama(["", "Ik heb de URL geopend."]),
            tool_bridge_runner=fake_bridge,
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Ga naar example.com", approval="Akkoord", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"]], ["memory_search", "browser_open_url"])
        self.assertEqual([call[0] for call in bridge_calls], ["browser_open_url"])
        self.assertEqual(bridge_calls[0][1]["url"], "https://example.com")
        self.assertEqual(result["planner"]["source"], "heuristic_fallback")

    def test_guardrail_maps_test_selector_to_bridge_run_tests(self):
        plan = '[{"tool":"run_tests","args":{"test_selector":"sandbox_tests.test_agentic_processor"}}]'
        bridge_calls = []

        def fake_bridge(tool, args):
            bridge_calls.append((tool, dict(args)))
            return {"status": "success", "stdout": "OK", "stderr": "", "result": {"test_command": "python3 -m unittest"}}

        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama([plan, "Tests zijn groen."]),
            tool_bridge_runner=fake_bridge,
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Draai tests sandbox_tests.test_agentic_processor", approval="Akkoord", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual(bridge_calls[0][0], "run_tests")
        self.assertEqual(bridge_calls[0][1]["selector"], "sandbox_tests.test_agentic_processor")
        self.assertEqual(bridge_calls[0][1]["approval"], "Akkoord")

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

    def test_guardrail_uses_9292_tool_for_9292_or_bus_tram_metro_request(self):
        plan = '[{"tool":"brave_search","args":{"query":"9292 bus Ermelo Utrecht","limit":5}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Gebruik de 9292-link en noem geen exacte tijden."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run(
                "Gebruik 9292 reisplanner voor bus tram metro van Ermelo naar Utrecht om 13:30",
                model="gemma4",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"]], ["memory_search", "ov9292_travel_advice"])
        self.assertEqual([call[0] for call in fake_tools.calls], ["memory_search", "ov9292_travel_advice"])
        ov_args = fake_tools.calls[1][1]
        self.assertEqual(ov_args["from_place"], "Ermelo")
        self.assertEqual(ov_args["to_place"], "Utrecht")
        self.assertEqual(ov_args["time"], "13:30")
        self.assertIn("inserted_ov9292_travel_advice", result["planner"]["guardrails_applied"])
        self.assertIn("removed_transit_brave_search", result["planner"]["guardrails_applied"])
        self.assertFalse(result["provenance"]["brave_search_used"])
        self.assertIn("ov9292_travel_advice", result["provenance"]["external_tools_used"])

    def test_connector_intents_are_preview_gated_before_any_private_tool_execution(self):
        plan = '[{"tool":"mail_read_recent","args":{"limit":5}},{"tool":"brave_search","args":{"query":"gmail"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "unused"]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Upload Gmail bijlage naar Google Drive en deploy via VPS", model="gemma4")

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertEqual([step["tool"] for step in result["plan"]], ["connector_intent_preview"])
        self.assertEqual([call[0] for call in fake_tools.calls], ["connector_intent_preview"])
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual(result["provenance"]["blocked_tools"], ["connector_intent_preview"])
        self.assertIn("inserted_connector_intent_preview", result["planner"]["guardrails_applied"])

    def test_gmail_and_drive_read_intents_route_to_first_class_gated_tools(self):
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(agent_tools=fake_tools, ollama_client=FakeOllama(['[{"tool":"brave_search","args":{"query":"gmail"}}]', "unused"]))
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            gmail = processor.run("Lees mijn Gmail inbox en vat samen", model="gemma4")

        fake_tools_drive = FakeAgentTools()
        drive_processor = AgenticProcessor(agent_tools=fake_tools_drive, ollama_client=FakeOllama(['[{"tool":"brave_search","args":{"query":"drive"}}]', "unused"]))
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            drive_processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            drive = drive_processor.run("Lijst mijn Google Drive bestanden", model="gemma4")

        self.assertEqual(gmail["status"], "blocked")
        self.assertEqual(gmail["plan"][0]["tool"], "gmail_search")
        self.assertEqual(gmail["steps"][0]["tool"], "gmail_search")
        self.assertEqual([call[0] for call in fake_tools.calls], ["gmail_search"])
        self.assertIn("inserted_gmail_search", gmail["planner"]["guardrails_applied"])
        self.assertEqual(drive["status"], "blocked")
        self.assertEqual(drive["plan"][0]["tool"], "google_drive_list")
        self.assertEqual([call[0] for call in fake_tools_drive.calls], ["google_drive_list"])
        self.assertIn("inserted_google_drive_list", drive["planner"]["guardrails_applied"])

    def test_mail_send_intent_routes_to_mail_send_not_gmail_search(self):
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(agent_tools=fake_tools, ollama_client=FakeOllama(['[{"tool":"gmail_search","args":{"query":"hallo"}}]', "unused"]))
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            blocked = processor.run('Stuur een mail met onderwerp "hallo" en tekst "hallo" naar info@wintrip.nl', model="gemma4")

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["plan"][0]["tool"], "mail_send")
        self.assertEqual(blocked["steps"][0]["tool"], "mail_send")
        self.assertEqual(fake_tools.calls, [])
        self.assertIn("inserted_mail_send", blocked["planner"]["guardrails_applied"])

        approved_tools = FakeAgentTools()
        approved_processor = AgenticProcessor(agent_tools=approved_tools, ollama_client=FakeOllama(['[{"tool":"gmail_search","args":{"query":"hallo"}}]', "Mail verstuurd."]))
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            approved_processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            approved = approved_processor.run('Stuur een mail met onderwerp "hallo" en tekst "hallo" naar info@wintrip.nl', approval="Akkoord", model="gemma4")

        self.assertEqual(approved["status"], "success")
        self.assertEqual([call[0] for call in approved_tools.calls], ["mail_send"])
        args = approved_tools.calls[0][1]
        self.assertEqual(args["to"], "info@wintrip.nl")
        self.assertEqual(args["subject"], "hallo")
        self.assertEqual(args["body"], "hallo")
        self.assertEqual(args["approval"], "Akkoord")

    def test_github_public_intent_routes_to_readonly_github_tool(self):
        plan = '[{"tool":"connector_intent_preview","args":{"prompt":"github"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(agent_tools=fake_tools, ollama_client=FakeOllama([plan, "GitHub metadata samengevat."]))
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Zoek publieke GitHub repositories over Ouroboros", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["plan"][0]["tool"], "github_search_repositories")
        self.assertEqual([call[0] for call in fake_tools.calls], ["github_search_repositories"])
        self.assertIn("inserted_github_search_repositories", result["planner"]["guardrails_applied"])
        self.assertIn("github_search_repositories", result["provenance"]["external_tools_used"])

    def test_vps_deploy_intent_routes_to_sync_preview_first_even_with_akkoord(self):
        plan = '[{"tool":"vps_sync_execute","args":{"approval":"Akkoord"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(agent_tools=fake_tools, ollama_client=FakeOllama([plan, "VPS preview samengevat."]))
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Deploy/sync Ouroboros naar de VPS", approval="Akkoord", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["plan"][0]["tool"], "vps_sync_preview")
        self.assertEqual([call[0] for call in fake_tools.calls], ["vps_sync_preview"])
        self.assertEqual(fake_tools.calls[0][1]["approval"], "Akkoord")
        self.assertIn("inserted_vps_sync_preview", result["planner"]["guardrails_applied"])
        self.assertIn("vps_sync_preview", result["provenance"]["external_tools_used"])
        self.assertNotIn("vps_sync_execute", result["provenance"]["tools_used"])
        self.assertFalse(result["steps"][0]["result"]["result"]["mutated"])

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

    def test_guardrail_inserts_agentic_ecosystem_for_agents_deepseek_atlas_goal(self):
        plan = '[{"tool":"prompt_understanding","args":{"prompt":"agentisch werk"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "DeepSeek en Atlas patronen zijn meegenomen."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run(
                "Gebruik relevante onderdelen van /home/pwintri2/deepseek en /home/pwintri2/atlas voor agentisch werken met agents.",
                model="gemma4",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual([step["tool"] for step in result["plan"][:2]], ["memory_search", "agentic_ecosystem_context"])
        self.assertEqual([call[0] for call in fake_tools.calls[:2]], ["memory_search", "agentic_ecosystem_context"])
        self.assertIn("inserted_agentic_ecosystem_context", result["planner"]["guardrails_applied"])
        self.assertTrue(result["provenance"]["agentic_ecosystem_used"])
        self.assertEqual(result["provenance"]["agentic_ecosystem_sources"], ["deepseek", "atlas"])
        self.assertIn("DeepSeek/Atlas: deepseek+atlas", result["response"])

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

    def test_emits_canonical_ooda_phases_for_agentic_run(self):
        plan = '[{"tool":"prompt_understanding","args":{"prompt":"hi"}}]'
        processor = AgenticProcessor(
            agent_tools=FakeAgentTools(),
            ollama_client=FakeOllama([plan, "Synthese."]),
        )
        events = []

        def fake_record(**kwargs):
            events.append(dict(kwargs))
            return {"status": "stored", "stored": True, "event_id": f"event-{len(events)}", "fake_success": False}

        with patch("controller.agentic_processor.record_ooda_event", side_effect=fake_record):
            with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
                processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
                result = processor.run("Vat lokaal samen", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual([event["phase"] for event in events], ["observe", "orient", "decide", "act", "reflect"])
        self.assertEqual(len({event["session_id"] for event in events}), 1)
        self.assertTrue(all(event["event_kind"] == "agentic_processor" for event in events))
        self.assertTrue(all(event["learnable"] is False for event in events))
        self.assertTrue(all(event["audit_only"] is True for event in events))

    def test_gates_agentic_mail_social_and_codex_actions_without_approval(self):
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
        self.assertEqual(result["plan"][0]["tool"], "connector_intent_preview")
        self.assertEqual(result["steps"][0]["tool"], "connector_intent_preview")
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual([call[0] for call in fake_tools.calls], ["connector_intent_preview"])
        self.assertEqual(result["provenance"]["external_tools_used"], ["connector_intent_preview"])
        self.assertEqual(result["provenance"]["mutating_tools_attempted"], [])
        self.assertEqual(result["provenance"]["blocked_tools"], ["connector_intent_preview"])

    def test_unknown_planner_tool_routes_to_self_programming_guardrail_and_blocks_without_approval(self):
        plan = '[{"tool":"make_hologram","args":{"color":"blue"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "unused"]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Gebruik een nog onbekende hologram capability", model="gemma4")

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["plan"][0]["tool"], "resolve_or_build_function")
        self.assertEqual(result["plan"][0]["args"]["requested_capability"], "make_hologram")
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual(fake_tools.calls, [])
        self.assertEqual(result["provenance"]["blocked_tools"], ["resolve_or_build_function"])

    def test_unknown_planner_tool_runs_self_programming_guardrail_after_approval(self):
        plan = '[{"tool":"make_hologram","args":{"color":"blue"}}]'
        fake_tools = FakeAgentTools()
        processor = AgenticProcessor(
            agent_tools=fake_tools,
            ollama_client=FakeOllama([plan, "Self-programming guardrail uitgevoerd."]),
        )
        with patch("controller.agentic_processor.save_agentic_session", return_value={"status": "stored", "stored": True}):
            processor._pocket_context = lambda trigger, payload: {"status": "success", "trigger": trigger, "fake_success": False}
            result = processor.run("Gebruik een nog onbekende hologram capability", approval="Akkoord", model="gemma4")

        self.assertEqual(result["status"], "success")
        self.assertEqual(fake_tools.calls[0][0], "resolve_or_build_function")
        self.assertEqual(fake_tools.calls[0][1]["requested_capability"], "make_hologram")
        self.assertEqual(fake_tools.calls[0][1]["arguments"], {"color": "blue"})
        self.assertEqual(fake_tools.calls[0][1]["approval"], "Akkoord")

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
