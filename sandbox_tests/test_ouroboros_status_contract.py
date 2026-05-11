import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""

from controller.ouroboros_status import compose_ouroboros_status


class FakeOllama:
    def __init__(self, models=None, error=None):
        self.model = "llama3.2:latest"
        self.models = list(models or [])
        self.error = error

    def list_models(self):
        if self.error:
            raise RuntimeError(self.error)
        return list(self.models)


class FakeAgentTools:
    def __init__(self, last_tool_result=None):
        self.last_tool_result = last_tool_result

    def status(self):
        return {"status": "online", "last_tool_result": self.last_tool_result}


class TestOuroborosStatusContract(unittest.TestCase):
    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.workspace_tmp = tempfile.TemporaryDirectory(prefix="ouroboros-status-ziel-")
        os.environ["WINTRIP_WORKSPACE"] = self.workspace_tmp.name
        ziel = Path(self.workspace_tmp.name) / ".agents" / "agent_types" / "type_2" / "Ziel.md"
        ziel.parent.mkdir(parents=True)
        ziel.write_text("# Zielenboek\n\n1. **Innerlijke Dialoog:** Blijf lokaal.\n", encoding="utf-8")

    def tearDown(self):
        self.workspace_tmp.cleanup()
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace

    def test_helper_contract_composes_extended_status_without_live_services(self):
        last_tool = {
            "tool_name": "run_tests",
            "status": "blocked",
            "stdout": "collected 3 tests",
            "stderr": "Run Tests wacht op Akkoord.",
            "stored_to_memory": False,
            "approval_status": "pending_philip_akkoord",
        }
        records = {
            "main_collection_count": 4,
            "training_collection_count": 2,
            "total_count": 6,
            "recent_training_ids": ["train-1"],
            "recent_training_metadatas": [{"dimension_count": 11, "dream_hz": 432.0}],
            "recent_training_documents": ["approved learning"],
        }

        data = compose_ouroboros_status(
            model_name="ouroboros",
            ollama_client=FakeOllama(
                [
                    "llama3.2:latest",
                    "mistral:latest",
                    "phi3:latest",
                    "deepseek-coder:latest",
                ]
            ),
            provider_status={
                "gemini": {"available": False, "version": "CLI niet gevonden"},
                "claude": {"available": True, "version": "Claude Code 1.0"},
            },
            agent_tools=FakeAgentTools(last_tool),
            records=records,
            geometry_11d={
                "dimension_count": 11,
                "dream_hz": 432.0,
                "radius": 1.1,
                "volume": 2.2,
                "oppervlakte": 3.3,
                "record_count": 6,
            },
            model_state={
                "active_base": "llama3.2:latest",
                "create_flow": {"status": "prepared", "created": False},
            },
            roo_adapter={"available": False, "reason": "not installed in sandbox"},
            self_modification_pipeline={
                "status": "approval_required",
                "approval_required": True,
                "last_run": None,
            },
            training_events=[{"kind": "stored", "dream_hz": 432.0}],
        )

        self.assertEqual(data["status"], "online")
        self.assertEqual(data["ollama"]["available_models"][0], "llama3.2:latest")
        self.assertEqual(data["model"]["available_bases"], data["ollama"]["available_models"])
        self.assertEqual(data["role_models"]["Developer"]["model"], "deepseek-coder:latest")
        self.assertEqual(data["role_models"]["Researcher"]["model"], "mistral:latest")
        self.assertEqual(data["role_models"]["Critic"]["model"], "mistral:latest")
        self.assertEqual(data["role_models"]["Tester"]["model"], "mistral:latest")

        self.assertEqual(data["external_providers"]["policy"], "blocked_by_default")
        self.assertIn("gemini", data["blocked_external_providers"])
        self.assertIn("claude", data["blocked_external_providers"])
        self.assertTrue(data["external_providers"]["blocked"]["claude"]["blocked"])
        self.assertEqual(data["roo_adapter"]["status"], "unavailable")

        self.assertEqual(data["last_tool_call"]["tool_name"], "run_tests")
        self.assertEqual(data["last_tool_call"]["status"], "blocked")
        self.assertEqual(data["stdout"], "collected 3 tests")
        self.assertEqual(data["stderr"], "Run Tests wacht op Akkoord.")
        self.assertEqual(data["self_modification_pipeline"]["status"], "approval_required")
        self.assertEqual(data["ziel_policy"]["status"], "loaded")
        self.assertEqual(data["ziel_policy"]["principle_count"], 1)
        self.assertIn("ToolBridge", " ".join(data["ziel_policy"]["guardrails"]))
        self.assertEqual(data["learning_11d"]["status"], "learning")
        self.assertTrue(data["learning_11d"]["chromadb"]["available"])
        self.assertFalse(data["fine_tune"]["fake_success"])
        self.assertFalse(data["integrity"]["fake_fine_tune_success"])
        self.assertFalse(data["integrity"]["fake_tool_success"])

    def test_helper_reports_not_run_instead_of_fake_success_when_dependencies_are_absent(self):
        data = compose_ouroboros_status(
            ollama_client=FakeOllama(error="ollama offline"),
            provider_status=lambda: (_ for _ in ()).throw(RuntimeError("provider check failed")),
            agent_tools=FakeAgentTools(),
        )

        self.assertFalse(data["ollama"]["online"])
        self.assertEqual(data["ollama"]["inventory_error"], "ollama offline")
        self.assertEqual(data["model"]["status"], "offline")
        self.assertEqual(data["last_tool_call"]["status"], "not_run")
        self.assertEqual(data["stdout"], "")
        self.assertEqual(data["stderr"], "")
        self.assertEqual(data["learning_11d"]["status"], "unavailable")
        self.assertEqual(data["self_modification_pipeline"]["status"], "not_configured")
        self.assertEqual(data["fine_tune"]["status"], "not_configured")
        self.assertTrue(all(not role["available"] for role in data["role_models"].values()))
        self.assertFalse(data["integrity"]["fake_fine_tune_success"])
        self.assertFalse(data["integrity"]["fake_tool_success"])


@unittest.skipIf(TestClient is None, MISSING_FASTAPI)
class TestOuroborosStatusRouteWithExistingFakes(unittest.TestCase):
    def setUp(self):
        self.previous_main = sys.modules.pop("controller.main", None)
        self.addCleanup(self._restore_previous_main)

    def _restore_previous_main(self):
        sys.modules.pop("controller.main", None)
        if self.previous_main is not None:
            sys.modules["controller.main"] = self.previous_main

    def test_testclient_route_can_serve_composed_contract_without_touching_main_py(self):
        from sandbox_tests.test_api_ouroboros_phase1 import install_main_fakes, restore_modules

        os.environ["WINTRIP_DB_PATH"] = tempfile.mkdtemp(prefix="ouroboros-status-contract-")
        originals = install_main_fakes()
        try:
            import controller.main as main
        finally:
            restore_modules(originals)

        main.agent_tools.last_tool_result = {
            "tool_name": "inspect_hippocampus",
            "status": "success",
            "stdout": "main_collection_count=4",
            "stderr": "",
            "stored_to_memory": False,
        }
        main.app.state.self_modification_pipeline = {
            "status": "idle",
            "approval_required": True,
        }
        main.app.state.roo_adapter = {"available": False, "reason": "not wired in tests"}

        def extended_status(extra=None):
            models = main._safe_model_names()
            records = main._hippocampus_records(limit=3)
            payload = compose_ouroboros_status(
                model_name=main.OUROBOROS_MODEL_NAME,
                available_models=models,
                active_base=main._active_base(models),
                provider_status=main.check_providers,
                agent_tools=main.agent_tools,
                records=records,
                geometry_11d=main._geometry_11d(records=records),
                browser_research=getattr(main.app.state, "ouroboros_browser_research", None),
                model_state=main._ensure_ouroboros_model_state(models),
                capabilities=main._ouroboros_capabilities(),
                roo_adapter=getattr(main.app.state, "roo_adapter", None),
                self_modification_pipeline=getattr(main.app.state, "self_modification_pipeline", None),
                training_events=getattr(main.app.state, "training_events", []),
                extra=extra,
            )
            return payload

        main._ouroboros_status_payload = extended_status

        response = TestClient(main.app).get("/api/ouroboros/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("ollama", data)
        self.assertIn("role_models", data)
        self.assertIn("blocked_external_providers", data)
        self.assertIn("roo_adapter", data)
        self.assertIn("self_modification_pipeline", data)
        self.assertIn("learning_11d", data)
        self.assertEqual(data["last_tool_call"]["stdout"], "main_collection_count=4")
        self.assertFalse(data["integrity"]["fake_tool_success"])
        self.assertFalse(data["integrity"]["fake_fine_tune_success"])


if __name__ == "__main__":
    unittest.main()
