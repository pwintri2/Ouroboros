import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAgenticCrawler(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="agentic-crawler-")
        self.root = Path(self.tmp.name)
        os.environ["WINTRIP_WORKSPACE"] = str(self.root)
        (self.root / "notes.md").write_text("Ouroboros public note", encoding="utf-8")
        (self.root / ".env").write_text("API_KEY=secret", encoding="utf-8")
        (self.root / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
        (self.root / "ignored.log").write_text("ignore me", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_filesystem_crawl_requires_approval(self):
        from controller.agentic_crawler import crawl_filesystem

        result = crawl_filesystem(paths=[str(self.root)], approval="")
        self.assertEqual(result["status"], "blocked")

    def test_filesystem_crawl_filters_private_and_gitignored_files(self):
        from controller.agentic_crawler import crawl_filesystem, get_agentic_crawler_status

        result = crawl_filesystem(paths=[str(self.root)], approval="Akkoord", max_files=10)
        self.assertEqual(result["status"], "success")
        titles = {record["title"] for record in result["records"]}
        self.assertIn("notes.md", titles)
        self.assertIn("src/app.py", titles)
        self.assertNotIn(".env", titles)
        self.assertNotIn("ignored.log", titles)
        self.assertGreaterEqual(result["skipped_private"], 2)
        self.assertFalse(any("API_KEY=secret" in str(record) for record in result["records"]))

        status = get_agentic_crawler_status()
        self.assertEqual(status["indexed_files"], 2)

    def test_cross_service_action_is_proposal_only(self):
        from controller.agentic_crawler import propose_cross_service_action

        result = propose_cross_service_action([{"title": "notes.md"}], target_service="sharepoint")
        self.assertEqual(result["status"], "proposal")
        self.assertTrue(result["plan"]["approval_required"])


if __name__ == "__main__":
    unittest.main()
