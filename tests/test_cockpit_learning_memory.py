import unittest
from unittest.mock import patch

from controller import cockpit_learning_memory as memory


class TestCockpitLearningMemory(unittest.TestCase):
    def test_stores_redacted_trainable_cockpit_turn(self):
        stored_calls = []

        def fake_store(document, metadata):
            stored_calls.append((document, metadata))
            return {"status": "success", "stored": True, "item_id": "learn-1", "fake_success": False}

        result = {
            "status": "success",
            "route": "agentic_processor",
            "provider": "ollama",
            "model": "gemma4:latest",
            "response": "Ik heb dit uitgevoerd zonder token=SECRET123456 te bewaren.",
            "source_trace": {
                "brave_search_used": True,
                "brave_search_success": True,
                "tools_used": ["memory_search", "brave_search"],
                "memory_status": "stored",
            },
            "steps": [
                {"index": 1, "tool": "brave_search", "status": "success", "result": {"reason": "ok"}},
            ],
        }

        with (
            patch.object(memory, "_store_training_record", side_effect=fake_store),
            patch.object(memory, "_wake_continuous_trainer") as wake,
        ):
            stored = memory.store_cockpit_learning_turn(
                prompt="Gebruik api_key=SHOULD_NOT_LEAK voor test",
                result=result,
                provider="ollama",
                model="gemma4:latest",
                conversation_id="conv-1",
            )

        self.assertEqual(stored["status"], "success")
        self.assertTrue(stored["stored"])
        self.assertEqual(len(stored_calls), 1)
        document, metadata = stored_calls[0]
        self.assertNotIn("SHOULD_NOT_LEAK", document)
        self.assertNotIn("SECRET123456", document)
        self.assertEqual(metadata["type"], "cockpit_learning_turn")
        self.assertEqual(metadata["approval_status"], "approved")
        self.assertTrue(metadata["learnable"])
        self.assertFalse(metadata["audit_only"])
        self.assertTrue(metadata["brave_search_used"])
        wake.assert_called_once_with("learn-1")


if __name__ == "__main__":
    unittest.main()
