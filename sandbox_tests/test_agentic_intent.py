import unittest

from controller.agentic_intent import APPROVAL_PHRASE, classify_agentic_intent, should_use_agentic_processor


class TestAgenticIntent(unittest.TestCase):
    def test_normal_chat_stays_model_chat(self):
        intent = classify_agentic_intent("Leg in twee zinnen uit wat Ouroboros betekent")
        self.assertEqual(intent.route, "normal_chat")
        self.assertFalse(intent.is_agentic)

    def test_file_and_preview_prompts_route_agentic(self):
        for prompt in ["toon bestanden in controller", "is de web preview bereikbaar?", "draai tests"]:
            with self.subTest(prompt=prompt):
                intent = classify_agentic_intent(prompt)
                self.assertEqual(intent.route, "agentic_processor")
                self.assertTrue(intent.is_agentic)

    def test_slash_commands_are_aliases_not_normal_agentic_chat(self):
        intent = classify_agentic_intent("/codex repareer de runtime")
        self.assertEqual(intent.route, "slash_agent")
        self.assertTrue(intent.is_slash_alias)
        self.assertFalse(intent.is_agentic)

    def test_exact_inline_approval_is_detected(self):
        intent = classify_agentic_intent(f"{APPROVAL_PHRASE}: open https://example.com")
        self.assertTrue(intent.approval_present)
        self.assertTrue(should_use_agentic_processor(f"{APPROVAL_PHRASE} open https://example.com"))
        self.assertFalse(classify_agentic_intent("akkoord open https://example.com").approval_present)


if __name__ == "__main__":
    unittest.main()
