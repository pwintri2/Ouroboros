# sandbox_tests/test_safe_shell.py

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from controller.safe_shell import run_safe_shell


class TestSafeShell(unittest.TestCase):
    def setUp(self):
        self._old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self._old_path = os.environ.get("PATH")
        self.workspace = tempfile.mkdtemp(prefix="wintrip-shell-test-")
        os.environ["WINTRIP_WORKSPACE"] = self.workspace

    def tearDown(self):
        if self._old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self._old_workspace
        if self._old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._old_path
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_requires_approval(self):
        result = run_safe_shell("pwd", approval="")
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["approved"])

    def test_approval_phrase_is_exact(self):
        result = run_safe_shell("pwd", approval="akkoord")
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["approved"])

    def test_runs_safe_command_in_workspace(self):
        result = run_safe_shell("pwd", approval="Akkoord")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stdout"].strip(), self.workspace)

    def test_allows_gemini_cli_command(self):
        gemini = Path(self.workspace) / "gemini"
        gemini.write_text("#!/usr/bin/env sh\nprintf 'gemini ok\\n'\n", encoding="utf-8")
        gemini.chmod(0o755)
        os.environ["PATH"] = os.pathsep.join([self.workspace, self._old_path or ""])

        result = run_safe_shell("gemini --version", approval="Akkoord")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stdout"], "gemini ok\n")

    def test_blocks_path_escape(self):
        result = run_safe_shell("cat /etc/passwd", approval="Akkoord")
        self.assertEqual(result["status"], "error")
        self.assertIn("buiten /workspace", result["reason"])

    def test_blocks_find_exec(self):
        result = run_safe_shell("find . -exec pwd ;", approval="Akkoord")
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
