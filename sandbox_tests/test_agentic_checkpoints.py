"""Checkpoint metadata tests against a temporary git repo."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from controller import agentic_checkpoints as checkpoints


GIT_AVAILABLE = shutil.which("git") is not None


@unittest.skipUnless(GIT_AVAILABLE, "git binary not available")
class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._root = self._tmp.name
        self._run("git", "init", "-q")
        self._run("git", "config", "user.email", "test@example.com")
        self._run("git", "config", "user.name", "Test")
        Path(self._root, "seed.txt").write_text("initial\n", encoding="utf-8")
        self._run("git", "add", ".")
        self._run("git", "commit", "-q", "-m", "seed")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args: str) -> None:
        subprocess.run(args, cwd=self._root, check=True, capture_output=True)

    def test_begin_records_head_and_branch(self):
        checkpoint = checkpoints.begin_checkpoint(workspace_root=self._root, reason="test")
        self.assertEqual(checkpoint["status"], checkpoints.STATUS_RECORDED)
        self.assertTrue(checkpoint["head_before"])
        self.assertTrue(checkpoint["branch"])
        self.assertEqual(checkpoint["porcelain_before"], [])

    def test_finalize_detects_new_file(self):
        checkpoint = checkpoints.begin_checkpoint(workspace_root=self._root)
        Path(self._root, "new.txt").write_text("added\n", encoding="utf-8")
        finalized = checkpoints.finalize_checkpoint(checkpoint, workspace_root=self._root)
        self.assertEqual(finalized["status"], checkpoints.STATUS_RECORDED)
        self.assertIn("new.txt", finalized["untracked_files"])

    def test_finalize_detects_modified_file(self):
        checkpoint = checkpoints.begin_checkpoint(workspace_root=self._root)
        Path(self._root, "seed.txt").write_text("changed\n", encoding="utf-8")
        finalized = checkpoints.finalize_checkpoint(checkpoint, workspace_root=self._root)
        self.assertEqual(finalized["status"], checkpoints.STATUS_RECORDED)
        self.assertIn("seed.txt", finalized["changed_files"])
        self.assertGreaterEqual(finalized["changed_files_count"], 1)

    def test_finalize_no_changes_reports_status(self):
        checkpoint = checkpoints.begin_checkpoint(workspace_root=self._root)
        finalized = checkpoints.finalize_checkpoint(checkpoint, workspace_root=self._root)
        self.assertEqual(finalized["status"], checkpoints.STATUS_NO_CHANGES)

    def test_diff_for_path_returns_content(self):
        Path(self._root, "seed.txt").write_text("changed\n", encoding="utf-8")
        diff = checkpoints.diff_for_path("seed.txt", workspace_root=self._root)
        self.assertEqual(diff["status"], "ok")
        self.assertIn("changed", diff["diff"])

    def test_non_git_workspace_returns_unavailable(self):
        outside = tempfile.mkdtemp()
        try:
            result = checkpoints.begin_checkpoint(workspace_root=outside)
            self.assertEqual(result["status"], checkpoints.STATUS_UNAVAILABLE)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
