import os
import tempfile
import unittest
from pathlib import Path

from controller.approval_resume import (
    APPROVAL_PHRASE,
    clear_pending_approval,
    consume_pending_approval,
    extract_inline_approval,
    pending_approval_status,
    store_pending_from_result,
)


class TestApprovalResume(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._previous_path = os.environ.get("WINTRIP_PENDING_APPROVAL_PATH")
        os.environ["WINTRIP_PENDING_APPROVAL_PATH"] = str(Path(self._tmp.name) / "pending.json")

    def tearDown(self):
        clear_pending_approval("conv-test")
        if self._previous_path is None:
            os.environ.pop("WINTRIP_PENDING_APPROVAL_PATH", None)
        else:
            os.environ["WINTRIP_PENDING_APPROVAL_PATH"] = self._previous_path
        self._tmp.cleanup()

    def test_extract_inline_approval_keeps_phrase_exact(self):
        self.assertEqual(extract_inline_approval("Akkoord open ns.nl")["prompt"], "open ns.nl")
        self.assertEqual(extract_inline_approval("Akkoord")["resume_only"], True)
        self.assertEqual(extract_inline_approval("akkoord open ns.nl")["approval"], "")

    def test_store_and_consume_pending_action(self):
        result = {
            "status": "blocked",
            "approval_required": True,
            "route": "agentic_processor",
            "source_trace": {"tools_blocked": ["browser_open_url"], "approval_required": True},
        }

        pending = store_pending_from_result(
            result,
            conversation_id="conv-test",
            prompt="open ns.nl",
            provider="ollama",
            model="llama",
            requested_provider="ollama",
        )

        self.assertEqual(pending["status"], "waiting_for_approval")
        self.assertEqual(pending["approval_phrase"], APPROVAL_PHRASE)
        self.assertEqual(pending["blocked_tools"], ["browser_open_url"])
        self.assertEqual(pending_approval_status("conv-test")["status"], "waiting_for_approval")

        resumed = consume_pending_approval("conv-test")
        self.assertEqual(resumed["prompt"], "open ns.nl")
        self.assertEqual(resumed["blocked_tools"], ["browser_open_url"])
        self.assertIsNone(consume_pending_approval("conv-test"))

    def test_pending_action_survives_module_state_only_resume(self):
        result = {
            "status": "blocked",
            "approval_required": True,
            "route": "agentic_processor",
            "source_trace": {"tools_blocked": ["write_file"], "approval_required": True},
        }
        store_pending_from_result(
            result,
            conversation_id="conv-test",
            prompt="schrijf test.txt",
            provider="ollama",
            model="llama",
            requested_provider="ollama",
        )

        stored_path = Path(os.environ["WINTRIP_PENDING_APPROVAL_PATH"])
        self.assertTrue(stored_path.exists())
        self.assertIn("conv-test", stored_path.read_text(encoding="utf-8"))
        self.assertEqual(pending_approval_status("conv-test")["status"], "waiting_for_approval")


if __name__ == "__main__":
    unittest.main()
