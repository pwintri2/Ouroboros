"""Loop guard threshold tests."""

import unittest

from controller import agentic_loop_guard as guard


class LoopGuardTests(unittest.TestCase):
    def setUp(self):
        guard.reset_all()

    def test_signature_ignores_irrelevant_keys(self):
        a = guard.evaluate_step("sess1", tool="brave_search", args={"query": "x", "approval": "Akkoord"})
        b = guard.evaluate_step("sess1", tool="brave_search", args={"query": "x"})
        self.assertEqual(a["signature"], b["signature"])
        self.assertEqual(b["count"], 2)

    def test_soft_threshold_emits_warning(self):
        for index in range(2):
            guard.evaluate_step("sess2", tool="brave_search", args={"query": "loop"})
        third = guard.evaluate_step("sess2", tool="brave_search", args={"query": "loop"})
        self.assertTrue(third["warning"])
        self.assertFalse(third["blocked"])
        self.assertEqual(third["count"], 3)

    def test_hard_threshold_blocks(self):
        for index in range(4):
            guard.evaluate_step("sess3", tool="memory_search", args={"query": "loop"})
        fifth = guard.evaluate_step("sess3", tool="memory_search", args={"query": "loop"})
        self.assertTrue(fifth["blocked"])
        self.assertEqual(fifth["count"], 5)
        self.assertTrue(fifth["reason"])

    def test_counter_resets_on_different_signature(self):
        guard.evaluate_step("sess4", tool="brave_search", args={"query": "a"})
        guard.evaluate_step("sess4", tool="brave_search", args={"query": "a"})
        switched = guard.evaluate_step("sess4", tool="brave_search", args={"query": "b"})
        self.assertEqual(switched["count"], 1)
        self.assertFalse(switched["warning"])
        self.assertFalse(switched["blocked"])

    def test_session_isolation(self):
        for index in range(5):
            guard.evaluate_step("sess5", tool="memory_search", args={"query": "loop"})
        outsider = guard.evaluate_step("sess6", tool="memory_search", args={"query": "loop"})
        self.assertEqual(outsider["count"], 1)
        self.assertFalse(outsider["blocked"])
        guard.reset_session("sess5")
        recovered = guard.evaluate_step("sess5", tool="memory_search", args={"query": "loop"})
        self.assertEqual(recovered["count"], 1)


if __name__ == "__main__":
    unittest.main()
