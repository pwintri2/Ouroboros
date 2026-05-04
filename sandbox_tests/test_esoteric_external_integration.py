import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    np = None
from ouroboros_esoteric.apeiron_identity import ApeironField
from ouroboros_esoteric.entropy_monitor import EntropyMonitor
from ouroboros_esoteric.light_language import LightLanguageCompiler

from controller.ouroboros_esoteric_bridge import build_job_esoteric_context, reflect_job_result
from ouroboros_esoteric.memory_lattice import MemoryKind, OuroborosMemoryLattice
from ouroboros_esoteric.repository_integration import (
    ExternalRepoProfile,
    RepoSignal,
    integrate_external_repositories,
    scan_external_repositories,
)
from ouroboros_esoteric.social_memory import SocialMemoryComplex


class TestEsotericMemoryLattice(unittest.TestCase):
    def test_recall_reinforces_procedural_memory(self):
        lattice = OuroborosMemoryLattice(agent_id="test-agent")
        atom = lattice.remember(
            "Always run pytest before merge when touching agent runtime.",
            MemoryKind.PROCEDURAL,
            importance=8.0,
            tags=["agent-runtime", "tests"],
        )

        recalled = lattice.recall("run pytest before merging runtime", top_k=1)

        self.assertEqual(recalled[0].id, atom.id)
        self.assertEqual(recalled[0].access_count, 1)
        self.assertGreater(recalled[0].stability, 1.0)
        self.assertEqual(lattice.stats()["by_kind"]["procedural"], 1)

    def test_auto_classifies_capability_text(self):
        lattice = OuroborosMemoryLattice()

        atom = lattice.remember("SurfSense supports connector retrieval and memory tools.")

        self.assertEqual(atom.memory_kind, MemoryKind.CAPABILITY)


class TestLightLanguageCompiler(unittest.TestCase):
    def test_compile_to_geometry_is_stable_and_normalized(self):
        compiler = LightLanguageCompiler()

        first = compiler.compile_to_geometry("ouroboros external memory")
        second = compiler.compile_to_geometry("ouroboros external memory")
        other = compiler.compile_to_geometry("different intent")

        if np is not None:
            self.assertTrue(np.allclose(first, second))
            self.assertFalse(np.allclose(first, other))
            self.assertAlmostEqual(float(np.linalg.norm(first)), 1.0, places=6)
        else:
            self.assertEqual(first, second)
            self.assertNotEqual(first, other)
            norm = sum(value * value for row in first for value in row) ** 0.5
            self.assertAlmostEqual(norm, 1.0, places=6)


class TestPanDimensionalCore(unittest.TestCase):
    def test_apeiron_field_uses_compact_11d_shape_and_metrics(self):
        field = ApeironField()

        field.inject_text_intention("build runtime entropy bridge")
        metrics = field.metrics().to_dict()

        self.assertEqual(metrics["dimension_count"], 11)
        self.assertEqual(len(field.project_to_11d_pocket()), 11)
        self.assertGreater(metrics["coh"], 0.0)
        self.assertEqual(metrics["data_threshold"], 89)

    def test_entropy_monitor_measures_and_heals_high_entropy_lists(self):
        monitor = EntropyMonitor(entropy_threshold=0.01)

        result = monitor.measure([0.0, 1.0, float("nan"), -1.0])

        self.assertGreater(result["entropy_level"], 0.01)
        self.assertTrue(result["healed"])
        self.assertEqual(result["resonance_status"], "healed")


class TestExternalRepositoryIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="esoteric-repos-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _repo(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(parents=True)
        return path

    def test_scanner_extracts_signals_without_reading_env_files(self):
        repo = self._repo("guaardvark")
        service_dir = repo / "backend" / "services"
        service_dir.mkdir(parents=True)
        (service_dir / "agent_brain.py").write_text("# routing", encoding="utf-8")
        (service_dir / "tool_execution_guard.py").write_text("# guard", encoding="utf-8")
        (repo / ".env").write_text("SECRET=do-not-read", encoding="utf-8")
        (repo / "README.md").write_text("Three-tier neural routing", encoding="utf-8")

        profiles = scan_external_repositories({"guaardvark": str(repo)})
        guaardvark = next(profile for profile in profiles if profile.origin == "guaardvark")
        payload = guaardvark.to_dict()

        self.assertTrue(guaardvark.exists)
        self.assertIn("tiered_agent_router", guaardvark.capabilities)
        self.assertIn("tool_execution_guard", guaardvark.capabilities)
        self.assertNotIn("do-not-read", str(payload))

    def test_integration_merges_capabilities_into_social_memory(self):
        repo = self._repo("memoryos")
        package = repo / "memoryos"
        package.mkdir(parents=True)
        (package / "models.py").write_text("# retention", encoding="utf-8")
        (package / "retriever.py").write_text("# composite", encoding="utf-8")
        complex_network = SocialMemoryComplex()
        lattice = OuroborosMemoryLattice(agent_id="integrator-test")

        result = integrate_external_repositories(
            complex_network=complex_network,
            lattice=lattice,
            paths={"memoryos": str(repo)},
        )

        self.assertEqual(result["status"], "online")
        self.assertIn("memoryos_capabilities", complex_network.shared_memory)
        self.assertGreaterEqual(result["memory"]["total"], 2)


class TestEsotericRuntimeBridge(unittest.TestCase):
    def test_job_context_matches_task_to_memory_and_retrieval_sources(self):
        profiles = [
            ExternalRepoProfile(
                origin="memoryos",
                path="/tmp/memoryos",
                exists=True,
                capabilities=["composite_memory_ranker"],
                signals=[
                    RepoSignal(
                        name="composite_memory_ranker",
                        family="retrieval",
                        summary="Composite recall.",
                        strength=8.8,
                    )
                ],
            ),
            ExternalRepoProfile(
                origin="mengram",
                path="/tmp/mengram",
                exists=True,
                capabilities=["tri_memory_architecture"],
                signals=[
                    RepoSignal(
                        name="tri_memory_architecture",
                        family="memory",
                        summary="Tri memory.",
                        strength=9.2,
                    )
                ],
            ),
        ]

        context = build_job_esoteric_context("strengthen memory retrieval", profiles)

        names = {pattern["name"] for pattern in context["recommended_patterns"]}
        self.assertIn("composite_memory_ranker", names)
        self.assertIn("tri_memory_architecture", names)
        self.assertEqual(context["phase"], "external_repo_lattice")

    def test_pan_dimensional_job_context_contains_metrics_storage_and_broadcast(self):
        record = {"job_id": "codex_123", "task": "measure entropy in runtime"}

        context = build_job_esoteric_context(record["task"], [])
        from controller.ouroboros_esoteric_bridge import build_pan_dimensional_job_context

        pan = build_pan_dimensional_job_context(record, record["task"])

        self.assertTrue(pan["enabled"])
        self.assertEqual(pan["metrics"]["dimension_count"], 11)
        self.assertIn("hologram", pan["cosmic_storage"])
        self.assertIn("dna_backup", pan["cosmic_storage"])
        self.assertEqual(pan["akashic_event"]["frequency"], 528.0)
        self.assertTrue(context["enabled"])

    def test_reflection_marks_successful_test_job_as_procedural_candidate(self):
        record = {
            "job_id": "codex_1",
            "task": "fix tests and update pipeline",
            "metadata": {"ouroboros_esoteric": {"enabled": True}},
        }

        reflection = reflect_job_result(record, {"status": "completed", "exit_code": 0})

        self.assertTrue(reflection["promote_to_procedure"])
        self.assertEqual(record["metadata"]["ouroboros_esoteric"]["last_reflection"], reflection)


if __name__ == "__main__":
    unittest.main()
