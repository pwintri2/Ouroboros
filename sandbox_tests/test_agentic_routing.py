import unittest

from controller.orchestrator import should_use_agentic_processor


class TestAgenticRouting(unittest.TestCase):
    def test_slash_routes_remain_reserved_for_slash_router(self):
        self.assertFalse(should_use_agentic_processor("/codex status"))

    def test_plain_chat_without_action_stays_normal_chat(self):
        self.assertFalse(should_use_agentic_processor("vertel een korte grap"))

    def test_open_url_routes_to_agentic_processor_without_slash(self):
        self.assertTrue(should_use_agentic_processor("open ns.nl"))
        self.assertTrue(should_use_agentic_processor("ga naar https://example.com"))

    def test_tests_route_to_agentic_processor_without_slash(self):
        self.assertTrue(should_use_agentic_processor("draai tests"))
        self.assertTrue(should_use_agentic_processor("pytest sandbox_tests/test_agentic_processor.py"))

    def test_file_actions_route_to_agentic_processor_without_slash(self):
        self.assertTrue(should_use_agentic_processor("toon bestanden in controller"))
        self.assertTrue(should_use_agentic_processor("zoek in bestanden naar AgenticProcessor"))


if __name__ == "__main__":
    unittest.main()
