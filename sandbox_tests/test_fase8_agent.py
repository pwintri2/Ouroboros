import os
import tempfile
import time
import unittest
from pathlib import Path

from controller.external_capabilities import external_capabilities_status
from controller.fase8_agent import Fase8Runner, Fase8Store, Fase8ToolDispatcher, create_plan


class FakeAgentTools:
    def __init__(self):
        self.calls = []

    def run_tool(self, tool_name, args=None):
        self.calls.append((tool_name, dict(args or {})))
        return {
            "status": "success",
            "tool_name": tool_name,
            "response": f"ran {tool_name}",
            "stdout": "ok",
            "stderr": "",
            "fake_success": False,
        }


class FakeOnlineDispatcher:
    def dispatch(self, tool_name, args=None):
        return {"status": "online", "tool_name": tool_name, "fake_success": False}


class TestFase8Agent(unittest.TestCase):
    def test_dispatcher_routes_explicit_grok_without_ollama_fallback(self):
        dispatcher = Fase8ToolDispatcher(agent_tools=FakeAgentTools())

        choice = dispatcher.choose("Kun je aan Grok vragen hoe je zelf verder moet ontwikkelen?", approval="Akkoord")

        self.assertEqual(choice["tool"], "world_grok_ask")
        self.assertEqual(choice["args"]["question"], "hoe je zelf verder moet ontwikkelen?")
        self.assertEqual(choice["args"]["approval"], "Akkoord")

    def test_plan_mentions_external_capabilities_when_requested(self):
        plan = create_plan("Voer Fase 8 uit en neem AgentS en OpenHands mee")

        tools = [step["tool"] for step in plan["steps"]]
        self.assertIn("external_capabilities_status", tools)
        self.assertGreaterEqual(plan["step_count"], 1)

    def test_runner_persists_task_and_runs_memory_step(self):
        tools = FakeAgentTools()
        with tempfile.TemporaryDirectory(prefix="fase8-store-") as tmp:
            store = Fase8Store(Path(tmp) / "tasks.json")
            runner = Fase8Runner(store=store, dispatcher=Fase8ToolDispatcher(agent_tools=tools))

            started = runner.run("wat weet je nog over Ouroboros?", approval="Akkoord", max_iterations=1)
            task_id = started["task_id"]
            deadline = time.time() + 2
            payload = runner.get(task_id)
            while payload.get("status") == "running" and time.time() < deadline:
                time.sleep(0.02)
                payload = runner.get(task_id)

            self.assertEqual(payload["status"], "completed")
            self.assertEqual(store.get(task_id)["status"], "completed")
            self.assertEqual(tools.calls[0][0], "memory_search")

    def test_runner_treats_external_online_status_as_success(self):
        with tempfile.TemporaryDirectory(prefix="fase8-store-") as tmp:
            store = Fase8Store(Path(tmp) / "tasks.json")
            runner = Fase8Runner(store=store, dispatcher=FakeOnlineDispatcher())

            started = runner.run("neem AgentS en OpenHands mee", approval="Akkoord", max_iterations=1)
            task_id = started["task_id"]
            deadline = time.time() + 2
            payload = runner.get(task_id)
            while payload.get("status") == "running" and time.time() < deadline:
                time.sleep(0.02)
                payload = runner.get(task_id)

            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["task"]["plan"]["steps"][0]["status"], "completed")

    def test_external_capability_scan_avoids_secret_like_entries(self):
        with tempfile.TemporaryDirectory(prefix="cap-scan-") as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("ok", encoding="utf-8")
            (root / ".env").write_text("SHOULD_NOT_READ", encoding="utf-8")
            status = external_capabilities_status({"custom": str(root)})

        text = str(status).lower()
        self.assertIn("custom", status["capabilities"])
        self.assertNotIn("should_not_read", text)
        self.assertNotIn(".env", text)


if __name__ == "__main__":
    unittest.main()
