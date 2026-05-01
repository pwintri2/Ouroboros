import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestOuroborosIndependence(unittest.TestCase):
    def test_label_thresholds_are_stable(self):
        from controller.ouroboros_independence import independence_label

        self.assertEqual(independence_label(0.1), "external_dependent")
        self.assertEqual(independence_label(0.5), "local_assisted")
        self.assertEqual(independence_label(0.7), "local_useful")
        self.assertEqual(independence_label(0.77), "self_extending_with_approval")
        self.assertEqual(independence_label(0.82), "mostly_independent")
        self.assertEqual(independence_label(0.9), "independent_candidate")

    def test_score_is_bounded_and_contains_required_fields(self):
        from controller import ouroboros_independence as independence

        fake_signal = {"score": 0.5, "gap": ""}
        with patch.object(independence, "_local_inference_signal", return_value={"score": 1.0, "models": ["local"], "gap": ""}), \
            patch.object(independence, "_tool_use_signal", return_value={"score": 0.8, "tools": ["safe_shell"], "gap": ""}), \
            patch.object(independence, "_code_ability_signal", return_value=fake_signal), \
            patch.object(independence, "_learning_loop_signal", return_value=fake_signal), \
            patch.object(independence, "_self_extension_signal", return_value=fake_signal), \
            patch.object(independence, "_validation_signal", return_value=fake_signal), \
            patch.object(independence, "_recovery_signal", return_value=fake_signal), \
            patch.object(
                independence,
                "_knowledge_coverage_signal",
                return_value={
                    "score": 0.6,
                    "coverage": {"general": 0.5, "programming": 0.7, "local_machine": 0.4},
                    "gap": "",
                },
            ):
            result = independence.compute_independence_score()

        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["independence_score"], 0.0)
        self.assertLessEqual(result["independence_score"], 1.0)
        self.assertIn("external_model_needed", result)
        self.assertEqual(result["fake_success"], False)


if __name__ == "__main__":
    unittest.main()
