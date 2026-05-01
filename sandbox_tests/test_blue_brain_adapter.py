import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


ML_DEPS_AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("numpy", "sklearn", "joblib"))


@unittest.skipUnless(ML_DEPS_AVAILABLE, "Blue Brain ML dependencies are not installed")
class TestBlueBrainAdapter(unittest.TestCase):
    def test_module_functions_train_save_and_reload_model(self):
        from controller.blue_brain_adapter import (
            E_TYPES,
            generate_dataset,
            load_model,
            predict,
            save_model,
            train_model,
        )

        with tempfile.TemporaryDirectory(prefix="blue-brain-module-") as tmp:
            X, y = generate_dataset(n_samples=500, n_features=11, random_state=7)
            model, metrics = train_model(
                X,
                y,
                {"n_estimators": 25, "max_depth": 6, "random_state": 7, "feature_names": E_TYPES},
            )
            self.assertGreater(metrics["accuracy"], 0.85)

            model_path = Path(tmp) / "blue.joblib"
            saved = save_model(model, model_path, metadata={"n_features": 11, "accuracy": metrics["accuracy"]})
            self.assertTrue(Path(saved["path"]).exists())

            loaded = load_model(model_path)
            prediction = predict(loaded, X[:1])
            self.assertIn(int(prediction[0]), (0, 1))

    def test_job_runner_registers_real_blue_brain_artifact(self):
        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="blue-brain-job-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                from controller.blue_brain_adapter import run_blue_brain_training
                from controller.trainer_jobs import TrainerMethod, create_job, get_job

                job = create_job(
                    base_model="blue-brain-random-forest",
                    method=TrainerMethod.BLUE_BRAIN,
                    epochs=2,
                    extra_training_params={"blue_samples": 500, "blue_estimators": 25, "blue_max_depth": 6},
                )
                result = run_blue_brain_training(
                    job_id=job["job_id"],
                    n_samples=500,
                    n_estimators=25,
                    max_depth=6,
                    cycles=2,
                )

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["cycles"], 2)
                self.assertTrue(Path(result["model_path"]).exists())
                self.assertTrue(result["reload_validation"]["passed"])

                updated = get_job(job["job_id"])
                self.assertEqual(updated["state"], "online")
                self.assertTrue(updated["validation_passed"])
                self.assertIn("blue_brain_model", updated["exported_artifacts"])
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
