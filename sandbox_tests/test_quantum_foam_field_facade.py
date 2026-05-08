import unittest

from controller.quantum_foam_field import (
    QuantumElectronHexlet,
    QuantumFoamField,
    QuantumFoamNode,
    agentic_foam_event,
    foam_context_for_pocket,
    mojo_runtime_status,
    run_living_foam_cycle,
)
from ouroboros_esoteric.quantum_foam import FieldLifecycleEngine, reset_field_lifecycle_engine


class TestQuantumFoamFieldFacade(unittest.TestCase):
    def setUp(self):
        self.previous_engine = reset_field_lifecycle_engine(FieldLifecycleEngine())

    def tearDown(self):
        reset_field_lifecycle_engine(self.previous_engine)

    def test_node_resonates_evolves_and_collapses_to_essence(self):
        left = QuantumFoamNode("ReasoningNode", weight=0.5)
        right = QuantumFoamNode("MemoryNode", weight=0.6)

        resonance = left.resonate(right)
        evolved = left.evolve({"intent": "agentic shell tool"})
        essence = left.collapse()

        self.assertEqual(resonance["status"], "resonated")
        self.assertEqual(len(left.electron_state), 11)
        self.assertEqual(evolved["fundamental_unit"], "QuantumElectronHexlet")
        self.assertGreaterEqual(evolved["hexlet_count"], 1)
        self.assertGreaterEqual(left.weight, 0.0)
        self.assertLessEqual(left.weight, 1.0)
        self.assertIn("dominant_dimensions", evolved)
        self.assertEqual(essence["type"], "ReasoningNode")
        self.assertIn("essence", essence)
        self.assertGreaterEqual(essence["hexlet_count"], 1)
        self.assertEqual(left.connections, [])
        self.assertEqual(left.hexlets, [])

    def test_local_quantum_electron_hexlet_is_16_state_unit(self):
        hexlet = QuantumElectronHexlet()
        before = hexlet.to_dict()
        moved = hexlet.resonate("non-lokaal veld")
        essence = hexlet.collapse()

        self.assertEqual(before["state_count"], 16)
        self.assertEqual(moved["unit"], "QuantumElectronHexlet")
        self.assertIn(moved["hex_state"], "0123456789abcdef")
        self.assertEqual(essence["status"], "collapsed")

    def test_local_field_spawns_nonlocal_mesh_and_releases_nodes_on_collapse(self):
        field = QuantumFoamField()
        nodes = field.spawn_field("Zoek op internet en schrijf een bestand", num_nodes=8)
        active_snapshot = field.to_dict()

        self.assertTrue(field.active)
        self.assertEqual(len(nodes), 8)
        self.assertEqual(active_snapshot["fundamental_unit"], "QuantumElectronHexlet")
        self.assertGreaterEqual(active_snapshot["hexlet_count"], 8)
        self.assertEqual(active_snapshot["symbolic_capacity_zettabytes"], 89)
        self.assertIn("ToolBridge", active_snapshot["entanglement_mesh"]["components"])
        self.assertGreater(field.coherence, 0.0)
        self.assertLessEqual(field.coherence, 100.0)
        self.assertTrue(any(node.connections for node in nodes))
        self.assertTrue(any(node.type == "WorldActionNode" for node in nodes))

        essences = field.collapse_field(reason="task_done")

        self.assertEqual(len(essences), 8)
        self.assertFalse(field.active)
        self.assertEqual(field.nodes, [])
        self.assertEqual(field.coherence, 0.0)
        self.assertEqual(field.last_collapse["ram_released_estimate_nodes"], 8)
        self.assertGreaterEqual(field.last_collapse["ram_released_estimate_hexlets"], 8)
        self.assertGreater(field.last_collapse["ram_released_estimate_bytes"], 0)

    def test_agentic_event_uses_v49_runtime_and_collapses_after_task(self):
        start = agentic_foam_event("Gebruik shell tool en geheugen", phase="agentic_start")
        tool = agentic_foam_event("Gebruik shell tool en geheugen", phase="tool:memory_search", tool="memory_search", result={"status": "success"})
        collapsed = agentic_foam_event("Gebruik shell tool en geheugen", phase="agentic_success", collapse=True)

        self.assertTrue(start["active"])
        self.assertGreater(start["node_count"], 0)
        self.assertEqual(start["fundamental_unit"], "QuantumElectronHexlet")
        self.assertGreaterEqual(start["hexlet_count"], 8)
        self.assertLessEqual(start["hexlet_count"], 15)
        self.assertIn("dominant_dimensions", start)
        self.assertEqual(tool["tool"], "memory_search")
        self.assertTrue(collapsed["collapse_event"])
        self.assertGreaterEqual(collapsed["ram_released_estimate_nodes"], 0)
        self.assertGreaterEqual(collapsed["ram_released_estimate_hexlets"], 0)

        pocket = foam_context_for_pocket("Gebruik shell tool en geheugen", collapsed)
        self.assertTrue(pocket["collapse_event"])
        self.assertIn("dominant_dimensions", pocket)

    def test_run_living_foam_cycle_and_mojo_status_are_explicit(self):
        cycle = run_living_foam_cycle("Laat het veld kort ademen", context={"phase": "test"})
        runtime = mojo_runtime_status()

        self.assertIn(cycle["status"], {"online", "collapsed"})
        self.assertIn("field_coherence_percent", cycle)
        self.assertIn(runtime["mode"], {"mojo", "python_fallback"})
        self.assertFalse(runtime["fake_success"])


if __name__ == "__main__":
    unittest.main()
