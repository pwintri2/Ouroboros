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


NUMPY_AVAILABLE = importlib.util.find_spec("numpy") is not None


@unittest.skipUnless(NUMPY_AVAILABLE, "numpy is not installed")
class TestStreamingConsciousnessAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="streaming-consciousness-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_tick_status_and_dataset_export(self):
        from controller.streaming_consciousness_adapter import (
            export_streaming_dataset,
            get_streaming_status,
            run_streaming_tick,
            start_streaming_consciousness,
            streaming_state_path,
            stop_streaming_consciousness,
        )

        blocked = start_streaming_consciousness("", {"run_immediately": True})
        self.assertEqual(blocked["status"], "blocked")

        started = start_streaming_consciousness(
            "Akkoord",
            {"n_samples": 200, "steps_per_tick": 5, "interval_seconds": 0.05, "run_immediately": True, "reset": True},
        )
        self.assertEqual(started["status"], "running")
        self.assertTrue(Path(streaming_state_path()).exists())

        tick = run_streaming_tick(force=True, steps=7)
        self.assertEqual(tick["status"], "success")
        self.assertEqual(tick["steps"], 7)
        self.assertIn("11d", tick["last_event"])
        self.assertEqual(len(tick["last_event"]["11d"]), 11)

        status = get_streaming_status()
        self.assertGreaterEqual(status["step_count"], 12)
        self.assertEqual(status["fake_success"], False)

        exported = export_streaming_dataset("Akkoord", n_samples=12)
        self.assertEqual(exported["status"], "success")
        self.assertEqual(exported["feature_count"], 17)
        self.assertTrue(Path(exported["dataset_path"]).exists())

        stopped = stop_streaming_consciousness("Akkoord")
        self.assertEqual(stopped["status"], "stopped")


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
@unittest.skipUnless(NUMPY_AVAILABLE, "numpy is not installed")
class TestStreamingConsciousnessRoutes(unittest.TestCase):
    def test_routes_are_registered_and_approval_gated(self):
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="streaming-consciousness-routes-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                status = client.get("/trainer/streaming-consciousness/status")
                self.assertEqual(status.status_code, 200)
                self.assertIn("feature_count", status.json())

                blocked = client.post("/trainer/streaming-consciousness/start", json={"approval": "nee"})
                self.assertEqual(blocked.status_code, 403)

                started = client.post(
                    "/trainer/streaming-consciousness/start",
                    json={"approval": "Akkoord", "steps_per_tick": 4, "interval_seconds": 0.05, "run_immediately": True},
                )
                self.assertEqual(started.status_code, 200)
                self.assertEqual(started.json()["status"], "running")

                tick = client.post("/trainer/streaming-consciousness/tick", json={"approval": "Akkoord", "steps": 3})
                self.assertEqual(tick.status_code, 200)
                self.assertEqual(tick.json()["status"], "success")

                export = client.post("/trainer/streaming-consciousness/export-dataset", json={"approval": "Akkoord", "n_samples": 5})
                self.assertEqual(export.status_code, 200)
                self.assertEqual(export.json()["feature_count"], 17)
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
