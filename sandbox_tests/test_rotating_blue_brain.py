import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    FastAPI = None
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""


ML_DEPS_AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("numpy", "sklearn", "joblib"))


@unittest.skipUnless(ML_DEPS_AVAILABLE, "Rotating Blue Brain ML dependencies are not installed")
class TestRotatingBlueBrain(unittest.TestCase):
    def test_rotation_matrix_is_orthogonal_and_preserves_shape(self):
        import numpy as np

        from controller.blue_brain_adapter import generate_dataset
        from controller.rotating_blue_brain import advance_rotation_clock, apply_rotation, generate_rotation_matrix

        X, _ = generate_dataset(n_samples=120, n_features=11, random_state=11)
        rotation = generate_rotation_matrix(dim=11, random_state=11)
        self.assertEqual(rotation.shape, (11, 11))
        self.assertTrue(np.allclose(rotation.T @ rotation, np.eye(11), atol=1e-8))
        self.assertAlmostEqual(float(np.linalg.det(rotation)), 1.0, places=6)

        rotated = apply_rotation(X, rotation)
        self.assertEqual(rotated.shape, X.shape)

        clock_rotation = advance_rotation_clock(None, start_index=0, rotation_count=128, dim=11)
        self.assertEqual(clock_rotation.shape, (11, 11))
        self.assertTrue(np.allclose(clock_rotation.T @ clock_rotation, np.eye(11), atol=1e-8))

    def test_training_returns_metrics_and_artifact_tick(self):
        from controller.blue_brain_adapter import generate_dataset
        from controller.rotating_blue_brain import (
            apply_rotation,
            generate_rotation_matrix,
            load_rotating_state,
            run_clock_rotation_burst,
            run_rotation_tick,
            save_rotating_state,
            train_rotated_model,
        )

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="rotating-blue-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp

                X, y = generate_dataset(n_samples=320, n_features=11, random_state=17)
                rotation = generate_rotation_matrix(dim=11, random_state=18)
                model, metrics = train_rotated_model(
                    apply_rotation(X, rotation),
                    y,
                    {"n_estimators": 25, "max_depth": 6, "random_state": 17},
                    rotation_index=1,
                )
                self.assertIsNotNone(model)
                self.assertGreater(metrics["accuracy"], 0.75)
                self.assertIn("macro_f1", metrics)

                state = load_rotating_state()
                state["n_samples"] = 320
                state["hyperparams"] = {"n_estimators": 25, "max_depth": 6, "random_state": 19, "test_size": 0.2}
                save_rotating_state(state)
                burst = run_clock_rotation_burst(force=True)
                self.assertEqual(burst["status"], "success")
                self.assertGreaterEqual(burst["rotation_count"], 1)

                result = run_rotation_tick(force=True)
                self.assertEqual(result["status"], "success")
                self.assertTrue(Path(result["state"]["best_model_path"]).exists())
                self.assertGreaterEqual(result["state"]["rotation_count"], 1)
                self.assertTrue(result["state"]["last_projection"])
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace

    def test_observer_adjusts_hyperparameters_after_low_scores(self):
        from controller.rotating_blue_brain import TrainingObserver

        observer = TrainingObserver(target_accuracy=0.95, target_f1=0.95, low_window=3)
        hyperparams = {"n_estimators": 25, "max_depth": 8, "random_state": 1, "test_size": 0.2}
        for index in range(1, 4):
            result = observer.evaluate(
                {"rotation_index": index, "accuracy": 0.5, "macro_f1": 0.45, "train_accuracy": 0.72},
                hyperparams,
            )
            hyperparams = result["hyperparams"]

        self.assertGreater(hyperparams["n_estimators"], 25)
        self.assertLess(hyperparams["max_depth"], 8)


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
@unittest.skipUnless(ML_DEPS_AVAILABLE, "Rotating Blue Brain ML dependencies are not installed")
class TestRotatingBlueBrainRoutes(unittest.TestCase):
    def test_rotating_blue_routes_require_approval_and_tick(self):
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline
        from controller.rotating_blue_brain import load_rotating_state, save_rotating_state, stop_rotating_training

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="rotating-blue-routes-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                state = load_rotating_state()
                state["n_samples"] = 300
                state["hyperparams"] = {"n_estimators": 20, "max_depth": 5, "random_state": 23, "test_size": 0.2}
                save_rotating_state(state)

                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                status = client.get("/trainer/rotating-blue/status")
                self.assertEqual(status.status_code, 200)
                self.assertIn("features", status.json())

                blocked = client.post("/trainer/rotating-blue/start", json={"approval": "nee"})
                self.assertEqual(blocked.status_code, 403)

                tick = client.post("/trainer/rotating-blue/tick", json={"approval": "Akkoord", "force": True})
                self.assertEqual(tick.status_code, 200)
                self.assertEqual(tick.json()["status"], "success")
                stop_rotating_training("Akkoord")
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
