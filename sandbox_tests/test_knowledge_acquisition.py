import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
            "WINTRIP_KNOWLEDGE_PARALLELISM": os.environ.get("WINTRIP_KNOWLEDGE_PARALLELISM"),
            "BRAVE_SEARCH_API_KEY": os.environ.get("BRAVE_SEARCH_API_KEY"),
        }
        os.environ["WINTRIP_WORKSPACE"] = str(self.workspace)
        os.environ["WINTRIP_DB_PATH"] = str(self.db)
        os.environ["WINTRIP_KNOWLEDGE_LIST_PATH"] = str(self.knowledge)
        os.environ.pop("BRAVE_SEARCH_API_KEY", None)
        return self

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class TestKnowledgeAcquisition(unittest.TestCase):
    def test_parse_uses_workspace_artifact_fallback_when_default_path_is_missing(self):
        from controller import knowledge_acquisition as ka

        tmp = tempfile.TemporaryDirectory(prefix="knowledge-fallback-")
        root = Path(tmp.name)
        workspace = root / "workspace"
        artifact_dir = workspace / "artifacts"
        artifact = artifact_dir / "OUROBOROS_KENNIS_LIJST.md"
        artifact_dir.mkdir(parents=True)
        artifact.write_text(KNOWLEDGE_MD, encoding="utf-8")
        previous = {
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
            "WINTRIP_KNOWLEDGE_LIST_PATH": os.environ.get("WINTRIP_KNOWLEDGE_LIST_PATH"),
        }
        try:
            os.environ["WINTRIP_WORKSPACE"] = str(workspace)
            os.environ.pop("WINTRIP_KNOWLEDGE_LIST_PATH", None)
            with patch.object(ka, "DEFAULT_KNOWLEDGE_LIST_PATH", str(root / "Downloads" / "missing.md")):
                parsed = ka.parse_knowledge_list()
                self.assertEqual(parsed["status"], "success")
                self.assertEqual(parsed["path"], str(artifact.resolve()))

                ka._save_state({"records": [], "last_error": "old missing path", "fake_success": False})
                status = ka.get_knowledge_acquisition_status()
                self.assertEqual(status["status"], "ready")
                self.assertGreater(status["topic_count"], 0)
                self.assertEqual(status["last_error"], "")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            tmp.cleanup()

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

    def test_brave_tick_stores_llm_context_records(self):
        from controller import knowledge_acquisition as ka

        with KnowledgeAcquisitionEnv():
            original_brave = ka.brave_research_topic
            original_store = ka.store_knowledge_record
            try:
                ka.brave_research_topic = lambda topic, approval="": {
                    "status": "success",
                    "document": f"Brave LLM context for {topic['title']} with fresh web grounding.",
                    "source": "brave:llm_context",
                    "source_urls": ["https://example.com/brave"],
                    "taint": "untrusted_web:brave_llm_context",
                    "fake_success": False,
                }
                seen_metadata = []

                def fake_store(document, metadata):
                    seen_metadata.append(metadata)
                    return {
                        "status": "success",
                        "stored": True,
                        "item_id": f"brave_{metadata['topic_id']}",
                        "fake_success": False,
                    }

                ka.store_knowledge_record = fake_store
                tick = ka.run_knowledge_tick(approval="Akkoord", mode="brave", max_topics=2)
            finally:
                ka.brave_research_topic = original_brave
                ka.store_knowledge_record = original_store

            self.assertEqual(tick["status"], "success")
            self.assertEqual(tick["created_count"], 2)
            self.assertEqual(tick["parallelism"]["brave_llm_context"], 2)
            self.assertTrue(all(item["source_type"] == "brave_llm_context" for item in seen_metadata))
            self.assertTrue(all(item["dimension_count"] == 11 for item in seen_metadata))
            status = ka.get_knowledge_acquisition_status()
            self.assertEqual(status["brave_completed"], 2)

    def test_gemma_tick_uses_bounded_parallelism(self):
        from controller import knowledge_acquisition as ka

        with KnowledgeAcquisitionEnv():
            os.environ["WINTRIP_KNOWLEDGE_PARALLELISM"] = "3"
            active = 0
            max_active = 0
            lock = threading.Lock()

            def fake_distill(topic, model="gemma4:latest"):
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.02)
                with lock:
                    active -= 1
                return {
                    "status": "success",
                    "document": f"Parallel Gemma distillation for {topic['title']}.",
                    "source": f"ollama:{model}",
                    "model": model,
                    "fake_success": False,
                }

            original_gemma = ka.distill_gemma_topic
            original_store = ka.store_knowledge_record
            try:
                ka.distill_gemma_topic = fake_distill
                ka.store_knowledge_record = lambda document, metadata: {
                    "status": "success",
                    "stored": True,
                    "item_id": f"parallel_{metadata['topic_id']}",
                    "fake_success": False,
                }
                tick = ka.run_knowledge_tick(approval="Akkoord", mode="gemma", max_topics=3)
            finally:
                ka.distill_gemma_topic = original_gemma
                ka.store_knowledge_record = original_store

            self.assertEqual(tick["status"], "success")
            self.assertEqual(tick["created_count"], 3)
            self.assertEqual(tick["parallelism"]["gemma_distillation"], 3)
            self.assertGreaterEqual(max_active, 2)

    def test_gemma_tick_prioritizes_curriculum_gaps(self):
        from controller import knowledge_acquisition as ka

        with KnowledgeAcquisitionEnv() as env:
            env.knowledge.write_text(
                """# Kennislijst

## Pop!_OS
### Pop!_OS thermal checks
- System76 recovery partition and NVIDIA powerprofilesctl

## SharePoint
### SharePoint unique permissions PnP PowerShell
- SharePoint unique permissions and PnP PowerShell
""",
                encoding="utf-8",
            )
            ka._save_state(
                {
                    "records": [
                        {
                            "topic_id": "historic_popos",
                            "source_type": "gemma_distillation",
                            "status": "success",
                            "curriculum_primary": "local_machine",
                        },
                        {
                            "topic_id": "historic_popos_mastery",
                            "source_type": "gemma_distillation",
                            "status": "success",
                            "curriculum_primary": "popos_mastery",
                        }
                    ],
                    "fake_success": False,
                }
            )
            selected_titles = []
            original_gemma = ka.distill_gemma_topic
            original_store = ka.store_knowledge_record
            try:
                def fake_distill(topic, model="gemma4:latest"):
                    selected_titles.append(topic["title"])
                    return {
                        "status": "success",
                        "document": f"Gap-prioritized record for {topic['title']}.",
                        "source": f"ollama:{model}",
                        "model": model,
                        "fake_success": False,
                    }

                ka.distill_gemma_topic = fake_distill
                ka.store_knowledge_record = lambda document, metadata: {
                    "status": "success",
                    "stored": True,
                    "item_id": f"gap_{metadata['topic_id']}",
                    "fake_success": False,
                }
                tick = ka.run_knowledge_tick(approval="Akkoord", mode="gemma", max_topics=1)
            finally:
                ka.distill_gemma_topic = original_gemma
                ka.store_knowledge_record = original_store

            self.assertEqual(tick["status"], "success")
            self.assertEqual(tick["selection_strategy"], "curriculum_gap_first")
            self.assertEqual(len(selected_titles), 1)
            self.assertIn("SharePoint", selected_titles[0])
            self.assertEqual(
                tick["selected_topics"]["gemma_distillation"][0]["curriculum_primary"],
                "sharepoint",
            )

    def test_topic_selection_does_not_stall_on_failed_attempt(self):
        from controller import knowledge_acquisition as ka

        topics = [
            {
                "id": "python_tests",
                "index": 0,
                "title": "Python test failures",
                "curriculum": {"primary": "programming"},
            },
            {
                "id": "python_refactor",
                "index": 1,
                "title": "Python refactor patterns",
                "curriculum": {"primary": "programming"},
            },
        ]
        selected = ka._select_topics(
            topics=topics,
            completed=set(),
            limit=1,
            start_index=None,
            records=[
                {
                    "topic_id": "python_tests",
                    "source_type": "gemma_distillation",
                    "status": "error",
                    "curriculum_primary": "programming",
                }
            ],
            source_type="gemma_distillation",
        )

        self.assertEqual(selected[0]["id"], "python_refactor")


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
