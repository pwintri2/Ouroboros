import json
import os
import tempfile
import unittest
from pathlib import Path

from controller import ouroboros_self_context as self_context


class TestOuroborosSelfContext(unittest.TestCase):
    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_ruflo = os.environ.get("WINTRIP_RUFLO_PATH")
        self.old_bridge = os.environ.get("WINTRIP_RCLONE_BRIDGE_URL")
        self.workspace_tmp = tempfile.TemporaryDirectory(prefix="wintrip-self-context-")
        self.ruflo_tmp = tempfile.TemporaryDirectory(prefix="wintrip-ruflo-context-")
        os.environ["WINTRIP_WORKSPACE"] = self.workspace_tmp.name
        os.environ["WINTRIP_RUFLO_PATH"] = self.ruflo_tmp.name
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)

        root = Path(self.ruflo_tmp.name)
        (root / "package.json").write_text(
            json.dumps({"name": "ruflo-test", "version": "1.2.3", "description": "test ruflo"}),
            encoding="utf-8",
        )
        (root / ".claude" / "agents").mkdir(parents=True)
        (root / ".claude" / "agents" / "python-specialist.md").write_text("agent", encoding="utf-8")
        (root / "plugins" / "ruflo-core").mkdir(parents=True)
        (root / ".agents" / "skills" / "memory-management").mkdir(parents=True)
        type_2 = Path(self.workspace_tmp.name) / ".agents" / "agent_types" / "type_2"
        type_2.mkdir(parents=True)
        (type_2 / "Ziel.md").write_text("# Zielenboek\n\n1. Blijf wakker.\n", encoding="utf-8")

    def tearDown(self):
        self.workspace_tmp.cleanup()
        self.ruflo_tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.old_workspace)
        self._restore("WINTRIP_RUFLO_PATH", self.old_ruflo)
        self._restore("WINTRIP_RCLONE_BRIDGE_URL", self.old_bridge)

    def test_build_chat_context_includes_identity_paths_and_ruflo_status(self):
        context = self_context.build_chat_context(
            prompt="Wie ben je?",
            provider="google",
            model="gemini-test",
            conversation_id="diti",
        )

        self.assertEqual(context["conversation_id"], "diti")
        self.assertIn("Ouroboros self-context", context["system_prompt"])
        self.assertIn(self.workspace_tmp.name, context["system_prompt"])
        self.assertEqual(context["self_context"]["ruflo"]["package"]["name"], "ruflo-test")
        self.assertIn("python-specialist", context["self_context"]["ruflo"]["agents"])
        agent_types = context["self_context"]["ouroboros_agent_types"]
        self.assertEqual(agent_types["type_count"], 1)
        self.assertTrue(agent_types["types"][0]["has_ziel"])
        self.assertIn("Ouroboros agent types: type_2(Ziel)", context["system_prompt"])

    def test_recorded_turn_returns_as_server_history_without_secret_leak(self):
        self_context.record_chat_turn(
            prompt="Onthoud dit project. GOOGLE_API_KEY=supersecret123456789",
            response="Ik onthoud WintripAI als root.",
            provider="google",
            model="gemini-test",
            conversation_id="diti",
        )

        context = self_context.build_chat_context(
            prompt="Wat was net belangrijk?",
            provider="google",
            model="gemini-test",
            conversation_id="diti",
        )
        serialized = json.dumps(context, ensure_ascii=False)
        state_text = self_context.self_context_state_path().read_text(encoding="utf-8")

        self.assertEqual(context["server_history_count"], 2)
        self.assertIn("Onthoud dit project", serialized)
        self.assertIn("Ik onthoud WintripAI", serialized)
        self.assertNotIn("supersecret123456789", serialized)
        self.assertNotIn("supersecret123456789", state_text)

    def test_relevant_lessons_survive_beyond_recent_history_window(self):
        self_context.record_chat_turn(
            prompt="Belangrijke les: slash_agent_router.py routeert slash agents voor Ouroboros.",
            response="Gebruik controller/slash_agent_router.py wanneer cockpit slash-opdrachten binnenkomen.",
            provider="ollama",
            model="gemma",
            conversation_id="long-run",
        )
        for index in range(12):
            self_context.record_chat_turn(
                prompt=f"Filler beurt {index}: alleen algemene statusinformatie.",
                response="Korte filler respons.",
                provider="ollama",
                model="gemma",
                conversation_id="long-run",
            )

        context = self_context.build_chat_context(
            prompt="Waar zit de slash agent router?",
            provider="ollama",
            model="gemma",
            conversation_id="long-run",
        )

        self.assertEqual(context["self_context"]["matched_lesson_count"], 1)
        self.assertIn("Relevante lessen", context["system_prompt"])
        self.assertIn("controller/slash_agent_router.py", context["system_prompt"])

    def test_status_lists_latest_conversations_and_context_files(self):
        self_context.record_chat_turn(
            prompt="Hallo persistent geheugen",
            response="Hallo terug",
            provider="ollama",
            model="gemma",
            conversation_id="cockpit",
        )

        status = self_context.get_self_context_status()

        self.assertEqual(status["status"], "online")
        self.assertEqual(status["conversation_count"], 1)
        self.assertEqual(status["lesson_count"], 1)
        self.assertEqual(status["latest_conversations"][0]["conversation_id"], "cockpit")
        self.assertIn("WINTRIPAI_CONTEXT.md", status["ruflo"]["ide_context_files"][1])
        self.assertEqual(status["ouroboros_agent_types"]["types"][0]["id"], "type_2")

    def _restore(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
