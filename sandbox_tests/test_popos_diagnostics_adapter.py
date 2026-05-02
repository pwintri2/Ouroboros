import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPopOSDiagnosticsAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="popos-diagnostics-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_status_reports_commands_without_running_diagnostics(self):
        from controller.popos_diagnostics_adapter import get_popos_diagnostics_status

        status = get_popos_diagnostics_status()
        self.assertEqual(status["status"], "ready")
        self.assertIn("journal_errors", status["commands"])
        self.assertTrue(status["approval_required"])
        self.assertFalse(status["fake_success"])

    def test_diagnostics_requires_akkoord(self):
        from controller.popos_diagnostics_adapter import run_popos_diagnostics

        result = run_popos_diagnostics(approval="", command_keys=["uptime"])
        self.assertEqual(result["status"], "blocked")

    def test_diagnostics_writes_structured_11d_artifact(self):
        from controller.popos_diagnostics_adapter import popos_diagnostics_output_dir, run_popos_diagnostics

        result = run_popos_diagnostics(approval="Akkoord", command_keys=["uptime", "free", "df"])
        self.assertEqual(result["status"], "success")
        self.assertIn("augmentation", result)
        self.assertEqual(len(result["record"]["11d"]["vector"]), 11)
        self.assertTrue(Path(result["artifact_path"]).exists())
        self.assertTrue(Path(popos_diagnostics_output_dir()).exists())
        self.assertIn("recommended_power_profile", result["recommendation"])


if __name__ == "__main__":
    unittest.main()
