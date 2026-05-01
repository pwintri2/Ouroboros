import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLocalMachineProfile(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="local-machine-profile-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_snapshot_requires_approval_and_writes_profile(self):
        from controller.local_machine_profile import get_local_machine_status, local_machine_profile_path, snapshot_local_machine

        blocked = snapshot_local_machine(approval="")
        self.assertEqual(blocked["status"], "blocked")

        snapshot = snapshot_local_machine(approval="Akkoord")
        self.assertEqual(snapshot["status"], "success")
        self.assertIn("os", snapshot)
        self.assertIn("hardware", snapshot)
        self.assertTrue(Path(local_machine_profile_path()).exists())

        status = get_local_machine_status()
        self.assertEqual(status["status"], "profiled")
        self.assertEqual(status["fake_success"], False)


if __name__ == "__main__":
    unittest.main()
