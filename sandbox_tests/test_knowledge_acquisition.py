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


KNOWLEDGE_MD = """# Kennislijst

## 1. Pop!_OS Linux Laptop

### 1.1 Kernel & Low-Level
- systemd, cgroups v2, namespaces en seccomp
- memory management met OOM killer en PSI

## 2. Google Ecosysteem

### 2.1 Google Workspace
- Gmail labels, Google Drive shared drives en Calendar API

## 3. Microsoft Ecosysteem

### 3.1 SharePoint
- Document Libraries, permissions, Graph en PnP PowerShell
"""


class KnowledgeAcquisitionEnv:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="knowledge-acquisition-")
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.db = self.root / "brain"
        self.knowledge = self.root / "OUROBOROS_KENNIS_LIJST.md"
        self.workspace.mkdir()
        self.db.mkdir()
        self.knowledge.write_text(KNOWLEDGE_MD, encoding="utf-8")
        self.previous = {
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
            "WINTRIP_DB_PATH": os.environ.get("WINTRIP_DB_PATH"),
            "WINTRIP_KNOWLEDGE_LIST_PATH": os.environ.get("WINTRIP_KNOWLEDGE_LIST_PATH"),
        }
        os.environ["WINTRIP_WORKSPACE"] = str(self.workspace)
        os.environ["WINTRIP_DB_PATH"] = str(self.db)
        os.environ["WINTRIP_KNOWLEDGE_LIST_PATH"] = str(self.knowledge)
        return self

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class TestKnowledgeAcquisition(unittest.TestCase):
    def test_parse_index_and_bounded_tick_store_records(self):
        from controller import knowledge_acquisition as ka

        with KnowledgeAcquisitionEnv():
            parsed = ka.parse_knowledge_list()
            self.assertEqual(parsed["status"], "success")
            self.assertGreaterEqual(parsed["topic_count"], 5)
            self.assertTrue(any("SharePoint" in topic["title"] for topic in parsed["topics"]))

            blocked = ka.index_knowledge_list(approval="nee")
            self.assertEqual(blocked["status"], "blocked")

            indexed = ka.index_knowledge_list(approval="Akkoord")
            self.assertEqual(indexed["status"], "success")

            original_gemma = ka.distill_gemma_topic
            original_browser = ka.browser_research_topic
            original_store = ka.store_knowledge_record
            try:
                ka.distill_gemma_topic = lambda topic, model="gemma4:latest": {
                    "status": "success",
                    "document": f"Gemma distillation for {topic['title']} with Python Linux SharePoint.",
                    "source": f"ollama:{model}",
                    "model": model,
                    "fake_success": False,
                }
                ka.browser_research_topic = lambda topic, approval="": {
                    "status": "success",
                    "document": f"Browser observed public result for {topic['title']} and Google Workspace.",
                    "source_url": "https://example.com/",
                    "browser_action_performed": True,
                    "bulk_scraping": False,
                    "taint": "scrubbed_browser",
                    "fake_success": False,
                }
                ka.store_knowledge_record = lambda document, metadata: {
                    "status": "success",
                    "stored": True,
                    "item_id": f"test_{metadata['topic_id']}_{metadata['source_type']}",
                    "fake_success": False,
                }
                tick = ka.run_knowledge_tick(approval="Akkoord", mode="both", max_topics=2)
            finally:
                ka.distill_gemma_topic = original_gemma
                ka.browser_research_topic = original_browser
                ka.store_knowledge_record = original_store

            self.assertEqual(tick["status"], "success")
            self.assertEqual(tick["created_count"], 4)
            status = ka.get_knowledge_acquisition_status()
            self.assertEqual(status["gemma_completed"], 2)
            self.assertEqual(status["browser_completed"], 2)
            self.assertGreaterEqual(status["total_records"], 4)


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestKnowledgeAcquisitionRoutes(unittest.TestCase):
    def test_routes_status_block_and_tick(self):
        from controller import knowledge_acquisition as ka
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline

        with KnowledgeAcquisitionEnv():
            original_gemma = ka.distill_gemma_topic
            original_browser = ka.browser_research_topic
            original_store = ka.store_knowledge_record
            try:
                ka.distill_gemma_topic = lambda topic, model="gemma4:latest": {
                    "status": "success",
                    "document": f"Route Gemma record for {topic['title']} Linux.",
                    "source": f"ollama:{model}",
                    "model": model,
                    "fake_success": False,
                }
                ka.browser_research_topic = lambda topic, approval="": {
                    "status": "success",
                    "document": f"Route browser record for {topic['title']} SharePoint.",
                    "source_url": "https://example.com/",
                    "browser_action_performed": True,
                    "bulk_scraping": False,
                    "fake_success": False,
                }
                ka.store_knowledge_record = lambda document, metadata: {
                    "status": "success",
                    "stored": True,
                    "item_id": f"route_{metadata['topic_id']}_{metadata['source_type']}",
                    "fake_success": False,
                }

                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                status = client.get("/trainer/knowledge/status")
                self.assertEqual(status.status_code, 200)
                self.assertGreaterEqual(status.json()["topic_count"], 5)

                blocked = client.post("/trainer/knowledge/index-list", json={"approval": "nee"})
                self.assertEqual(blocked.status_code, 403)

                indexed = client.post("/trainer/knowledge/index-list", json={"approval": "Akkoord"})
                self.assertEqual(indexed.status_code, 200)
                self.assertEqual(indexed.json()["status"], "success")

                tick = client.post(
                    "/trainer/knowledge/tick",
                    json={"approval": "Akkoord", "mode": "gemma", "max_topics": 1, "model": "gemma4:latest"},
                )
                self.assertEqual(tick.status_code, 200)
                self.assertEqual(tick.json()["created_count"], 1)
            finally:
                ka.distill_gemma_topic = original_gemma
                ka.browser_research_topic = original_browser
                ka.store_knowledge_record = original_store


if __name__ == "__main__":
    unittest.main()
