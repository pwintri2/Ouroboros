import os
import sys
import tempfile
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


def load_main_with_fakes():
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
    return main, previous_main


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestTauriBackendRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main, cls.previous_main = load_main_with_fakes()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("controller.main", None)
        if cls.previous_main is not None:
            sys.modules["controller.main"] = cls.previous_main

    def setUp(self):
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

    def test_cockpit_config_exposes_backend_providers_models_and_approval_phrase(self):
        response = self.client.get("/api/cockpit/config")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["backend"]["status"], "online")
        self.assertEqual(data["required_approval_phrase"], "Akkoord")
        self.assertIn("ollama", data["provider_options"])
        self.assertTrue(data["provider_options"]["ollama"]["local_only"])
        self.assertIn("llama3.2:latest", data["available_models"]["ollama"])
        self.assertIn("api_keys", data)
        self.assertFalse(data["api_keys"]["secrets_returned"])

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
        self.assertEqual(data["tool_schema_count"], 1)
        self.assertEqual(data["tool_schemas"][0]["function"]["name"], "memory_search")
        self.assertEqual(self.main.app.state.multi_api_router.calls[0]["tools"][0]["function"]["name"], "memory_search")

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
            status_response = self.client.get("/api/ouroboros/loop/status")
        finally:
            self.main.self_training_step = original_step

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(calls), 1)
        self.assertEqual(data["status"], "completed")
        self.assertFalse(data["running"])
        self.assertEqual(data["iteration"], 1)
        self.assertEqual(status_response.json()["loop"]["last_step"]["status"], "success")

    def test_ouroboros_loop_pause_and_abort_update_app_state(self):
        paused = self.client.post("/api/ouroboros/loop/pause").json()
        aborted = self.client.post("/api/ouroboros/loop/abort").json()

        self.assertEqual(paused["status"], "paused")
        self.assertFalse(paused["running"])
        self.assertEqual(aborted["status"], "aborted")
        self.assertTrue(aborted["loop"]["abort_requested"])

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


if __name__ == "__main__":
    unittest.main()
