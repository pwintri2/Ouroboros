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
        self.assertIn("quantum", tick["last_event"])
        self.assertIn("expectation", tick["last_event"]["quantum"])

        status = get_streaming_status()
        self.assertGreaterEqual(status["step_count"], 12)
        self.assertEqual(status["fake_success"], False)
        self.assertEqual(status["quantum_collapse"]["sdk"], "none_numpy_classical")

        exported = export_streaming_dataset("Akkoord", n_samples=12)
        self.assertEqual(exported["status"], "success")
        self.assertEqual(exported["feature_count"], 17)
        self.assertTrue(Path(exported["dataset_path"]).exists())

        stopped = stop_streaming_consciousness("Akkoord")
        self.assertEqual(stopped["status"], "stopped")

    def test_quantum_collapse_math_helpers(self):
        import numpy as np

        from controller.streaming_consciousness_adapter import StreamingConsciousnessAdapter

        adapter = StreamingConsciousnessAdapter()
        self.assertEqual(adapter.sigma_z.dtype, np.dtype(complex))
        self.assertEqual(adapter.sigma_x.dtype, np.dtype(complex))

        tensor = adapter.calculate_tensor_product(adapter.sigma_x, adapter.sigma_z)
        self.assertEqual(tensor.shape, (4, 4))

        expectation = adapter.calculate_born_expectation(np.array([1, 0], dtype=complex), adapter.sigma_z)
        self.assertAlmostEqual(expectation, 1.0, places=7)

        vector = np.array([1.0, 1.0, 0.5, 0.25, -0.2, 0.1, 0.3, 0.4, -0.5, 0.6, 0.7])
        collapsed = adapter.trigger_quantum_collapse(vector)
        self.assertEqual(collapsed.shape, (11,))
        self.assertTrue(np.allclose(collapsed, vector, atol=1e-7))
        self.assertAlmostEqual(adapter.last_observation["expectation"], 1.0, places=7)

        with self.assertRaises(ValueError):
            adapter.trigger_quantum_collapse(np.zeros(10))


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
                self.assertEqual(status.json()["quantum_collapse"]["enabled"], True)

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
