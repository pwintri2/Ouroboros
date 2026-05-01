import importlib.util
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
CHROMA_AVAILABLE = importlib.util.find_spec("chromadb") is not None


class MockCollection:
    def __init__(self):
        self._store = {}

    def get(self, where=None, limit=100, ids=None, include=None):
        results = {"ids": [], "metadatas": [], "documents": []}
        rows = self._store.items()
        if ids is not None:
            rows = [(item_id, self._store[item_id]) for item_id in ids if item_id in self._store]
        for item_id, entry in rows:
            if where and not all(entry["metadata"].get(k) == v for k, v in where.items()):
                continue
            results["ids"].append(item_id)
            results["metadatas"].append(entry["metadata"])
            results["documents"].append(entry["document"])
            if len(results["ids"]) >= limit:
                break
        return results

    def add(self, documents, metadatas, ids, embeddings=None):
        for doc, meta, item_id in zip(documents, metadatas, ids):
            self._store[item_id] = {"document": doc, "metadata": dict(meta)}

    def count(self):
        return len(self._store)


@unittest.skipUnless(FASTAPI_AVAILABLE and CHROMA_AVAILABLE, "FastAPI/ChromaDB test dependencies are not installed")
class TestContinuousTrainer(unittest.TestCase):
    def test_browser_ingest_can_trigger_litgpt_and_unsloth_dataset_jobs(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from controller.api.trainer_pipeline_routes import init_trainer_pipeline
        from controller.api.training_routes import init_training
        from controller.stream.storage import StreamStorage

        previous = {
            "WINTRIP_DB_PATH": os.environ.get("WINTRIP_DB_PATH"),
            "WINTRIP_TRAINING_COLLECTION": os.environ.get("WINTRIP_TRAINING_COLLECTION"),
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
        }
        try:
            with tempfile.TemporaryDirectory(prefix="continuous-trainer-") as tmp:
                workspace = Path(tmp)
                os.environ["WINTRIP_DB_PATH"] = str(workspace / "brain")
                os.environ["WINTRIP_TRAINING_COLLECTION"] = f"continuous_{uuid.uuid4().hex}"
                os.environ["WINTRIP_WORKSPACE"] = str(workspace)

                app = FastAPI()
                init_training(app, storage=StreamStorage(collection=MockCollection()))
                init_trainer_pipeline(app)
                client = TestClient(app)

                ingest = client.post(
                    "/trainer/browser/ingest",
                    json={
                        "url": "https://teachablemachine.withgoogle.com/train",
                        "browser_text": "Wintrip AI approved browser call feeds LitGPT and Unsloth continuous trainers.",
                        "approval": "Akkoord",
                        "notify_continuous": True,
                        "trigger_tick": True,
                        "execute_training": False,
                        "methods": ["litgpt", "unsloth"],
                    },
                )
                self.assertEqual(ingest.status_code, 200)
                data = ingest.json()
                self.assertEqual(data["status"], "stored")
                self.assertTrue(data["stored"])
                self.assertEqual(data["tick"]["status"], "success")
                self.assertEqual(len(data["tick"]["jobs"]), 2)
                self.assertTrue(Path(data["tick"]["dataset"]["output_path"]).exists())

                jobs = client.get("/trainer/jobs").json()["jobs"]
                methods = {job["method"] for job in jobs}
                self.assertIn("litgpt", methods)
                self.assertIn("unsloth", methods)
                self.assertTrue(all(job["state"] == "dataset_ready" for job in jobs))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
