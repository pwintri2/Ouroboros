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


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestOuroborosChatClineCapabilities(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ouroboros-chat-cline-")
        root = Path(self.tmp.name)
        self.data_dir = root / "data" / "ouroboros_chat"
        self.cline_root = root / "cline"
        (self.cline_root / "docs" / "core-workflows").mkdir(parents=True)
        (self.cline_root / "docs" / "customization").mkdir(parents=True)
        (self.cline_root / "README.md").write_text(
            "# Cline\n\nPlan tasks safely.\napi_key = SHOULD_NOT_LEAK_123456\n",
            encoding="utf-8",
        )
        (self.cline_root / "docs" / "core-workflows" / "plan-and-act.mdx").write_text(
            "# Plan and Act\n\nUse plans before changes.\n",
            encoding="utf-8",
        )
        (self.cline_root / "docs" / "customization" / "cline-rules.mdx").write_text(
            "# Cline Rules\n\nRules shape behavior.\n",
            encoding="utf-8",
        )
        (self.cline_root / ".env.example").write_text(
            "TOKEN=DISALLOWED_ENV_TOKEN_123456789\n",
            encoding="utf-8",
        )

        from controller.ouroboros_chat import OuroborosChatService, init_ouroboros_chat_routes

        app = FastAPI()
        service = OuroborosChatService(data_dir=self.data_dir, cline_root=self.cline_root, ollama_client=object())
        init_ouroboros_chat_routes(app, service=service)
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cline_capabilities_are_read_only_allowlisted_and_redacted(self):
        response = self.client.get("/api/ouroboros-chat/cline-capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        serialized = str(payload)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["executed"])
        self.assertFalse(payload["fake_success"])
        self.assertNotIn(".env.example", payload["allowlisted_files"])
        self.assertNotIn("DISALLOWED_ENV_TOKEN", serialized)
        self.assertNotIn("SHOULD_NOT_LEAK", serialized)
        self.assertIn("[REDACTED]", serialized)

        paths = {item["path"] for item in payload["files"]}
        self.assertIn("README.md", paths)
        self.assertIn("docs/core-workflows/plan-and-act.mdx", paths)
        self.assertNotIn(".env.example", paths)

        cards = {item["id"]: item for item in payload["capabilities"]}
        self.assertTrue(cards["plan_act"]["detected"])
        self.assertTrue(cards["cline_rules"]["detected"])
        for card in payload["capabilities"]:
            self.assertEqual(card["execution"], "read_only_context")


if __name__ == "__main__":
    unittest.main()
