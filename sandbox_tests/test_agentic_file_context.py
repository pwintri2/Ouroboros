"""File context tracker staleness tests."""

import os
import tempfile
import time
import unittest
from pathlib import Path

from controller import agentic_file_context as tracker


class FileContextTests(unittest.TestCase):
    def setUp(self):
        tracker.reset_all()
        self._tmp = tempfile.TemporaryDirectory()
        self._root = self._tmp.name

    def tearDown(self):
        tracker.reset_all()
        self._tmp.cleanup()

    def _write(self, relative: str, content: str) -> str:
        path = Path(self._root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_recording_read_marks_path_fresh(self):
        self._write("a.txt", "hello")
        record = tracker.record_file_read("sess1", "a.txt", workspace_root=self._root)
        self.assertEqual(record["source"], tracker.SOURCE_READ)
        self.assertTrue(record["exists"])
        evaluated = tracker.evaluate_path("sess1", "a.txt", workspace_root=self._root)
        self.assertEqual(evaluated["status"], tracker.STATUS_FRESH)

    def test_modification_marks_path_stale(self):
        full = self._write("b.txt", "v1")
        tracker.record_file_read("sess2", "b.txt", workspace_root=self._root)
        time.sleep(0.05)
        new_mtime = time.time() + 5
        os.utime(full, (new_mtime, new_mtime))
        evaluated = tracker.evaluate_path("sess2", "b.txt", workspace_root=self._root)
        self.assertEqual(evaluated["status"], tracker.STATUS_STALE)
        stale = tracker.list_stale_files("sess2")
        self.assertEqual(len(stale), 1)

    def test_missing_path_status(self):
        full = self._write("c.txt", "v1")
        tracker.record_file_read("sess3", "c.txt", workspace_root=self._root)
        os.remove(full)
        evaluated = tracker.evaluate_path("sess3", "c.txt", workspace_root=self._root)
        self.assertEqual(evaluated["status"], tracker.STATUS_MISSING)

    def test_unknown_path_returns_unknown(self):
        evaluated = tracker.evaluate_path("sessX", "never_touched.txt", workspace_root=self._root)
        self.assertEqual(evaluated["status"], tracker.STATUS_UNKNOWN)

    def test_session_isolation(self):
        self._write("d.txt", "v1")
        tracker.record_file_read("sessA", "d.txt", workspace_root=self._root)
        files_a = tracker.list_files("sessA")
        files_b = tracker.list_files("sessB")
        self.assertEqual(len(files_a), 1)
        self.assertEqual(len(files_b), 0)


if __name__ == "__main__":
    unittest.main()
