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


def _write_fake_codeneuron(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "coreneuron" / "mechanism").mkdir(parents=True)
    (root / "tests" / "unit" / "alignment").mkdir(parents=True)
    (root / "CMake").mkdir(parents=True)
    (root / "docs" / "index.md").write_text("# CoreNEURON\n\nGPU offload, MPI, checkpoint reports.\n", encoding="utf-8")
    (root / "coreneuron" / "mechanism" / "ion.cpp").write_text(
        "// mechanism ion channel nrn_state current\nvoid advance() {}\n",
        encoding="utf-8",
    )
    (root / "tests" / "unit" / "alignment" / "alignment.cpp").write_text(
        "ASSERT_TRUE(soa_padded_size(11)); // validation test soa padding memory layout\n",
        encoding="utf-8",
    )
    (root / "CMake" / "compiler.cmake").write_text("set(CMAKE_CXX_STANDARD 17) # compiler runtime hardware\n", encoding="utf-8")


class TestCodeNeuronAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_codeneuron = os.environ.get("WINTRIP_CODENEURON_PATH")
        self.tmp = tempfile.TemporaryDirectory(prefix="codeneuron-adapter-")
        self.workspace = Path(self.tmp.name) / "workspace"
        self.root = Path(self.tmp.name) / "CodeNeuron"
        self.workspace.mkdir()
        _write_fake_codeneuron(self.root)
        os.environ["WINTRIP_WORKSPACE"] = str(self.workspace)
        os.environ["WINTRIP_CODENEURON_PATH"] = str(self.root)

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace
        if self.previous_codeneuron is None:
            os.environ.pop("WINTRIP_CODENEURON_PATH", None)
        else:
            os.environ["WINTRIP_CODENEURON_PATH"] = self.previous_codeneuron

    def test_index_status_search_and_pocket_map(self):
        from controller.codeneuron_adapter import (
            get_codeneuron_pocket_map,
            get_codeneuron_status,
            index_codeneuron,
            search_codeneuron,
        )

        status = get_codeneuron_status()
        self.assertEqual(status["status"], "available")
        self.assertTrue(status["root_exists"])

        indexed = index_codeneuron(max_files=50, max_bytes_per_file=4096)
        self.assertEqual(indexed["status"], "success")
        self.assertGreaterEqual(indexed["file_count"], 4)
        self.assertIn("d05_memory_layout_soa_padding", indexed["dimension_counts"])

        search = search_codeneuron("soa padding", limit=5)
        self.assertEqual(search["status"], "success")
        self.assertTrue(search["results"])

        pocket = get_codeneuron_pocket_map()
        self.assertEqual(pocket["dimension_count"], 11)
        source_counts = [dimension["source_count"] for dimension in pocket["dimensions"]]
        self.assertGreater(max(source_counts), 0)


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestCodeNeuronRoutes(unittest.TestCase):
    def test_codeneuron_routes_are_registered(self):
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        previous_codeneuron = os.environ.get("WINTRIP_CODENEURON_PATH")
        try:
            with tempfile.TemporaryDirectory(prefix="codeneuron-routes-") as tmp:
                workspace = Path(tmp) / "workspace"
                root = Path(tmp) / "CodeNeuron"
                workspace.mkdir()
                _write_fake_codeneuron(root)
                os.environ["WINTRIP_WORKSPACE"] = str(workspace)
                os.environ["WINTRIP_CODENEURON_PATH"] = str(root)

                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                status = client.get("/trainer/codeneuron/status")
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.json()["root_exists"], True)

                indexed = client.post("/trainer/codeneuron/index", json={"max_files": 50, "max_bytes_per_file": 4096})
                self.assertEqual(indexed.status_code, 200)
                self.assertEqual(indexed.json()["status"], "success")

                pocket = client.get("/trainer/codeneuron/pocket-map")
                self.assertEqual(pocket.status_code, 200)
                self.assertEqual(pocket.json()["dimension_count"], 11)

                search = client.get("/trainer/codeneuron/search?q=mpi")
                self.assertEqual(search.status_code, 200)
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace
            if previous_codeneuron is None:
                os.environ.pop("WINTRIP_CODENEURON_PATH", None)
            else:
                os.environ["WINTRIP_CODENEURON_PATH"] = previous_codeneuron


if __name__ == "__main__":
    unittest.main()
