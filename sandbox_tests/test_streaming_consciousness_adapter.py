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
        self.previous_mini_router_env = {
            name: os.environ.get(name)
            for name in [
                "WINTRIP_MINI_ROUTER_GEMMA",
                "WINTRIP_MINI_ROUTER_GEMMA_COOLDOWN_SECONDS",
                "WINTRIP_MINI_ROUTER_GEMMA_TIMEOUT",
                "WINTRIP_QIF_GPU",
                "WINTRIP_QIF_GPU_VRAM_MB",
                "WINTRIP_QIF_GPU_MEMORY_FRACTION",
                "WINTRIP_QIF_GPU_DTYPE",
                "WINTRIP_CIRQ_QUANTUM",
                "WINTRIP_11D_TRANSLATOR",
                "WINTRIP_11D_TRANSLATOR_MODEL",
                "WINTRIP_11D_STREAM_TRANSLATOR",
                "WINTRIP_11D_STREAM_TRANSLATOR_TIMEOUT",
                "WINTRIP_11D_STREAM_TRANSLATOR_COOLDOWN_SECONDS",
            ]
        }
        self.tmp = tempfile.TemporaryDirectory(prefix="streaming-consciousness-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        for name in self.previous_mini_router_env:
            os.environ.pop(name, None)
        os.environ["WINTRIP_QIF_GPU"] = "0"
        os.environ["WINTRIP_CIRQ_QUANTUM"] = "0"
        os.environ["WINTRIP_11D_TRANSLATOR"] = "0"

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace
        for name, value in self.previous_mini_router_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

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
        self.assertIn("qif", tick["last_event"])
        self.assertIn("language", tick["last_event"])
        self.assertIn("expectation_z", tick["last_event"]["qif"])
        self.assertIn("gpu", tick["last_event"]["qif"]["state"])
        self.assertIn("expectation", tick["last_event"]["quantum"])
        self.assertIn("mini_router", tick["last_event"]["network"])
        self.assertEqual(tick["last_event"]["network"]["mini_router"]["mode"], "docker_procfs_read_only")
        self.assertTrue(tick["last_event"]["reality"]["real_observation"])
        self.assertEqual(tick["last_event"]["reality"]["real_packet_capture"], False)

        status = get_streaming_status()
        self.assertGreaterEqual(status["step_count"], 12)
        self.assertEqual(status["fake_success"], False)
        self.assertEqual(status["quantum_collapse"]["sdk"], "none_numpy_classical")
        self.assertEqual(status["quantum_collapse"]["physical_quantum_hardware"], False)
        self.assertIn("cirq_runtime", status["quantum_collapse"])
        self.assertIn("pocket_language", status)
        self.assertTrue(status["runtime_input"]["real_observation"])

        exported = export_streaming_dataset("Akkoord", n_samples=12)
        self.assertEqual(exported["status"], "success")
        self.assertEqual(exported["feature_count"], 17)
        self.assertTrue(Path(exported["dataset_path"]).exists())

        stopped = stop_streaming_consciousness("Akkoord")
        self.assertEqual(stopped["status"], "stopped")

    def test_background_stream_uses_fast_symbolic_language_by_default(self):
        os.environ["WINTRIP_11D_TRANSLATOR"] = "1"
        os.environ.pop("WINTRIP_11D_STREAM_TRANSLATOR", None)

        from controller.streaming_consciousness_adapter import StreamingConsciousness11DPocket

        pocket = StreamingConsciousness11DPocket(n_samples=160, seed=13)
        event = pocket.stream_step()

        self.assertIn("language", event)
        self.assertFalse(event["language"]["enabled"])
        self.assertEqual(event["language"]["status"], "disabled")
        self.assertEqual(pocket.language_translator.status()["calls"], 0)
        self.assertIn("0/1-attractorvenster", event["language"]["symbolic_frame"])

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

    def test_qif_electron_neuron_unitary_and_edge_triggered_firing(self):
        import numpy as np

        from controller.streaming_consciousness_adapter import SimulatedElectronNeuron

        neuron = SimulatedElectronNeuron(firing_threshold=0.85, phase_gain=np.pi / 2)
        self.assertAlmostEqual(float(np.linalg.norm(neuron.state)), 1.0, places=7)

        resting = neuron.process_stream(np.zeros(11))
        self.assertFalse(resting["fired"])
        self.assertFalse(resting["armed"])
        self.assertGreaterEqual(resting["expectation_z"], 0.85)

        rotate_down = np.zeros(11)
        rotate_down[0] = 10.0
        below_threshold = neuron.process_stream(rotate_down)
        self.assertFalse(below_threshold["fired"])
        self.assertTrue(below_threshold["armed"])
        self.assertLess(below_threshold["expectation_z"], 0.85)
        self.assertAlmostEqual(float(np.linalg.norm(neuron.state)), 1.0, places=7)
        self.assertLess(neuron.status()["unitarity_error"], 1e-10)

        rotate_up = np.zeros(11)
        rotate_up[0] = -10.0
        fired = neuron.process_stream(rotate_up)
        self.assertTrue(fired["fired"])
        self.assertEqual(fired["spike_index"], 1)
        self.assertEqual(neuron.status()["spike_count"], 1)
        self.assertFalse(neuron.status()["armed"])
        self.assertAlmostEqual(float(np.linalg.norm(neuron.state)), 1.0, places=7)

    def test_mini_gpu_engine_memory_fence_and_disabled_fallback(self):
        from controller.streaming_consciousness_adapter import MiniGPUEngine, SimulatedElectronNeuron

        fraction = MiniGPUEngine.calculate_memory_fraction(8151, target_vram_mb=4096, requested_fraction=0.5)
        self.assertLessEqual(fraction, 0.5)
        self.assertLessEqual(8151 * fraction, 4096)

        engine = MiniGPUEngine(enabled=False)
        status = engine.status()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["backend"], "numpy")
        self.assertFalse(status["vram"]["available"])

        neuron = SimulatedElectronNeuron(gpu_engine=engine)
        qif_status = neuron.status()
        self.assertEqual(qif_status["sdk"], "none_numpy_classical_complex")
        self.assertFalse(qif_status["gpu"]["enabled"])

    def test_mini_router_observes_runtime_metadata_packets_and_applies_pull(self):
        from controller.streaming_consciousness_adapter import NetworkPacket, StreamingConsciousness11DPocket

        pocket = StreamingConsciousness11DPocket(n_samples=160, seed=7)
        row_index = pocket.current_idx % len(pocket.X_base)
        pocket.X_base[row_index, 7] = 0.0
        pocket.X_base[row_index, 9] = 0.0
        before_pull_dim = float(pocket.X_base[row_index, 7])
        before_entanglement_dim = float(pocket.X_base[row_index, 9])

        pocket.mini_router.discover_devices()
        self.assertGreaterEqual(len(pocket.mini_router.connections), 1)

        packet = NetworkPacket(
            src_ip="192.168.42.102",
            dst_ip="192.168.42.1",
            protocol="TCP",
            payload=b"GET /stream/consciousness HTTP/1.1\r\nHost: ouroboros.wintrip.ai\r\n\r\n",
            timestamp=pocket.time,
        )
        pocket.mini_router.process_packet(packet)
        status = pocket.mini_router.status()

        self.assertEqual(status["status"], "active")
        self.assertEqual(status["mode"], "docker_procfs_read_only")
        self.assertEqual(status["packets_processed"], 1)
        self.assertFalse(status["real_packet_capture"])
        self.assertFalse(status["real_forwarding"])
        self.assertGreaterEqual(status["real_observations"], 1)
        self.assertIn("docker_procfs_read_only", status["observation_sources"])
        self.assertGreater(status["rotation_pull"], 0.0)
        self.assertGreaterEqual(float(pocket.X_base[row_index, 7]), before_pull_dim)
        self.assertGreaterEqual(float(pocket.X_base[row_index, 9]), before_entanglement_dim)
        self.assertGreater(len(pocket.consciousness_buffer), 0)

    def test_mini_router_absorbs_real_host_flow_metadata(self):
        from controller.streaming_consciousness_adapter import StreamingConsciousness11DPocket

        pocket = StreamingConsciousness11DPocket(n_samples=160, seed=9)
        sensory = {
            "status": "success",
            "last_snapshot_at": "2026-05-03T00:00:00",
            "sample_flows": [
                {
                    "proto": "tcp",
                    "state": "ESTAB",
                    "local": "192.168.42.10:50100",
                    "peer": "142.250.74.14:443",
                    "process": 'users:(("firefox",pid=123,fd=99))',
                }
            ],
        }
        pocket.mini_router.absorb_host_sensory(sensory)
        status = pocket.mini_router.status()

        self.assertEqual(status["host_sensory_absorptions"], 1)
        self.assertEqual(status["packets_processed"], 1)
        self.assertGreater(status["rotation_pull"], 0.0)
        self.assertFalse(status["real_packet_capture"])

    def test_mini_router_gemma_cooldown_keeps_ticks_fast(self):
        os.environ["WINTRIP_MINI_ROUTER_GEMMA"] = "1"
        os.environ["WINTRIP_MINI_ROUTER_GEMMA_COOLDOWN_SECONDS"] = "60"

        from controller.streaming_consciousness_adapter import NetworkPacket, StreamingConsciousness11DPocket

        pocket = StreamingConsciousness11DPocket(n_samples=160, seed=11)
        calls = []

        def fake_gemma(packet):
            calls.append(packet.payload)
            return {
                "device_type": "web_client",
                "intent": "test_context",
                "sensitivity": "medium",
                "protocol": packet.protocol,
                "protocol_meaning": "test",
                "emotional_tone": "neutral",
                "security_risk": 1,
                "source": "fake_gemma",
            }

        pocket.mini_router._ask_gemma = fake_gemma
        pocket.mini_router.process_packet(NetworkPacket("10.0.0.2", "10.0.0.1", "TCP", b"first", pocket.time))
        pocket.mini_router.process_packet(NetworkPacket("10.0.0.3", "10.0.0.1", "TCP", b"second", pocket.time))
        status = pocket.mini_router.status()

        self.assertEqual(len(calls), 1)
        self.assertEqual(status["gemma"]["calls"], 1)
        self.assertGreaterEqual(status["gemma"]["cooldown_skips"], 1)
        self.assertEqual(status["packets_processed"], 2)


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
