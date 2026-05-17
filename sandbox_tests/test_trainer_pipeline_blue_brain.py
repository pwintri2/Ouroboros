import importlib.util
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

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


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
@unittest.skipUnless(ML_DEPS_AVAILABLE, "Blue Brain ML dependencies are not installed")
class TestTrainerPipelineBlueBrain(unittest.TestCase):
    def test_blue_brain_job_can_be_created_and_started_from_trainer_api(self):
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="trainer-blue-brain-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                status = client.get("/trainer/status")
                self.assertEqual(status.status_code, 200)
                self.assertIn("blue_brain", status.json())

                created = client.post(
                    "/trainer/jobs",
                    json={
                        "base_model": "blue-brain-random-forest",
                        "method": "blue_brain",
                        "epochs": 1,
                        "blue_samples": 500,
                        "blue_estimators": 25,
                        "blue_max_depth": 6,
                    },
                )
                self.assertEqual(created.status_code, 200)
                job_id = created.json()["job_id"]

                started = client.post(
                    "/trainer/training/start",
                    json={"job_id": job_id, "approval": "Akkoord", "background": False},
                )
                self.assertEqual(started.status_code, 200)
                data = started.json()
                self.assertEqual(data["status"], "success")
                self.assertIn("model_path", data)

                fetched = client.get(f"/trainer/jobs/{job_id}")
                self.assertEqual(fetched.json()["state"], "online")
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestTrainerPipelineAsyncStart(unittest.TestCase):
    def test_start_job_returns_queued_before_background_training_finishes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from controller.api import trainer_pipeline_routes as routes

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="trainer-async-start-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                routes._TRAINING_JOBS_IN_FLIGHT.clear()
                app = FastAPI()
                routes.init_trainer_pipeline(app)
                client = TestClient(app)

                created = client.post(
                    "/trainer/jobs",
                    json={
                        "base_model": "blue-brain-random-forest",
                        "method": "blue_brain",
                        "epochs": 1,
                        "blue_samples": 500,
                        "blue_estimators": 25,
                    },
                )
                self.assertEqual(created.status_code, 200)
                job_id = created.json()["job_id"]

                def release_only(job_id, *_args):
                    routes._release_training_job(job_id)

                with patch.object(routes, "_run_training_background", side_effect=release_only):
                    started = client.post(
                        "/trainer/training/start",
                        json={"job_id": job_id, "approval": "Akkoord"},
                    )

                self.assertEqual(started.status_code, 200)
                data = started.json()
                self.assertEqual(data["status"], "queued")
                self.assertEqual(data["state"], "training")
                fetched = client.get(f"/trainer/jobs/{job_id}")
                self.assertEqual(fetched.json()["state"], "training")
        finally:
            routes._TRAINING_JOBS_IN_FLIGHT.clear()
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
