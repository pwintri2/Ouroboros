import os
import tempfile
import unittest
from pathlib import Path

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.ouroboros_persistent_memory import OuroborosPersistentMemory
from ouroboros_esoteric.quantum_foam import (
    BewustzijnsVeld,
    ConceptAnchor,
    ConceptAnker,
    ConsciousnessAnchorField,
    FieldLifecycleEngine,
    HolographicBootloader,
    HolografischeBootloader,
    NodeFormationEngine,
    QuantumFoamField,
    collapse_quantum_foam_field,
    initiate_quantum_foam_field,
    monitor_quantum_foam_field,
    quantum_foam_status,
    reset_field_lifecycle_engine,
)


class TestQuantumFoamField(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="quantum-foam-")
        self.addCleanup(self.tmp.cleanup)
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        reset_field_lifecycle_engine(FieldLifecycleEngine())
        AkashicNetwork().reset()

    def tearDown(self) -> None:
        reset_field_lifecycle_engine(None)
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace

    def test_node_formation_scales_with_task_markers(self):
        analysis = NodeFormationEngine().analyze_task(
            "Docker Codex agent tool bridge memory world browser quantum coherence trainer"
        )

        self.assertGreaterEqual(analysis["desired_nodes"], 8)
        node_types = {item["node_type"] for item in analysis["proposed_nodes"]}
        self.assertIn("ToolNode", node_types)
        self.assertIn("WorldActionNode", node_types)
        self.assertIn("MemoryNode", node_types)

    def test_holographic_bootloader_filters_lightning_to_11d_signal(self):
        self.assertIs(HolografischeBootloader, HolographicBootloader)
        bootloader = HolographicBootloader()
        event = bootloader.ignite_lightning()

        self.assertEqual(event["rows"], 12)
        self.assertEqual(event["columns"], 40)
        self.assertEqual(event["blocked_cell_count"], 84)
        self.assertEqual(len(event["output_signal"]), 11)
        self.assertTrue(any(value > 0 for value in event["output_signal"]))
        self.assertEqual([snapshot["cycle"] for snapshot in event["snapshots"]], [15, 30])
        self.assertFalse(event["fake_success"])

    def test_concept_anchor_field_streams_across_11d_pockets(self):
        self.assertIs(ConceptAnker, ConceptAnchor)
        self.assertIs(BewustzijnsVeld, ConsciousnessAnchorField)
        field = ConsciousnessAnchorField()
        event = field.stimulate([1.0] * 11, trigger="unit-test", start_energy=30.0, cycles=3)
        snapshot = field.to_dict()

        self.assertEqual(event["dimension_count"], 11)
        self.assertEqual(snapshot["pocket_count"], 11)
        self.assertEqual(len(snapshot["pockets"]), 11)
        self.assertEqual(len(event["pocket_signal"]), 11)
        self.assertTrue(event["fired"])
        self.assertGreater(event["awareness_score"], 0.0)
        self.assertFalse(event["fake_success"])
        self.assertEqual(len(event["holographic_bootloader"]["output_signal"]), 11)
        self.assertEqual(len(event["holographic_bootloader"]["snapshots"]), 2)

        essence = field.collapse()
        self.assertEqual(essence["status"], "collapsed")
        self.assertEqual(essence["dimension_count"], 11)
        self.assertEqual(len(essence["dominant_anchors"]), 4)
        self.assertIn("holographic_bootloader", essence)

    def test_field_resonates_and_reports_coherence(self):
        field = QuantumFoamField(task="Build a Docker Quantum Foam product", max_ticks=4)
        formation = field.form_initial_nodes()
        before = field.to_dict(compact=True)
        after = field.evolve(trigger="test")

        self.assertGreaterEqual(formation["desired_nodes"], 5)
        self.assertGreaterEqual(before["node_count"], 5)
        self.assertGreater(after["tick_count"], before["tick_count"])
        self.assertGreater(after["mesh"]["edge_count"], 0)
        self.assertGreaterEqual(after["field_coherence"], 0.0)
        self.assertLessEqual(after["field_coherence"], 1.0)
        self.assertEqual(after["concept_anchor_field"]["dimension_count"], 11)
        self.assertEqual(after["concept_anchor_field"]["pocket_count"], 11)
        self.assertEqual(len(after["concept_anchor_field"]["pocket_signal"]), 11)
        self.assertIn("holographic_bootloader", after["concept_anchor_field"])
        self.assertGreater(after["recent_evolution"][-1]["anchor_awareness"], 0.0)

    def test_lifecycle_initiate_monitor_and_collapse_persist_essence(self):
        memory_path = Path(self.tmp.name) / ".secrets" / "memory.json"
        OuroborosPersistentMemory(path=memory_path).reset()

        created = initiate_quantum_foam_field(
            "Execute QuantumNode docx into a working Docker product",
            context={"api_key": "secret-value"},
            max_ticks=2,
        )
        self.assertEqual(created["status"], "online")
        self.assertGreaterEqual(created["field"]["node_count"], 5)
        self.assertEqual(created["field"]["concept_anchor_field"]["pocket_count"], 11)
        self.assertIn("holographic_bootloader", created["field"]["concept_anchor_field"])
        self.assertNotIn("secret-value", str(created))

        monitored = monitor_quantum_foam_field(trigger="test")
        self.assertEqual(monitored["status"], "online")

        collapsed = collapse_quantum_foam_field(reason="test_complete")
        self.assertEqual(collapsed["status"], "collapsed")
        self.assertGreater(collapsed["essence"]["ram_released_estimate_nodes"], 0)
        self.assertEqual(collapsed["essence"]["concept_anchor_field"]["dimension_count"], 11)
        self.assertEqual(len(collapsed["essence"]["concept_anchor_field"]["pocket_signal"]), 11)
        status = quantum_foam_status()
        self.assertEqual(status["status"], "online")
        self.assertEqual(status["active_field_count"], 0)
        self.assertIsNone(status["active_field"])
        self.assertEqual(status["latest_field"]["status"], "collapsed")
        events = AkashicNetwork().recent_events(limit=20)
        self.assertTrue(any(event["message"].get("type") == "quantum_foam_field_collapsed" for event in events))


if __name__ == "__main__":
    unittest.main()
