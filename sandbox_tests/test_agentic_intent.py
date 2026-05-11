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

    def test_web_search_is_readonly_agentic_with_brave_hint(self):
        intent = classify_agentic_intent("Zoek online de laatste internetresultaten over NS storingen")

        self.assertEqual(intent.route, "agentic_processor")
        self.assertTrue(intent.is_agentic)
        self.assertEqual(intent.target_tool, "brave_search")
        self.assertEqual(intent.action_type, "read_only")
        self.assertTrue(intent.read_only)
        self.assertFalse(intent.approval_required)
        self.assertIn("web_search", intent.categories)
        self.assertEqual(intent.plan_hints[0]["tool"], "brave_search")

    def test_travel_classifier_prefers_ns_or_9292_deterministically(self):
        ns_intent = classify_agentic_intent("Hoe laat vertrekt de trein van Ermelo naar Utrecht Centraal volgens NS?")
        ov_intent = classify_agentic_intent("Gebruik 9292 voor een bus tram metro reisplanner van huis naar station")

        self.assertEqual(ns_intent.target_tool, "ns_travel_advice")
        self.assertIn("ns", ns_intent.services)
        self.assertEqual(ov_intent.target_tool, "ov9292_travel_advice")
        self.assertIn("9292", ov_intent.services)
        self.assertEqual(ov_intent.action_type, "read_only")
        self.assertFalse(ov_intent.approval_required)

    def test_private_connector_and_vps_intents_are_gated_preview_only(self):
        cases = [
            ("Upload dit bestand naar Google Drive", "google_drive", "private_mutating", "connector_intent_preview", "connector_preview_required"),
            ("Sync en deploy via mijn VPS login", "vps", "private_mutating", "vps_sync_preview", "vps_sync_preview_first"),
            ("Maak een GitHub issue in mijn private repo", "github", "private_mutating", "connector_intent_preview", "connector_preview_required"),
        ]
        for prompt, service, action_type, target_tool, routing_hint in cases:
            with self.subTest(prompt=prompt):
                intent = classify_agentic_intent(prompt)
                self.assertEqual(intent.route, "agentic_processor")
                self.assertEqual(intent.target_tool, target_tool)
                self.assertIn(service, intent.services)
                self.assertEqual(intent.action_type, action_type)
                self.assertTrue(intent.private)
                self.assertTrue(intent.approval_required)
                self.assertEqual(intent.routing_hint, routing_hint)

    def test_connector_reads_route_to_first_class_tools_with_gating_metadata(self):
        gmail = classify_agentic_intent("Lees mijn Gmail inbox")
        drive = classify_agentic_intent("Lijst mijn Google Drive bestanden")
        github = classify_agentic_intent("Zoek publieke GitHub repos over Ouroboros")
        github_repo = classify_agentic_intent("Toon GitHub repo octocat/Hello-World")
        status = classify_agentic_intent("Wat is de GitHub status?")

        self.assertEqual(gmail.target_tool, "gmail_search")
        self.assertTrue(gmail.approval_required)
        self.assertEqual(gmail.action_type, "private_read")
        self.assertEqual(drive.target_tool, "google_drive_list")
        self.assertTrue(drive.approval_required)
        self.assertEqual(github.target_tool, "github_search_repositories")
        self.assertFalse(github.approval_required)
        self.assertEqual(github.action_type, "read_only")
        self.assertEqual(github_repo.target_tool, "github_repo")
        self.assertEqual(status.target_tool, "github_status")
        self.assertFalse(status.approval_required)

    def test_agent_selection_routes_to_local_agentic_ecosystem_context(self):
        intent = classify_agentic_intent("Welke agent of tool moet dit gewone chatverzoek afhandelen?")

        self.assertEqual(intent.route, "agentic_processor")
        self.assertEqual(intent.target_tool, "agentic_ecosystem_context")
        self.assertIn("agent_selection", intent.categories)
        self.assertFalse(intent.approval_required)


if __name__ == "__main__":
    unittest.main()
