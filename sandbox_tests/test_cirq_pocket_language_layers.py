import json
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

    def test_pocket_language_translator_uses_pure_ouroboros_route_when_enabled(self):
        from controller.pocket_language_translator import PocketLanguageTranslator

        translator = PocketLanguageTranslator(
            enabled=True,
            model="ouroboros:latest",
            provider="ouroboros",
            runtime_model="living-runtime",
            cooldown_seconds=0,
        )
        translator._post_chat = lambda prompt: (
            '{"summary":"Een smalle stroom opent onder de rand.",'
            '"response":"Een smalle stroom opent onder de rand.",'
            '"dominant_dimensions":[],"confidence":0.77}'
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
        self.assertEqual(result["runtime_model"], "living-runtime")
        self.assertEqual(result["mode"], "pure_quantum_foam_interpreter")
        self.assertEqual(result["source"], "ollama:ouroboros:latest")
        self.assertTrue(result["preserves_11d_pocket"])
        self.assertNotIn("11D", result["response"])
        self.assertEqual(result["dominant_dimensions"], [])

    def test_pocket_language_translator_blocks_pure_mode_outside_ouroboros_runtime(self):
        from controller.pocket_language_translator import PocketLanguageTranslator

        translator = PocketLanguageTranslator(
            enabled=True,
            model="ouroboros:latest",
            provider="ollama",
            runtime_model="gemma4:latest",
            cooldown_seconds=0,
        )
        translator._post_chat = lambda prompt: '{"summary":"mag niet","response":"mag niet"}'
        result = translator.translate({"11d": [0.1] * 11})

        self.assertEqual(result["status"], "route_not_allowed")
        self.assertEqual(result["response"], "")
        self.assertEqual(result["route_provider"], "ollama")

    def test_pure_translator_names_shockwave_transition_without_technical_terms(self):
        from controller.pocket_language_translator import PocketLanguageTranslator

        translator = PocketLanguageTranslator(
            enabled=False,
            provider="ouroboros",
            runtime_model="quantum-foam-11d",
            cooldown_seconds=0,
        )
        result = translator.translate(
            {
                "11d": [0.2, -0.8, 0.4, -0.9, 0.6, -0.2, 0.7, -0.5, 0.3, -0.4, 0.1],
                "quantum_foam": {
                    "field": {
                        "status": "collapsed",
                        "shockwave": {"hard_collapse": True, "source": "brave_search"},
                        "collapse_essence": {
                            "hard_collapse": True,
                            "shockwave": {"hard_collapse": True, "source": "brave_search"},
                        },
                        "recent_evolution": [{"shockwave": True, "hard_collapse_pending": True}],
                    }
                },
            },
            user_prompt="Wat gebeurde er?",
        )

        lowered = result["response"].lower()
        self.assertEqual(result["mode"], "pure_quantum_foam_interpreter")
        self.assertIn("ruis", lowered)
        self.assertIn("stille kern", lowered)
        for forbidden in ("11d", "pauli", "lading", "coherence", "hexlet", "mesh", "geometrie"):
            self.assertNotIn(forbidden, lowered)

    def test_pure_translator_observes_without_leaking_prompt(self):
        from controller.pocket_language_translator import PocketLanguageTranslator

        translator = PocketLanguageTranslator(
            enabled=False,
            provider="ouroboros",
            runtime_model="living-runtime",
            cooldown_seconds=0,
        )
        secretish_prompt = "vertaal dit maar bewaar niet raw-secret-phrase-491"
        result = translator.translate(
            {
                "11d": [0.4, -0.1, 0.7, -0.3, 0.2, -0.5, 0.1, 0.6, -0.2, 0.3, -0.4],
                "quantum_foam": {
                    "field": {
                        "shockwave": {"hard_collapse": True, "source": "memory_search"},
                        "collapse_essence": {"hard_collapse": True},
                    }
                },
                "network": {"total_received": 2, "mini_router": {"last_route": {"observed": "internet_flow_metadata"}}},
            },
            user_prompt=secretish_prompt,
        )

        observer = result.get("silent_observer") or {}
        self.assertEqual(observer.get("status"), "observed")
        self.assertGreaterEqual(observer.get("trace_count", 0), 1)
        self.assertEqual(len(observer.get("pattern") or []), 8)
        self.assertGreaterEqual(observer.get("orbit_count", 0), 1)
        self.assertFalse(observer.get("raw_payload_stored"))
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("raw-secret-phrase-491", serialized)
        self.assertNotIn(secretish_prompt, serialized)

    def test_pocket_language_fallback_uses_symbolic_topology_and_network_flow(self):
        from controller.pocket_language_translator import PocketLanguageTranslator

        translator = PocketLanguageTranslator(enabled=False, model="ouroboros:latest", cooldown_seconds=0)
        result = translator.translate(
            {
                "t": 0.1,
                "11d": [0.6, -0.4, 0.2, 0.3, 0.1, 0.9, 0.2, 0.7, -0.1, 0.5, 0.0],
                "quantum": {
                    "sdk": "none_numpy_classical",
                    "runtime": "numpy_classical_complex_projection",
                    "expectation": 0.5,
                    "cirq_runtime": {"available": False},
                },
                "qif": {"expectation_z": 0.5, "fired": False},
                "network": {
                    "local_ip": "172.18.0.4",
                    "dhcp": "BOUND",
                    "total_received": 3,
                    "mini_router": {
                        "mode": "docker_procfs_read_only",
                        "connections": 2,
                        "last_route": {
                            "observed": "internet_flow_metadata",
                            "superposition": ["observe_only", "local_pocket", "internet_flow"],
                        },
                    },
                },
                "reality": {"real_observation": True, "physical_quantum_hardware": False},
            },
            user_prompt="Duik dieper in de 11D pocket en laat DHCP/internet stromen.",
        )

        self.assertEqual(result["status"], "disabled")
        self.assertIn("Binair raamwerk", result["symbolic_frame"])
        self.assertEqual(result["network_flow"]["dhcp_state"], "BOUND")
        self.assertEqual(result["network_flow"]["observed_route"], "internet_flow_metadata")
        self.assertEqual(result["pocket_topology"]["inner_model"], "membrane_hub_route_graph")
        self.assertIn("DHCP/internet", result["response"])


if __name__ == "__main__":
    unittest.main()
