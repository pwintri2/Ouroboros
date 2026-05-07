import os
import asyncio
import json
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""

from sandbox_tests.test_api_ouroboros_phase1 import install_main_fakes, restore_modules


class FakeAgentTools:
    def __init__(self):
        self.last_tool_result = None

    def status(self):
        return {
            "status": "online",
            "available_tools": ["memory_search", "run_tests"],
            "last_tool_result": self.last_tool_result,
        }

    def get_tool_schemas(self, provider="openai"):
        return [
            {
                "type": "function",
                "function": {
                    "name": "memory_search",
                    "description": "Search fake memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]

    def run_tool(self, tool_name, args=None):
        self.last_tool_result = {
            "tool_name": tool_name,
            "status": "success",
            "result": {"count": 1, "matches": [{"text": "fake match"}]},
            "stdout": "fake stdout",
            "stderr": "",
            "error": "",
            "stored_to_memory": False,
        }
        return self.last_tool_result


class FakeMultiAPIRouter:
    def __init__(self):
        self.calls = []

    async def route_chat(self, provider, model, prompt, system_prompt=None, tools=None, history=None):
        self.calls.append(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "tools": list(tools or []),
                "history": list(history or []),
            }
        )
        return {
            "status": "success",
            "response": "fake multi-api response",
            "provider": provider,
            "model": model,
        }


class SlowFakeMultiAPIRouter:
    async def route_chat(self, provider, model, prompt, system_prompt=None, tools=None, history=None):
        await asyncio.sleep(1)
        return {
            "status": "success",
            "response": "late response",
            "provider": provider,
            "model": model,
        }


def load_main_with_fakes():
    previous_env = {
        "WINTRIP_DB_PATH": os.environ.get("WINTRIP_DB_PATH"),
        "WINTRIP_API_KEY_STORE": os.environ.get("WINTRIP_API_KEY_STORE"),
    }
    os.environ["WINTRIP_DB_PATH"] = tempfile.mkdtemp(prefix="tauri-backend-routes-")
    os.environ["WINTRIP_API_KEY_STORE"] = os.path.join(tempfile.mkdtemp(prefix="tauri-api-keys-"), "keys.json")
    previous_main = sys.modules.pop("controller.main", None)
    originals = install_main_fakes()
    try:
        import controller.main as main
    finally:
        restore_modules(originals)
    main.agent_tools = FakeAgentTools()
    main.app.state.multi_api_router = FakeMultiAPIRouter()
    main.app.state.ouroboros_loop = {
        "status": "idle",
        "running": False,
        "queued": False,
        "abort_requested": False,
        "pause_requested": False,
        "iteration": 0,
        "prompt": "",
        "last_step": None,
        "last_error": "",
        "started_at": None,
        "updated_at": None,
        "paused_at": None,
        "aborted_at": None,
    }
    return main, previous_main, previous_env


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestTauriBackendRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main, cls.previous_main, cls.previous_env = load_main_with_fakes()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("controller.main", None)
        if cls.previous_main is not None:
            sys.modules["controller.main"] = cls.previous_main
        for key, value in cls.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_bridge = os.environ.get("WINTRIP_RCLONE_BRIDGE_URL")
        self.workspace_tmp = tempfile.TemporaryDirectory(prefix="tauri-self-context-")
        os.environ["WINTRIP_WORKSPACE"] = self.workspace_tmp.name
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)
        self.main.agent_tools = FakeAgentTools()
        self.main.app.state.multi_api_router = FakeMultiAPIRouter()
        self.main.app.state.ouroboros_loop = {
            "status": "idle",
            "running": False,
            "queued": False,
            "abort_requested": False,
            "pause_requested": False,
            "iteration": 0,
            "prompt": "",
            "last_step": None,
            "last_error": "",
            "started_at": None,
            "updated_at": None,
            "paused_at": None,
            "aborted_at": None,
        }

    def tearDown(self):
        self.workspace_tmp.cleanup()
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace
        if self.old_bridge is None:
            os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)
        else:
            os.environ["WINTRIP_RCLONE_BRIDGE_URL"] = self.old_bridge

    def _wait_for_loop_status(self, expected_status, timeout=2.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.client.get("/api/ouroboros/loop/status").json()
            if last.get("status") == expected_status:
                return last
            time.sleep(0.02)
        return last

    def test_cockpit_config_exposes_backend_providers_models_and_approval_phrase(self):
        response = self.client.get("/api/cockpit/config")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["backend"]["status"], "online")
        self.assertEqual(data["required_approval_phrase"], "Akkoord")
        self.assertIn("ollama", data["provider_options"])
        self.assertTrue(data["provider_options"]["ollama"]["local_only"])
        self.assertIn("ouroboros", data["provider_options"])
        self.assertTrue(data["provider_options"]["ouroboros"]["local_only"])
        self.assertFalse(data["provider_options"]["ouroboros"]["llm_provider_used"])
        self.assertIn("living-runtime", data["provider_options"]["ouroboros"]["models"])
        self.assertIn("llama3.2:latest", data["available_models"]["ollama"])
        google_models = data["provider_options"]["google"]["models"]
        self.assertIn("gemini-2.5-flash", google_models)
        self.assertNotIn("gemini-2.0-flash", google_models)
        self.assertIn("api_keys", data)
        self.assertFalse(data["api_keys"]["secrets_returned"])
        self.assertIn("chroma", data)
        self.assertIn(data["chroma"]["mode"], {"persistent", "http"})

    def test_chroma_status_endpoint_exposes_runtime_mode_without_secrets(self):
        response = self.client.get("/api/ouroboros/chroma/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("mode", data)
        self.assertIn(data["mode"], {"persistent", "http"})
        self.assertIn("collections", data)
        self.assertFalse(data["fake_success"])
        self.assertNotIn("api_key", json.dumps(data).lower())

    def test_cockpit_config_keeps_local_provider_enabled_when_ollama_inventory_is_empty(self):
        original_list_models = self.main.ollama.list_models
        self.main.ollama.list_models = lambda: []
        try:
            response = self.client.get("/api/cockpit/config")
        finally:
            self.main.ollama.list_models = original_list_models

        self.assertEqual(response.status_code, 200)
        data = response.json()
        local = data["provider_options"]["ollama"]
        self.assertTrue(local["enabled"])
        self.assertFalse(local["available"])
        self.assertEqual(local["status"], "inventory_unavailable")
        self.assertEqual(data["backend"]["models_available"], 0)
        self.assertIn("llama3.2:latest", data["available_models"]["ollama"])

    def test_browser_research_route_includes_brave_companion_search(self):
        import controller.browser_research as browser_research

        original_browser = browser_research.browser_research
        original_brave = self.main.search_brave_llm_context
        browser_research.browser_research = lambda query, url=None, approval=None, **_kwargs: {
            "status": "success",
            "query": query,
            "url": "https://duckduckgo.com/",
            "scrubbed_text": "browser observed",
            "blocked_patterns": [],
            "browser_action_performed": True,
            "fake_success": False,
        }
        self.main.search_brave_llm_context = lambda query, maximum_number_of_urls=5: {
            "status": "success",
            "provider": "brave",
            "document": f"Brave context for {query}",
            "source_urls": ["https://example.com/source"],
            "fake_success": False,
        }
        try:
            response = self.client.post(
                "/api/ouroboros/research/browser",
                json={"query": "Ouroboros 11D pockets", "approval": "Akkoord", "limit": 3},
            )
        finally:
            browser_research.browser_research = original_browser
            self.main.search_brave_llm_context = original_brave

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "browser_observed")
        self.assertEqual(data["brave"]["status"], "success")
        self.assertEqual(data["browser_research"]["brave_matches"], 1)
        self.assertIn("Brave context", data["stdout"])

    def test_project_context_routes_include_dash_and_underscore_aliases(self):
        summary = self.client.get("/context/summary")
        file_tree = self.client.get("/context/file-tree?max_depth=2&limit=10")
        changed = self.client.get("/context/changed-files?limit=10")
        file_tree_underscore = self.client.get("/context/file_tree?max_depth=2&limit=10")
        changed_underscore = self.client.get("/context/changed_files?limit=10")

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(file_tree.status_code, 200)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(file_tree_underscore.status_code, 200)
        self.assertEqual(changed_underscore.status_code, 200)
        self.assertIn("structure", summary.json())
        self.assertIn("tree", file_tree.json())
        self.assertIn("changed_files", changed.json())

    def test_cockpit_chat_routes_through_multi_api_with_agent_tool_schemas(self):
        response = self.client.post(
            "/api/cockpit/chat",
            json={
                "provider": "openai",
                "model": "gpt-test",
                "prompt": "Use a tool if useful.",
                "include_tools": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["route"], "multi_api")
        self.assertEqual(data["response"], "fake multi-api response")
        self.assertEqual(data["source_trace"]["source_kind"], "model_only")
        self.assertTrue(data["source_trace"]["model_only"])
        self.assertFalse(data["source_trace"]["brave_search_used"])
        self.assertTrue(data["source_trace"]["selected_model_interprets_answer"])
        tool_names = [tool["function"]["name"] for tool in data["tool_schemas"]]
        routed_tool_names = [tool["function"]["name"] for tool in self.main.app.state.multi_api_router.calls[0]["tools"]]
        self.assertEqual(data["tool_schema_count"], len(data["tool_schemas"]))
        self.assertGreaterEqual(data["tool_schema_count"], 1)
        self.assertIn("memory_search", tool_names)
        self.assertIn("memory_search", routed_tool_names)

    def test_cockpit_chat_routes_complex_goal_to_agentic_processor(self):
        original_should = self.main.should_use_agentic_processor
        original_agentic = getattr(self.main.orchestrator, "agentic_process", None)
        calls = []

        def fake_agentic(prompt, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            return {
                "status": "success",
                "route": "agentic_processor",
                "response": "agentic done",
                "steps": [{"tool": "memory_search", "status": "success"}],
                "provenance": {
                    "planner_source": "llm_with_guardrails",
                    "planner_guardrails_applied": ["inserted_brave_search"],
                    "tools_used": ["memory_search"],
                },
                "fake_success": False,
            }

        self.main.should_use_agentic_processor = lambda prompt: "zoek" in str(prompt).lower()
        self.main.orchestrator.agentic_process = fake_agentic
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={
                    "provider": "ollama",
                    "model": "llama3.2:latest",
                    "prompt": "Zoek internet en vat samen",
                    "approval": "Akkoord",
                },
            )
        finally:
            self.main.should_use_agentic_processor = original_should
            if original_agentic is None:
                delattr(self.main.orchestrator, "agentic_process")
            else:
                self.main.orchestrator.agentic_process = original_agentic

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "agentic_processor")
        self.assertEqual(data["response"], "agentic done")
        self.assertEqual(data["source_trace"]["source_kind"], "agentic")
        self.assertFalse(data["source_trace"]["model_only"])
        self.assertEqual(data["source_trace"]["tools_executed"], ["memory_search"])
        self.assertEqual(data["source_trace"]["action_status"], "executed")
        self.assertEqual(data["source_trace"]["planner_source"], "llm_with_guardrails")
        self.assertEqual(data["source_trace"]["planner_guardrails_applied"], ["inserted_brave_search"])
        self.assertTrue(data["source_trace"]["selected_model_interprets_answer"])
        self.assertEqual(calls[0]["provider"], "ollama")
        self.assertEqual(calls[0]["approval"], "Akkoord")

    def test_cockpit_chat_slash_agents_are_intercepted_before_provider(self):
        original_living_echo = self.main._living_chat_echo
        self.main._living_chat_echo = lambda: {
            "current_thought": "living thought must stay out of slash catalog",
            "last_whisper": "living whisper must stay out of slash catalog",
            "fake_success": False,
        }
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={"provider": "google", "model": "gemini-test", "prompt": "/agents"},
            )
        finally:
            self.main._living_chat_echo = original_living_echo

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "slash_agent")
        self.assertEqual(data["agent"], "catalog")
        self.assertNotIn("living_echo", data)
        self.assertTrue(any(command.startswith("/codex") for command in data["commands"]))
        self.assertEqual(self.main.app.state.multi_api_router.calls, [])

    def test_cockpit_chat_can_address_ouroboros_runtime_without_ollama(self):
        response = self.client.post(
            "/api/cockpit/chat",
            json={
                "provider": "ouroboros",
                "model": "living-runtime",
                "conversation_id": "direct-ouroboros-test",
                "prompt": "Kun jij zelf antwoorden zonder Ollama?",
                "include_tools": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["provider"], "ouroboros")
        self.assertEqual(data["route"], "ouroboros_runtime")
        self.assertTrue(data["local_only"])
        self.assertFalse(data["llm_provider_used"])
        self.assertEqual(data["source_trace"]["source_kind"], "ouroboros_runtime")
        self.assertFalse(data["source_trace"]["model_only"])
        self.assertTrue(data["source_trace"]["pocket_voice_used"])
        self.assertGreaterEqual(data["source_trace"]["pocket_processed"], 1)
        self.assertIn("niet via Ollama", data["response"])
        self.assertEqual(data["concept_anchor_field"]["dimension_count"], 11)
        self.assertEqual(data["concept_anchor_field"]["pocket_count"], 11)
        self.assertEqual(len(data["concept_anchor_field"]["pocket_signal"]), 11)
        self.assertEqual(data["concept_anchor_field"]["holographic_bootloader"]["blocked_cell_count"], 84)
        self.assertEqual(len(data["concept_anchor_field"]["holographic_bootloader"]["output_signal"]), 11)
        self.assertIn("pocket_voice", data)
        self.assertIn("response", data["pocket_voice"])
        self.assertIn("dominant_dimensions", data["pocket_voice"])
        self.assertIn("quantum_collapse", data)
        self.assertIn("cirq_runtime", data["quantum_collapse"])
        self.assertIn("local_model_translation_used", data)
        self.assertIn("Holografische bootloader", data["response"])
        self.assertEqual(self.main.app.state.multi_api_router.calls, [])

    def test_ouroboros_respond_endpoint_forces_runtime_provider(self):
        response = self.client.post(
            "/api/ouroboros/respond",
            json={"provider": "ollama", "model": "llama3.2:latest", "prompt": "test directe runtime"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider"], "ouroboros")
        self.assertEqual(data["route"], "ouroboros_runtime")
        self.assertFalse(data["llm_provider_used"])
        self.assertIn("lokale Ouroboros-runtime", data["response"])

    def test_cockpit_chat_keeps_server_side_history_for_next_turn(self):
        first = self.client.post(
            "/api/cockpit/chat",
            json={
                "provider": "google",
                "model": "gemini-test",
                "conversation_id": "diti-test-memory",
                "prompt": "Mijn projectroot is WintripAI en Ruflo hoort erbij.",
            },
        )
        second = self.client.post(
            "/api/cockpit/chat",
            json={
                "provider": "google",
                "model": "gemini-test",
                "conversation_id": "diti-test-memory",
                "prompt": "Wat zei ik net over de projectroot?",
            },
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["conversation_id"], "diti-test-memory")
        calls = self.main.app.state.multi_api_router.calls
        self.assertEqual(len(calls), 2)
        second_context = json.dumps(
            {"history": calls[1]["history"], "system_prompt": calls[1]["system_prompt"]},
            ensure_ascii=False,
        )
        self.assertIn("Ouroboros self-context", second_context)
        self.assertIn("Mijn projectroot is WintripAI", second_context)
        self.assertIn("fake multi-api response", second_context)
        self.assertGreaterEqual(second.json()["self_context"]["server_history_count"], 2)

    def test_cockpit_chat_returns_timeout_payload_before_client_abort(self):
        self.main.app.state.multi_api_router = SlowFakeMultiAPIRouter()
        original_timeout = self.main._cockpit_chat_timeout_seconds
        original_slash_timeout = self.main._cockpit_slash_dispatch_timeout_seconds
        self.main._cockpit_chat_timeout_seconds = lambda: 0.05
        self.main._cockpit_slash_dispatch_timeout_seconds = lambda: 0.05
        try:
            before = time.time()
            response = self.client.post(
                "/api/cockpit/chat",
                json={"provider": "google", "model": "gemini-test", "prompt": "hello"},
            )
            elapsed = time.time() - before
        finally:
            self.main._cockpit_chat_timeout_seconds = original_timeout
            self.main._cockpit_slash_dispatch_timeout_seconds = original_slash_timeout

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLess(elapsed, 0.75)
        self.assertEqual(data["status"], "timeout")
        self.assertEqual(data["route"], "multi_api")
        self.assertIn("timeout", data["error"].lower())

    def test_cockpit_chat_routes_grok_natural_language_to_world_agent(self):
        calls = []
        original_ask = self.main.ask_grok_via_world_agent

        def fake_ask(question, approval="", open_tab=True, submit=True):
            calls.append({"question": question, "approval": approval, "open_tab": open_tab, "submit": submit})
            return {
                "status": "success",
                "route": "world_agent",
                "provider": "world_agent",
                "model": "grok.com",
                "response": "fake grok response",
                "memory": {"stored": True, "memory_id": "world-test"},
            }

        self.main.ask_grok_via_world_agent = fake_ask
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={
                    "provider": "ollama",
                    "model": "llama3.2:latest",
                    "approval": "Akkoord",
                    "prompt": "open grok.com en vraag wat het verschil is tussen simulatie en bewustzijn",
                },
            )
        finally:
            self.main.ask_grok_via_world_agent = original_ask

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "world_agent")
        self.assertEqual(data["response"], "fake grok response")
        self.assertEqual(calls[0]["approval"], "Akkoord")
        self.assertFalse(calls[0]["open_tab"])
        self.assertIn("simulatie", calls[0]["question"])
        self.assertEqual(data["frontend_action"]["type"], "open_url")
        self.assertTrue(data["frontend_action"]["url"].startswith("https://grok.com/"))
        self.assertIn("simulatie", data["frontend_action"]["url"])
        self.assertEqual(data["frontend_action"]["question"], "wat het verschil is tussen simulatie en bewustzijn")
        self.assertEqual(self.main.app.state.multi_api_router.calls, [])

    def test_cockpit_chat_routes_polite_grok_question_to_world_agent(self):
        calls = []
        original_ask = self.main.ask_grok_via_world_agent

        def fake_ask(question, approval="", open_tab=True, submit=True):
            calls.append({"question": question, "approval": approval, "open_tab": open_tab, "submit": submit})
            return {
                "status": "success",
                "route": "world_agent",
                "provider": "world_agent",
                "model": "grok.com",
                "response": "fake grok response",
            }

        self.main.ask_grok_via_world_agent = fake_ask
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={
                    "provider": "ollama",
                    "model": "ouroboros",
                    "approval": "Akkoord",
                    "prompt": "Kun je aan grok vragen hoe je zelf verder moet ontwikkelen?",
                },
            )
        finally:
            self.main.ask_grok_via_world_agent = original_ask

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "world_agent")
        self.assertEqual(data["provider"], "world_agent")
        self.assertEqual(data["model"], "grok.com")
        self.assertEqual(calls[0]["question"], "hoe je zelf verder moet ontwikkelen?")
        self.assertFalse(calls[0]["open_tab"])
        self.assertTrue(data["frontend_action"]["url"].startswith("https://grok.com/"))
        self.assertIn("ontwikkelen", data["frontend_action"]["url"])
        self.assertEqual(data["frontend_action"]["question"], "hoe je zelf verder moet ontwikkelen?")
        self.assertEqual(self.main.app.state.multi_api_router.calls, [])

    def test_cockpit_chat_routes_grok_frontend_action_with_trimmed_approval(self):
        original_ask = self.main.ask_grok_via_world_agent

        def fake_ask(question, approval="", open_tab=True, submit=True):
            return {
                "status": "success",
                "route": "world_agent",
                "provider": "world_agent",
                "model": "grok.com",
                "response": "fake grok response",
            }

        self.main.ask_grok_via_world_agent = fake_ask
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={
                    "provider": "ollama",
                    "model": "llama3.2:latest",
                    "approval": "Akkoord ",
                    "prompt": "open grok.com en vraag: antwoord alleen met OK",
                },
            )
        finally:
            self.main.ask_grok_via_world_agent = original_ask

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "world_agent")
        self.assertEqual(data["frontend_action"]["type"], "open_url")
        self.assertTrue(data["frontend_action"]["url"].startswith("https://grok.com/"))
        self.assertIn("antwoord", data["frontend_action"]["url"])
        self.assertEqual(data["world_intent"]["action"], "grok_ask")

    def test_cockpit_chat_returns_grok_frontend_action_even_when_bridge_times_out(self):
        original_ask = self.main.ask_grok_via_world_agent
        original_timeout = self.main._cockpit_chat_timeout_seconds

        def slow_ask(question, approval="", open_tab=True, submit=True):
            time.sleep(0.2)
            return {"status": "success", "response": "late grok response"}

        self.main.ask_grok_via_world_agent = slow_ask
        self.main._cockpit_chat_timeout_seconds = lambda: 0.05
        try:
            before = time.time()
            response = self.client.post(
                "/api/cockpit/chat",
                json={
                    "provider": "ollama",
                    "model": "llama3.2:latest",
                    "approval": "Akkoord",
                    "prompt": "open grok.com en vraag antwoord alleen met OK",
                },
            )
            elapsed = time.time() - before
        finally:
            self.main.ask_grok_via_world_agent = original_ask
            self.main._cockpit_chat_timeout_seconds = original_timeout

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLess(elapsed, 0.75)
        self.assertEqual(data["status"], "timeout")
        self.assertEqual(data["route"], "world_agent")
        self.assertEqual(data["frontend_action"]["type"], "open_url")
        self.assertTrue(data["frontend_action"]["url"].startswith("https://grok.com/"))
        self.assertIn("antwoord", data["frontend_action"]["url"])

    def test_cockpit_chat_routes_reflective_grok_prompt_to_living_action(self):
        calls = []
        original_method = getattr(self.main.orchestrator, "levendige_actie", None)

        def fake_living_action(prompt, approval="", max_iterations=3):
            calls.append({"prompt": prompt, "approval": approval, "max_iterations": max_iterations})
            return {
                "status": "success",
                "route": "living_action",
                "provider": "ouroboros",
                "model": "living-ooda-world",
                "response": "Levendige Actie: world_grok_open_if_interesting",
                "decision": {"tool": "world_grok_open_if_interesting"},
                "frontend_action": {"type": "open_url", "url": "https://grok.com/", "target": "_blank"},
                "stored": True,
                "fake_success": False,
            }

        self.main.orchestrator.levendige_actie = fake_living_action
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={
                    "provider": "ollama",
                    "model": "llama3.2:latest",
                    "prompt": "denk na over 1GB bewustzijn en open grok.com als je iets interessants vindt",
                },
            )
        finally:
            if original_method is None:
                delattr(self.main.orchestrator, "levendige_actie")
            else:
                self.main.orchestrator.levendige_actie = original_method

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "living_action")
        self.assertEqual(data["decision"]["tool"], "world_grok_open_if_interesting")
        self.assertEqual(data["frontend_action"]["type"], "open_url")
        self.assertTrue(data["stored"])
        self.assertEqual(calls[0]["prompt"], "denk na over 1GB bewustzijn en open grok.com als je iets interessants vindt")
        self.assertEqual(self.main.app.state.multi_api_router.calls, [])

    def test_cockpit_chat_returns_disabled_payload_when_multi_api_is_unavailable(self):
        self.main.app.state.multi_api_router = None
        original_multi = self.main.MultiAPIRouter
        self.main.MultiAPIRouter = None
        try:
            response = self.client.post(
                "/api/cockpit/chat",
                json={"provider": "openai", "model": "gpt-test", "prompt": "hello"},
            )
        finally:
            self.main.MultiAPIRouter = original_multi

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "disabled")
        self.assertIn("no external API call was made", data["error"])

    def test_ouroboros_loop_start_runs_one_fake_step_then_stops(self):
        calls = []

        def fake_step(philip_opdracht, registry, approval="", action=None, action_args=None):
            calls.append(
                {
                    "prompt": philip_opdracht,
                    "approval": approval,
                    "action": action,
                    "action_args": action_args,
                }
            )
            return {
                "status": "success",
                "next_action": "Inspect Loop Status",
                "stdout": "one step",
                "stderr": "",
            }

        original_step = self.main.self_training_step
        self.main.self_training_step = fake_step
        try:
            response = self.client.post(
                "/api/ouroboros/loop/start",
                json={"prompt": "Train one tiny loop step", "approval": "Akkoord"},
            )
            status_payload = self._wait_for_loop_status("completed")
        finally:
            self.main.self_training_step = original_step

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["background"])
        self.assertIn(data["status"], {"running", "completed"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(status_payload["status"], "completed")
        self.assertFalse(status_payload["running"])
        self.assertEqual(status_payload["iteration"], 1)
        self.assertEqual(status_payload["loop"]["last_step"]["status"], "success")

    def test_ouroboros_loop_start_returns_before_slow_step_finishes(self):
        started = threading.Event()
        release = threading.Event()

        def slow_step(philip_opdracht, registry, approval="", action=None, action_args=None):
            started.set()
            release.wait(timeout=2)
            return {
                "status": "success",
                "next_action": "Inspect Loop Status",
                "stdout": "slow step",
                "stderr": "",
            }

        original_step = self.main.self_training_step
        self.main.self_training_step = slow_step
        try:
            before = time.time()
            response = self.client.post(
                "/api/ouroboros/loop/start",
                json={"prompt": "Train one slow loop step", "approval": "Akkoord"},
            )
            elapsed = time.time() - before
            self.assertTrue(started.wait(timeout=1.0))
            data = response.json()
            self.assertLess(elapsed, 0.75)
            self.assertEqual(data["status"], "running")
            self.assertTrue(data["running"])
            self.assertTrue(data["background"])
            release.set()
            status_payload = self._wait_for_loop_status("completed")
        finally:
            release.set()
            self.main.self_training_step = original_step

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status_payload["status"], "completed")
        self.assertEqual(status_payload["loop"]["last_step"]["stdout"], "slow step")

    def test_ouroboros_loop_pause_and_abort_update_app_state(self):
        paused = self.client.post("/api/ouroboros/loop/pause").json()
        aborted = self.client.post("/api/ouroboros/loop/abort").json()

        self.assertEqual(paused["status"], "paused")
        self.assertFalse(paused["running"])
        self.assertEqual(aborted["status"], "aborted")
        self.assertTrue(aborted["loop"]["abort_requested"])
        self.assertIsNone(aborted["loop"]["last_step"])
        self.assertEqual(aborted["loop"]["last_error"], "")

    def test_self_training_step_legacy_fallback_when_real_step_missing(self):
        original_step = self.main.self_training_step
        self.main.self_training_step = None
        try:
            response = self.client.post(
                "/api/ouroboros/self-training/step",
                json={
                    "prompt": "Train 11D memory",
                    "browser_text": "Wintrip self training",
                    "run_tests": True,
                },
            )
        finally:
            self.main.self_training_step = original_step

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(data["test_result"]["status"], "blocked")
        self.assertIn("understanding", data)
        self.assertIn("records", data)

    def test_api_key_save_is_approval_gated_and_never_returns_secret(self):
        response = self.client.post(
            "/api/cockpit/api-keys",
            json={"provider": "openai", "api_key": "openai-test-secret-1234"},
        )
        self.assertEqual(response.status_code, 200)
        blocked = response.json()
        self.assertEqual(blocked["status"], "blocked")
        self.assertNotIn("openai-test-secret-1234", response.text)

        response = self.client.post(
            "/api/cockpit/api-keys",
            json={"provider": "openai", "api_key": "openai-test-secret-1234", "approval": "Akkoord"},
        )
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["status"], "success")
        self.assertFalse(saved["secrets_returned"])
        self.assertNotIn("openai-test-secret-1234", response.text)

    def test_ollama_create_payload_uses_current_from_system_parameters_shape(self):
        payload = self.main._ollama_create_payload_from_modelfile(
            {"base_model": "llama3.2:latest"},
            'FROM llama3.2:latest\nPARAMETER temperature 0.15\nPARAMETER num_ctx 8192\nSYSTEM """\nHallo Ouroboros\n"""\n',
        )

        self.assertEqual(payload["model"], "ouroboros")
        self.assertEqual(payload["from"], "llama3.2:latest")
        self.assertEqual(payload["parameters"]["temperature"], 0.15)
        self.assertEqual(payload["parameters"]["num_ctx"], 8192)
        self.assertEqual(payload["system"], "Hallo Ouroboros")
        self.assertNotIn("modelfile", payload)


if __name__ == "__main__":
    unittest.main()
