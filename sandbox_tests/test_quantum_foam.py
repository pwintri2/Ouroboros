import os
import tempfile
import unittest
from pathlib import Path

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.ouroboros_persistent_memory import OuroborosPersistentMemory
from ouroboros_esoteric.quantum_foam import (
    FieldLifecycleEngine,
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
        self.assertNotIn("secret-value", str(created))

        monitored = monitor_quantum_foam_field(trigger="test")
        self.assertEqual(monitored["status"], "online")

        collapsed = collapse_quantum_foam_field(reason="test_complete")
        self.assertEqual(collapsed["status"], "collapsed")
        self.assertGreater(collapsed["essence"]["ram_released_estimate_nodes"], 0)
        status = quantum_foam_status()
        self.assertEqual(status["status"], "online")
        self.assertEqual(status["active_field_count"], 0)
        self.assertIsNone(status["active_field"])
        self.assertEqual(status["latest_field"]["status"], "collapsed")
        events = AkashicNetwork().recent_events(limit=20)
        self.assertTrue(any(event["message"].get("type") == "quantum_foam_field_collapsed" for event in events))


if __name__ == "__main__":
    unittest.main()
