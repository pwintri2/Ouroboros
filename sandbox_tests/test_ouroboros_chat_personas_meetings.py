import json
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


class QuietOllama:
    def list_models(self):
        return ["quiet-local:latest", "ouroboros:latest"]

    def chat(self, **kwargs):
        return "ok"


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestOuroborosChatPersonasMeetings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ouroboros-chat-store-")
        root = Path(self.tmp.name)
        self.data_dir = root / "data" / "ouroboros_chat"
        self.cline_root = root / "cline"
        self.cline_root.mkdir()

        from controller.ouroboros_chat import OuroborosChatService, init_ouroboros_chat_routes

        app = FastAPI()
        service = OuroborosChatService(
            data_dir=self.data_dir,
            cline_root=self.cline_root,
            ollama_client=QuietOllama(),
        )
        init_ouroboros_chat_routes(app, service=service)
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_persona_store_saves_to_data_ouroboros_chat(self):
        response = self.client.post(
            "/api/ouroboros-chat/personas",
            json={
                "id": "critic",
                "name": "Critic",
                "description": "Checks risks and tests.",
                "system_prompt": "Stay practical and evidence-based.",
                "tags": ["review", "tests"],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "saved")
        self.assertEqual(payload["persona"]["id"], "critic")

        store_path = self.data_dir / "personas.json"
        self.assertTrue(store_path.exists())
        data = json.loads(store_path.read_text(encoding="utf-8"))
        ids = {item["id"] for item in data["personas"]}
        self.assertIn("critic", ids)

    def test_persona_store_rejects_secret_like_content(self):
        response = self.client.post(
            "/api/ouroboros-chat/personas",
            json={
                "id": "leaky",
                "name": "Leaky",
                "description": "api_key = SECRET_VALUE_123456789",
                "system_prompt": "Do not save this.",
            },
        )

        self.assertEqual(response.status_code, 400)
        if (self.data_dir / "personas.json").exists():
            self.assertNotIn("SECRET_VALUE", (self.data_dir / "personas.json").read_text(encoding="utf-8"))

    def test_meeting_records_jsonl_without_tools(self):
        self.client.post(
            "/api/ouroboros-chat/personas",
            json={"id": "tester", "name": "Tester", "system_prompt": "Validate outcomes."},
        )

        response = self.client.post(
            "/api/ouroboros-chat/meetings",
            json={"topic": "Plan a safe backend handoff", "participants": ["tester"], "approval": "Akkoord"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "recorded")
        self.assertFalse(payload["fake_success"])
        self.assertFalse(payload["tool_policy"]["cline_execution"])
        self.assertFalse(payload["tool_policy"]["shell"])
        self.assertFalse(payload["tool_policy"]["browser"])
        self.assertFalse(payload["tool_policy"]["write_tools"])

        artifact = Path(payload["artifact_path"])
        self.assertTrue(artifact.exists())
        self.assertEqual(artifact.parent, self.data_dir / "meetings")
        lines = [json.loads(line) for line in artifact.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), payload["event_count"])
        self.assertEqual(lines[0]["approval_phrase"], "Akkoord")
        serialized = str(lines).lower()
        self.assertIn("no cline execution", serialized)

        readback = self.client.get(f"/api/ouroboros-chat/meetings/{payload['meeting_id']}")
        self.assertEqual(readback.status_code, 200)
        self.assertEqual(readback.json()["meeting_id"], payload["meeting_id"])
        self.assertTrue(Path(payload["record_path"]).exists())

        saved = self.client.put(
            f"/api/ouroboros-chat/meetings/{payload['meeting_id']}",
            json={
                "topic": "Plan a safe backend handoff",
                "participants": payload["participants"],
                "participant_ids": ["tester"],
                "rounds": payload["rounds"],
                "summary": "Consensus: testen en bewaren.",
                "transcript": payload["transcript"],
                "status": "saved",
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "saved")

    def test_meeting_blocks_requested_cline_or_shell_tools(self):
        response = self.client.post(
            "/api/ouroboros-chat/meetings",
            json={"topic": "Run a Cline tool", "tools": ["cline_execute", "safe_shell"], "allow_tools": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("cline_execute", payload["forbidden_tools"])
        self.assertIn("safe_shell", payload["forbidden_tools"])
        self.assertFalse(payload["fake_success"])
        self.assertFalse((self.data_dir / "meetings").exists())


if __name__ == "__main__":
    unittest.main()
