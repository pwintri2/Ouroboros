import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_external_capabilities_honor_container_mount_env(self):
        old_agents = os.environ.get("WINTRIP_AGENTS_PATH")
        old_openhands = os.environ.get("WINTRIP_OPENHANDS_PATH")
        old_deepseek = os.environ.get("WINTRIP_DEEPSEEK_PATH")
        old_atlas = os.environ.get("WINTRIP_ATLAS_PATH")
        try:
            with (
                tempfile.TemporaryDirectory(prefix="agents-root-") as agents_tmp,
                tempfile.TemporaryDirectory(prefix="openhands-root-") as openhands_tmp,
                tempfile.TemporaryDirectory(prefix="deepseek-root-") as deepseek_tmp,
                tempfile.TemporaryDirectory(prefix="atlas-root-") as atlas_tmp,
            ):
                agents_root = Path(agents_tmp)
                openhands_root = Path(openhands_tmp)
                deepseek_root = Path(deepseek_tmp)
                atlas_root = Path(atlas_tmp)
                (agents_root / "gui_agents").mkdir()
                (openhands_root / "openhands").mkdir()
                (deepseek_root / "docs").mkdir()
                (atlas_root / "context").mkdir()
                os.environ["WINTRIP_AGENTS_PATH"] = str(agents_root)
                os.environ["WINTRIP_OPENHANDS_PATH"] = str(openhands_root)
                os.environ["WINTRIP_DEEPSEEK_PATH"] = str(deepseek_root)
                os.environ["WINTRIP_ATLAS_PATH"] = str(atlas_root)

                status = external_capabilities_status(prefer_bridge=False)

            self.assertEqual(status["capabilities"]["agents"]["status"], "available")
            self.assertEqual(status["capabilities"]["openhands"]["status"], "available")
            self.assertEqual(status["capabilities"]["deepseek"]["status"], "available")
            self.assertEqual(status["capabilities"]["atlas"]["status"], "available")
            self.assertEqual(status["capabilities"]["agents"]["root"], str(agents_root))
            self.assertEqual(status["capabilities"]["openhands"]["root"], str(openhands_root))
            self.assertEqual(status["capabilities"]["deepseek"]["root"], str(deepseek_root))
            self.assertEqual(status["capabilities"]["atlas"]["root"], str(atlas_root))
        finally:
            if old_agents is None:
                os.environ.pop("WINTRIP_AGENTS_PATH", None)
            else:
                os.environ["WINTRIP_AGENTS_PATH"] = old_agents
            if old_openhands is None:
                os.environ.pop("WINTRIP_OPENHANDS_PATH", None)
            else:
                os.environ["WINTRIP_OPENHANDS_PATH"] = old_openhands
            if old_deepseek is None:
                os.environ.pop("WINTRIP_DEEPSEEK_PATH", None)
            else:
                os.environ["WINTRIP_DEEPSEEK_PATH"] = old_deepseek
            if old_atlas is None:
                os.environ.pop("WINTRIP_ATLAS_PATH", None)
            else:
                os.environ["WINTRIP_ATLAS_PATH"] = old_atlas

    def test_external_capabilities_augments_stale_bridge_payload_with_deepseek_atlas(self):
        old_deepseek = os.environ.get("WINTRIP_DEEPSEEK_PATH")
        old_atlas = os.environ.get("WINTRIP_ATLAS_PATH")
        try:
            with tempfile.TemporaryDirectory(prefix="deepseek-root-") as deepseek_tmp, tempfile.TemporaryDirectory(prefix="atlas-root-") as atlas_tmp:
                deepseek_root = Path(deepseek_tmp)
                atlas_root = Path(atlas_tmp)
                (deepseek_root / "docs").mkdir()
                (atlas_root / "context").mkdir()
                os.environ["WINTRIP_DEEPSEEK_PATH"] = str(deepseek_root)
                os.environ["WINTRIP_ATLAS_PATH"] = str(atlas_root)

                with patch(
                    "controller.external_capabilities._bridge_request",
                    return_value={
                        "status": "online",
                        "capabilities": {"agents": {"status": "available"}, "openhands": {"status": "available"}},
                    },
                ):
                    status = external_capabilities_status()

            self.assertTrue(status["via_bridge"])
            self.assertEqual(status["capabilities"]["deepseek"]["status"], "available")
            self.assertEqual(status["capabilities"]["atlas"]["status"], "available")
            self.assertIn("DeepSeek/Atlas", status["tool_schemas"][0]["function"]["description"])
        finally:
            if old_deepseek is None:
                os.environ.pop("WINTRIP_DEEPSEEK_PATH", None)
            else:
                os.environ["WINTRIP_DEEPSEEK_PATH"] = old_deepseek
            if old_atlas is None:
                os.environ.pop("WINTRIP_ATLAS_PATH", None)
            else:
                os.environ["WINTRIP_ATLAS_PATH"] = old_atlas


if __name__ == "__main__":
    unittest.main()
