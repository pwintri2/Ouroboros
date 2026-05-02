import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEcosystemCurriculum(unittest.TestCase):
    def test_new_ecosystem_tracks_are_visible(self):
        from controller.training_curriculum import classify_record, list_curricula

        curricula = list_curricula()["curricula"]
        ids = {item["id"] for item in curricula}
        for expected in {"popos_mastery", "os_cross_platform", "google_ecosystem", "sharepoint_deep", "agentic_crawling"}:
            self.assertIn(expected, ids)

        google = classify_record("Drive API OAuth2 Calendar API service accounts", {})
        self.assertIn("google_ecosystem", google["labels"])
        crawler = classify_record("Crawl filesystem with gitignore privacy filters and content hash", {})
        self.assertIn("agentic_crawling", crawler["labels"])

    def test_ecosystem_knowledge_ingest_requires_approval_and_writes_records(self):
        from controller.ecosystem_knowledge_ingest import ingest_ecosystem_knowledge, parse_knowledge_list

        text = """# Kennislijst
## 1. Pop!_OS Linux Laptop
### 1.1 Hardware
- System76 hardware and recovery partition
## 3. Google Ecosysteem
### 3.1 APIs
- Google Drive API v3 and OAuth2 scopes
"""
        parsed = parse_knowledge_list(text)
        self.assertEqual(len(parsed["records"]), 2)
        self.assertEqual(parsed["track_counts"]["popos_mastery"], 1)
        self.assertEqual(parsed["track_counts"]["google_ecosystem"], 1)

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        with tempfile.TemporaryDirectory(prefix="ecosystem-ingest-") as tmp:
            os.environ["WINTRIP_WORKSPACE"] = tmp
            path = Path(tmp) / "OUROBOROS_KENNIS_LIJST.md"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(ingest_ecosystem_knowledge(approval="", path=str(path))["status"], "blocked")
            result = ingest_ecosystem_knowledge(approval="Akkoord", path=str(path))
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["topic_count"], 2)
            self.assertTrue(Path(result["artifact_path"]).exists())
        if previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
