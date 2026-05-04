import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    from ouroboros_esoteric.light_language import LightLanguageCompiler
except ModuleNotFoundError:
    np = None
    LightLanguageCompiler = None

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
    @unittest.skipUnless(np is not None and LightLanguageCompiler is not None, "numpy ontbreekt in deze Python env")
    def test_compile_to_geometry_is_stable_and_normalized(self):
        compiler = LightLanguageCompiler()

        first = compiler.compile_to_geometry("ouroboros external memory")
        second = compiler.compile_to_geometry("ouroboros external memory")
        other = compiler.compile_to_geometry("different intent")

        self.assertTrue(np.allclose(first, second))
        self.assertFalse(np.allclose(first, other))
        self.assertAlmostEqual(float(np.linalg.norm(first)), 1.0, places=6)


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
