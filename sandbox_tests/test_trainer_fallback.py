import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrainerFallback(unittest.TestCase):
    def test_fallback_status_preserves_trainer_dashboard_contract(self):
        from controller import trainer_fallback

        def default_status(_module_name, _function_name, default):
            return dict(default)

        with (
            patch.object(trainer_fallback, "_safe_status", side_effect=default_status),
            patch.object(trainer_fallback, "_safe_count", return_value=0),
        ):
            status = trainer_fallback.trainer_fallback_status("import boom")

        expected_keys = {
            "pipeline",
            "litgpt",
            "unsloth",
            "blue_brain",
            "rotating_blue",
            "streaming_consciousness",
            "codex_registry",
            "codex_agent",
            "codeneuron",
            "ecosystem",
            "popos_diagnostics",
            "google_workspace",
            "rclone_drive",
            "microsoft_graph",
            "sharepoint",
            "agentic_crawler",
            "program_inventory",
            "host_sensory",
            "ecosystem_knowledge",
            "curriculum",
            "knowledge_acquisition",
            "local_machine",
            "independence",
            "continuous",
            "artifacts",
            "approved_dataset_records",
        }
        self.assertEqual(status["status"], "degraded")
        self.assertFalse(status["routes_available"])
        self.assertFalse(status["fake_success"])
        self.assertTrue(expected_keys.issubset(status.keys()))
        self.assertEqual(status["pipeline"]["total_jobs"], 0)
        self.assertEqual(status["continuous"]["new_records_available"], 0)
        self.assertEqual(status["artifacts"]["total_artifacts"], 0)
        self.assertEqual(status["independence"]["independence_score"], 0.0)

    def test_fallback_jobs_returns_empty_list_when_storage_is_unavailable(self):
        from controller import trainer_fallback

        with patch.object(trainer_fallback, "import_module", side_effect=RuntimeError("missing")):
            jobs = trainer_fallback.trainer_fallback_jobs("import boom")

        self.assertEqual(jobs["status"], "degraded")
        self.assertFalse(jobs["routes_available"])
        self.assertEqual(jobs["jobs"], [])
        self.assertEqual(jobs["count"], 0)
        self.assertFalse(jobs["fake_success"])


if __name__ == "__main__":
    unittest.main()
