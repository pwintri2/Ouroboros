import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    FastAPI = None
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""


class FakeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return "lokaal antwoord"


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestOuroborosChatRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ouroboros-chat-routes-")
        self.data_dir = Path(self.tmp.name) / "data" / "ouroboros_chat"
        self.cline_root = Path(self.tmp.name) / "cline"
        self.cline_root.mkdir()
        self.fake_ollama = FakeOllama()

        from controller.ouroboros_chat import OuroborosChatService, init_ouroboros_chat_routes

        app = FastAPI()
        service = OuroborosChatService(
            data_dir=self.data_dir,
            cline_root=self.cline_root,
            ollama_client=self.fake_ollama,
        )
        init_ouroboros_chat_routes(app, service=service)
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chat_defaults_to_ollama_ouroboros_latest(self):
        response = self.client.post("/api/ouroboros-chat/chat", json={"prompt": "Hallo Ouroboros"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["model"], "ouroboros:latest")
        self.assertEqual(payload["response"], "lokaal antwoord")
        self.assertEqual(payload["approval_phrase"], "Akkoord")
        self.assertFalse(payload["fake_success"])
        self.assertEqual(self.fake_ollama.calls[0]["model"], "ouroboros:latest")

    def test_chat_slash_commands_are_menu_only_in_this_router(self):
        response = self.client.post(
            "/api/ouroboros-chat/chat",
            json={"prompt": "/codex run wijzig bestanden", "approval": "Akkoord"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["route"], "slash_menu")
        self.assertIn("approval-gated cockpit router", payload["response"])
        self.assertEqual(self.fake_ollama.calls, [])

    def test_slash_menu_preserves_existing_approval_phrase(self):
        response = self.client.get("/api/ouroboros-chat/slash-menu")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["approval_phrase"], "Akkoord")
        self.assertIn("/agents", payload["commands"])
        self.assertEqual(payload["execution"], "not_executed_by_ouroboros_chat_router")
        self.assertFalse(payload["fake_success"])

    def test_model_options_expose_claude_and_brave_status_without_keys(self):
        response = self.client.get("/api/ouroboros-chat/model-options")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        providers = {item["id"]: item for item in payload["providers"]}
        self.assertIn("anthropic", providers)
        self.assertIn("claude-sonnet-4-6", providers["anthropic"]["models"])
        self.assertIn("brave", payload)
        self.assertFalse(payload["fake_success"])


if __name__ == "__main__":
    unittest.main()
