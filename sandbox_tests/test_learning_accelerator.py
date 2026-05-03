import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLearningAccelerator(unittest.TestCase):
    def test_accelerate_learning_requires_approval(self):
        from controller.learning_accelerator import accelerate_learning

        result = accelerate_learning(approval="nee")

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["fake_success"])

    def test_accelerate_learning_runs_knowledge_then_continuous_dataset_tick(self):
        from controller.learning_accelerator import accelerate_learning

        with (
            patch("controller.learning_accelerator.count_approved_records", side_effect=[2, 5, 5]),
            patch("controller.learning_accelerator.index_knowledge_list", return_value={"status": "success"}),
            patch(
                "controller.learning_accelerator.run_knowledge_tick",
                return_value={"status": "success", "created_count": 3, "state": {"total_records": 3}},
            ) as knowledge_tick,
            patch(
                "controller.learning_accelerator.run_continuous_tick",
                return_value={
                    "status": "success",
                    "dataset": {"included_count": 5},
                    "jobs": [{"method": "litgpt"}],
                },
            ) as continuous_tick,
        ):
            result = accelerate_learning(
                approval="Akkoord",
                knowledge_mode="gemma",
                knowledge_topics=4,
                model="gemma4:latest",
                continuous_methods=["litgpt"],
                execute_training=False,
                max_records=250,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["knowledge_passes_completed"], 1)
        self.assertEqual(result["added_approved_records"], 3)
        knowledge_tick.assert_called_once_with(
            approval="Akkoord",
            mode="gemma",
            max_topics=4,
            start_index=None,
            model="gemma4:latest",
        )
        continuous_tick.assert_called_once_with(
            approval="",
            force=True,
            execute_training=False,
            methods=["litgpt"],
            max_records=250,
        )

    def test_accelerate_learning_runs_batches_until_no_progress(self):
        from controller.learning_accelerator import accelerate_learning

        with (
            patch("controller.learning_accelerator.count_approved_records", side_effect=[10, 14, 14]),
            patch("controller.learning_accelerator.index_knowledge_list", return_value={"status": "success"}),
            patch(
                "controller.learning_accelerator.run_knowledge_tick",
                side_effect=[
                    {"status": "success", "created_count": 2, "error_count": 0},
                    {"status": "success", "created_count": 2, "error_count": 0},
                    {"status": "noop", "created_count": 0, "error_count": 0},
                ],
            ) as knowledge_tick,
            patch(
                "controller.learning_accelerator.run_continuous_tick",
                return_value={"status": "success", "dataset": {"included_count": 14}},
            ) as continuous_tick,
        ):
            result = accelerate_learning(
                approval="Akkoord",
                knowledge_mode="gemma",
                knowledge_topics=2,
                knowledge_passes=5,
                continuous_methods=["litgpt"],
                execute_training=False,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["knowledge_passes_requested"], 5)
        self.assertEqual(result["knowledge_passes_completed"], 3)
        self.assertEqual(result["knowledge_created_count"], 4)
        self.assertEqual(result["knowledge_error_count"], 0)
        self.assertEqual(knowledge_tick.call_count, 3)
        self.assertEqual(
            [step["name"] for step in result["steps"][1:4]],
            ["knowledge_tick_1", "knowledge_tick_2", "knowledge_tick_3"],
        )
        continuous_tick.assert_called_once()


class TestContinuousTrainerAcceleratorSupport(unittest.TestCase):
    def test_continuous_tick_accepts_max_records_override(self):
        from controller import trainer_continuous

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="continuous-max-records-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                state = trainer_continuous._default_state()
                state["enabled"] = True
                trainer_continuous.save_continuous_state(state)

                with (
                    patch.object(trainer_continuous, "count_approved_records", return_value=3),
                    patch.object(
                        trainer_continuous,
                        "build_dataset",
                        return_value={"status": "success", "included_count": 3, "output_path": "dataset.jsonl"},
                    ) as build_dataset,
                    patch.object(
                        trainer_continuous,
                        "_create_or_run_job",
                        return_value={"job_id": "job-1", "method": "litgpt", "state": "dataset_ready"},
                    ),
                ):
                    result = trainer_continuous.run_continuous_tick(
                        force=True,
                        methods=["litgpt"],
                        execute_training=False,
                        max_records=7,
                    )

                self.assertEqual(result["status"], "success")
                self.assertEqual(build_dataset.call_args.kwargs["max_records"], 7)
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
