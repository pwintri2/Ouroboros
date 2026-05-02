import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHostProgramInventory(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="host-program-inventory-")
        self.root = Path(self.tmp.name)
        os.environ["WINTRIP_WORKSPACE"] = str(self.root)

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_scan_requires_approval(self):
        from controller.host_program_inventory import scan_host_program_inventory

        result = scan_host_program_inventory(approval="")
        self.assertEqual(result["status"], "blocked")

    def test_scan_writes_artifact_and_status(self):
        from controller.host_program_inventory import get_host_program_inventory_status, scan_host_program_inventory

        result = scan_host_program_inventory(
            approval="Akkoord",
            max_desktop_apps=20,
            max_packages=50,
            max_path_binaries=50,
        )
        self.assertEqual(result["status"], "success")
        self.assertIn(result["scope"], {"host", "docker_container"})
        self.assertTrue(Path(result["artifact_path"]).exists())
        self.assertEqual(len(result["record"]["11d"]["vector"]), 11)

        status = get_host_program_inventory_status()
        self.assertEqual(status["status"], "success")
        self.assertIn("desktop_app_count", status)


if __name__ == "__main__":
    unittest.main()
