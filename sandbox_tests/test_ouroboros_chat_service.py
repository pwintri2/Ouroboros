import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeHTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FakeAPIRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def post(self, path):
        def decorator(func):
            self.routes.append(("POST", path, func.__name__))
            return func

        return decorator

    def get(self, path):
        def decorator(func):
            self.routes.append(("GET", path, func.__name__))
            return func

        return decorator

    def put(self, path):
        def decorator(func):
            self.routes.append(("PUT", path, func.__name__))
            return func

        return decorator

    def delete(self, path):
        def decorator(func):
            self.routes.append(("DELETE", path, func.__name__))
            return func

        return decorator


def load_ouroboros_chat_module():
    """Import the service even when FastAPI is absent from the sandbox image."""

    fake_fastapi = types.ModuleType("fastapi")
    fake_fastapi.APIRouter = FakeAPIRouter
    fake_fastapi.HTTPException = FakeHTTPException
    fake_fastapi.Request = object
    fake_fastapi.UploadFile = object
    fake_fastapi.File = lambda *args, **kwargs: None
    sys.modules.pop("controller.ouroboros_chat", None)
    with patch.dict(sys.modules, {"fastapi": fake_fastapi}):
        return importlib.import_module("controller.ouroboros_chat")


class FakeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return "service antwoord"


class TestOuroborosChatService(unittest.TestCase):
    def setUp(self):
        self.module = load_ouroboros_chat_module()
        self.tmp = tempfile.TemporaryDirectory(prefix="ouroboros-chat-service-")
        root = Path(self.tmp.name)
        self.data_dir = root / "data" / "ouroboros_chat"
        self.cline_root = root / "cline"
        (self.cline_root / "docs" / "core-workflows").mkdir(parents=True)
        (self.cline_root / "docs" / "customization").mkdir(parents=True)
        (self.cline_root / "README.md").write_text(
            "# Cline\napi_key = SECRET_VALUE_SHOULD_REDACT_123456\n",
            encoding="utf-8",
        )
        (self.cline_root / "docs" / "core-workflows" / "plan-and-act.mdx").write_text(
            "# Plan and Act\n",
            encoding="utf-8",
        )
        (self.cline_root / "docs" / "customization" / "cline-rules.mdx").write_text(
            "# Cline Rules\n",
            encoding="utf-8",
        )
        (self.cline_root / ".env.example").write_text("TOKEN=DISALLOWED_123456789\n", encoding="utf-8")
        self.fake_ollama = FakeOllama()
        self.service = self.module.OuroborosChatService(
            data_dir=self.data_dir,
            cline_root=self.cline_root,
            ollama_client=self.fake_ollama,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_chat_defaults_to_local_ollama_ouroboros(self):
        request = self.module.OuroborosChatRequest(prompt="Hallo")
        payload = self.service.chat(request)

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["model"], "ouroboros:latest")
        self.assertEqual(payload["response"], "service antwoord")
        self.assertEqual(payload["approval_phrase"], "Akkoord")
        self.assertEqual(self.fake_ollama.calls[0]["model"], "ouroboros:latest")

    def test_text_attachment_is_transient_context_and_image_blocks_for_text_model(self):
        note = self.data_dir / "uploads" / "note.md"
        note.parent.mkdir(parents=True)
        note.write_text("Belangrijke projectcontext.", encoding="utf-8")
        payload = self.service.chat(self.module.OuroborosChatRequest(prompt="Vat samen", files=[str(note)]))

        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["transient_attachment_context"])
        self.assertEqual(self.fake_ollama.calls[-1]["user_input"], "Vat samen")
        self.assertIn("Belangrijke projectcontext", self.fake_ollama.calls[-1]["system_prompt"])

        image = self.data_dir / "uploads" / "mock.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        blocked = self.service.chat(self.module.OuroborosChatRequest(prompt="Wat zie je?", files=[str(image)]))

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["reason"], "image_model_unsupported")
        self.assertFalse(blocked["fake_success"])

    def test_cline_capabilities_only_read_allowlisted_redacted_files(self):
        payload = self.service.cline_capabilities()
        serialized = str(payload)

        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["executed"])
        self.assertNotIn(".env.example", payload["allowlisted_files"])
        self.assertNotIn("DISALLOWED", serialized)
        self.assertNotIn("SECRET_VALUE_SHOULD_REDACT", serialized)
        self.assertIn("[REDACTED]", serialized)
        paths = {item["path"] for item in payload["files"]}
        self.assertIn("README.md", paths)
        self.assertIn("docs/core-workflows/plan-and-act.mdx", paths)
        self.assertNotIn(".env.example", paths)

    def test_persona_store_rejects_secret_like_content(self):
        clean = self.service.personas.upsert(
            self.module.PersonaRequest(id="critic", name="Critic", system_prompt="Review risks.")
        )
        self.assertEqual(clean["id"], "critic")

        with self.assertRaises(ValueError):
            self.service.personas.upsert(
                self.module.PersonaRequest(
                    id="leaky",
                    name="Leaky",
                    description="token = SECRET_VALUE_123456789",
                )
            )
        self.assertNotIn("SECRET_VALUE", (self.data_dir / "personas.json").read_text(encoding="utf-8"))

    def test_legacy_personas_are_normalized_for_chat_and_meetings(self):
        self.service.personas.path.parent.mkdir(parents=True, exist_ok=True)
        self.service.personas.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "personas": [
                        {
                            "id": "old-style",
                            "name": "Old Style",
                            "system_prompt": "Use the old stored instruction.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        persona = self.service.personas.get("old-style")
        self.assertEqual(persona["id"], "old-style")
        self.assertEqual(persona["model_settings"]["provider"], "ollama")
        self.assertEqual(persona["model_settings"]["name"], "ouroboros:latest")
        self.assertTrue(persona["tools"]["file_search"])
        self.assertTrue(persona["memory"]["enabled"])

    def test_default_meeting_personas_are_seeded_with_web_search_and_claude_models(self):
        personas = {item["id"]: item for item in self.service.personas.list_personas()}

        self.assertIn("de-voorzitter", personas)
        self.assertIn("de-ontwerper", personas)
        self.assertIn("de-criticus", personas)
        self.assertTrue(personas["de-voorzitter"]["builtin"])
        self.assertTrue(personas["de-voorzitter"]["tools"]["web_search"])
        self.assertEqual(personas["de-voorzitter"]["model_settings"]["provider"], "anthropic")
        self.assertTrue(personas["de-voorzitter"]["knowledge_sources"])

    def test_custom_persona_assembles_prompt_memory_knowledge_tools_and_conversation(self):
        knowledge = self.data_dir / "uploads" / "monique-atelier.md"
        knowledge.parent.mkdir(parents=True)
        knowledge.write_text(
            "Monique Botje bewaakt keramische planning, rustige feedback en concrete vervolgstappen.",
            encoding="utf-8",
        )
        persona = self.service.personas.upsert(
            self.module.PersonaRequest(
                id="monique-botje",
                name="Monique Botje",
                description="Een ateliercoach voor maakwerk.",
                role="Ateliercoach",
                introduction="Ik help rustig en praktisch met maakprocessen.",
                instructions="Antwoord als Monique Botje: kort, warm en concreet.",
                tone="Warm, nuchter, precies",
                language="nl",
                rules=["Gebruik alleen voorstellen voor acties met externe impact."],
                tools={"file_search": True, "local_shell": True, "web_search": False},
                memory={"enabled": True, "scope": "persona"},
                model_settings={
                    "provider": "ollama",
                    "name": "ouroboros:latest",
                    "temperature": 0.3,
                    "max_tokens": 1200,
                },
                knowledge_files=[{"path": str(knowledge), "label": "Ateliernotities"}],
            )
        )
        self.assertEqual(persona["id"], "monique-botje")

        self.service.memory.create(
            {
                "persona_id": "monique-botje",
                "scope": "persona",
                "content": "Monique geeft graag puntsgewijze antwoorden.",
                "importance": 5,
            }
        )
        payload = self.service.chat(
            self.module.OuroborosChatRequest(
                prompt="Wat weet je over keramische planning?",
                persona_id="monique-botje",
                conversation_id="thread-monique",
            )
        )

        system_prompt = self.fake_ollama.calls[-1]["system_prompt"]
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["persona_id"], "monique-botje")
        self.assertIn("Persona name: Monique Botje", system_prompt)
        self.assertIn("Antwoord als Monique Botje", system_prompt)
        self.assertIn("Monique geeft graag puntsgewijze antwoorden", system_prompt)
        self.assertIn("Ateliernotities", system_prompt)
        self.assertIn("keramische planning", system_prompt)
        self.assertIn("local_shell", payload["tool_policy"]["requires_approval"])

        conversation = self.service.conversations.get("thread-monique")
        self.assertEqual(conversation["persona_id"], "monique-botje")
        self.assertEqual(len(conversation["messages"]), 2)
        self.assertEqual(conversation["messages"][0]["role"], "user")

    def test_persona_memory_can_be_disabled_and_personas_roundtrip_json(self):
        imported = self.service.personas.import_persona(
            {
                "id": "stateless-reviewer",
                "name": "Stateless Reviewer",
                "instructions": "Review only what is in the current prompt.",
                "memory": {"enabled": False, "scope": "persona"},
                "tools": {"file_search": False, "web_search": False},
            }
        )
        self.service.memory.create(
            {
                "persona_id": "stateless-reviewer",
                "scope": "persona",
                "content": "This disabled memory must not enter the runtime prompt.",
                "importance": 5,
            }
        )
        self.service.chat(
            self.module.OuroborosChatRequest(
                prompt="Review dit.",
                persona_id="stateless-reviewer",
            )
        )

        system_prompt = self.fake_ollama.calls[-1]["system_prompt"]
        self.assertIn("Stateless Reviewer", system_prompt)
        self.assertNotIn("This disabled memory", system_prompt)

        duplicate = self.service.personas.duplicate(imported["id"])
        self.assertNotEqual(duplicate["id"], imported["id"])
        self.assertEqual(duplicate["instructions"], imported["instructions"])

    def test_meetings_write_jsonl_only_and_block_tools(self):
        self.service.personas.upsert(
            self.module.PersonaRequest(
                id="critic",
                name="Critic",
                role="Risk reviewer",
                rules=["Noem regressierisico's."],
                system_prompt="Review risks and tests.",
            )
        )

        recorded = self.service.create_meeting(
            self.module.MeetingRequest(topic="Plan backend handoff", participants=["ouroboros", "critic"], approval="Akkoord")
        )
        self.assertEqual(recorded["status"], "recorded")
        self.assertFalse(recorded["tool_policy"]["cline_execution"])
        self.assertFalse(recorded["tool_policy"]["shell"])
        self.assertFalse(recorded["tool_policy"]["browser"])
        self.assertFalse(recorded["tool_policy"]["write_tools"])
        self.assertEqual(len(recorded["participants"]), 2)
        self.assertEqual(len(recorded["rounds"]), 4)
        self.assertEqual(recorded["summary"], "service antwoord")
        self.assertEqual(len(self.fake_ollama.calls), 5)
        self.assertIn("Andere aanwezigen", self.fake_ollama.calls[0]["system_prompt"])
        self.assertIn("Jouw Rol", self.fake_ollama.calls[0]["system_prompt"])
        self.assertIn("Volledige transcriptie tot nu toe", self.fake_ollama.calls[2]["user_input"])

        artifact = Path(recorded["artifact_path"])
        self.assertEqual(artifact.parent, self.data_dir / "meetings")
        lines = [json.loads(line) for line in artifact.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), recorded["event_count"])
        self.assertEqual(lines[0]["approval_phrase"], "Akkoord")
        self.assertTrue(Path(recorded["record_path"]).exists())
        readback = self.service.meetings.read_meeting(recorded["meeting_id"])
        self.assertEqual(readback["summary"], "service antwoord")
        self.assertEqual(len(readback["rounds"]), 4)

        blocked = self.service.meetings.create_meeting(
            self.module.MeetingRequest(topic="Execute tools", tools=["cline_execute", "safe_shell"], allow_tools=True),
            self.service.personas,
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("cline_execute", blocked["forbidden_tools"])
        self.assertIn("safe_shell", blocked["forbidden_tools"])

    def test_meeting_snapshot_can_be_saved_and_listed_without_jsonl(self):
        saved = self.service.meetings.save_snapshot(
            "manual-review",
            self.module.MeetingSaveRequest(
                topic="Manual review",
                participants=[{"id": "de-voorzitter", "name": "De voorzitter"}],
                participant_ids=["de-voorzitter"],
                rounds=[
                    {
                        "id": "round-1",
                        "phase": "saved",
                        "participantId": "de-voorzitter",
                        "participantName": "De voorzitter",
                        "content": "Besluit: opslaan.",
                    }
                ],
                summary="Consensus: bewaren.",
                transcript="De voorzitter: Besluit: opslaan.",
            ),
        )

        self.assertEqual(saved["status"], "saved")
        listed = self.service.meetings.list_meetings()
        self.assertEqual(listed[0]["meeting_id"], "manual-review")
        readback = self.service.meetings.read_meeting("manual-review")
        self.assertEqual(readback["summary"], "Consensus: bewaren.")
        self.assertEqual(readback["artifact_path"], "")


if __name__ == "__main__":
    unittest.main()
