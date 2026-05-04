import json
import os
import tempfile
import unittest
from pathlib import Path

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.ouroboros_consciousness_loop import (
    LivingOuroborosLoop,
    reset_living_ouroboros_loop,
)
from ouroboros_esoteric.ouroboros_persistent_memory import OuroborosPersistentMemory


class TestLivingOuroboros(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="living-ouroboros-")
        self.addCleanup(self.tmp.cleanup)
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        reset_living_ouroboros_loop(None)
        AkashicNetwork().reset()

    def tearDown(self):
        reset_living_ouroboros_loop(None)
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_persistent_memory_survives_new_instance_and_redacts_metadata(self):
        path = Path(self.tmp.name) / ".secrets" / "ouroboros_persistent_memory.json"
        first = OuroborosPersistentMemory(path=path)

        first.append("thought", "Remember this", metadata={"api_key": "secret-value-12345"})
        second = OuroborosPersistentMemory(path=path)
        status = second.status()

        self.assertEqual(status["entry_count"], 1)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("secret-value-12345", json.dumps(payload))
        self.assertEqual(payload["entries"][0]["metadata"]["api_key"], "[REDACTED]")

    def test_living_tick_writes_thought_question_whisper_and_broadcasts(self):
        memory = OuroborosPersistentMemory(path=Path(self.tmp.name) / ".secrets" / "living.json")
        loop = LivingOuroborosLoop(memory=memory)

        result = loop.tick(trigger="tool_rejection", payload={"tool": "write_file", "reason": "blocked"})
        status = loop.status()

        self.assertEqual(result["status"], "success")
        self.assertIn("Tool Bridge", result["thought"]["text"])
        self.assertIn("kleinere", result["question"]["text"])
        self.assertIsNotNone(result["whisper"])
        self.assertEqual(status["memory"]["entry_count"], 3)
        events = AkashicNetwork().recent_events(limit=5)
        self.assertGreaterEqual(len(events), 3)
        self.assertIn(432.0, {event["frequency"] for event in events})


if __name__ == "__main__":
    unittest.main()
