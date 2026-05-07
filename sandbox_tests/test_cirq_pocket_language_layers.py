import os
import sys
import importlib.util
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

NUMPY_AVAILABLE = importlib.util.find_spec("numpy") is not None


class TestCirqPocketLanguageLayers(unittest.TestCase):
    @unittest.skipUnless(NUMPY_AVAILABLE, "numpy is not installed")
    def test_cirq_adapter_reports_boundary_and_preserves_11d_shape(self):
        import numpy as np

        from controller.cirq_quantum_adapter import CirqQuantumAdapter

        previous = os.environ.get("WINTRIP_CIRQ_QUANTUM")
        os.environ["WINTRIP_CIRQ_QUANTUM"] = "1"
        try:
            adapter = CirqQuantumAdapter(enabled=True, repetitions=8, noise_probability=0.0)
            status = adapter.status()
            self.assertFalse(status["physical_quantum_hardware"])
            self.assertTrue(status["preserves_11d_pocket"])

            vector = np.linspace(-0.5, 0.5, 11, dtype=np.float32)
            projected, observation = adapter.project_11d(vector)
            self.assertEqual(projected.shape, (11,))
            self.assertFalse(observation["physical_quantum_hardware"])
            self.assertTrue(observation["preserves_11d_pocket"])
            if observation["available"]:
                self.assertEqual(observation["sdk"], "cirq")
                self.assertEqual(observation["runtime"], "cirq_density_matrix_local")
                self.assertIn("histogram", observation)
            else:
                self.assertEqual(observation["sdk"], "none")
                self.assertIn("reason", observation)
        finally:
            if previous is None:
                os.environ.pop("WINTRIP_CIRQ_QUANTUM", None)
            else:
                os.environ["WINTRIP_CIRQ_QUANTUM"] = previous

    def test_pocket_language_translator_uses_ouroboros_model_when_enabled(self):
        from controller.pocket_language_translator import PocketLanguageTranslator

        translator = PocketLanguageTranslator(enabled=True, model="ouroboros:latest", cooldown_seconds=0)
        translator._post_chat = lambda prompt: (
            '{"summary":"Pocket vertaald.","response":"Ik geef taal aan dit 11D signaal.",'
            '"dominant_dimensions":["network=0.8"],"confidence":0.77}'
        )
        result = translator.translate(
            {
                "t": 0.05,
                "11d": [0.1, -0.2, 0.0, 0.3, 0.1, 0.8, 0.2, 0.1, -0.1, 0.4, 0.0],
                "quantum": {"sdk": "cirq", "runtime": "cirq_density_matrix_local", "expectation": 0.25},
                "qif": {"expectation_z": 0.25, "fired": False},
                "network": {"dhcp": "BOUND", "total_received": 1, "mini_router": {"mode": "docker_procfs_read_only"}},
                "reality": {"real_observation": True, "physical_quantum_hardware": False},
            }
        )

        self.assertEqual(result["status"], "translated")
        self.assertEqual(result["model"], "ouroboros:latest")
        self.assertEqual(result["source"], "ollama:ouroboros:latest")
        self.assertTrue(result["preserves_11d_pocket"])
        self.assertIn("11D", result["response"])


if __name__ == "__main__":
    unittest.main()
