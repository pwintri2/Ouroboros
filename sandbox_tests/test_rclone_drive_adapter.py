import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestRcloneDriveAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_rclone_config = os.environ.get("RCLONE_CONFIG")
        self.tmp = tempfile.TemporaryDirectory(prefix="rclone-drive-adapter-")
        self.root = Path(self.tmp.name)
        os.environ["WINTRIP_WORKSPACE"] = str(self.root)
        self.config = self.root / "rclone.conf"
        self.config.write_text("[gdrive]\ntype = drive\n", encoding="utf-8")
        os.environ["RCLONE_CONFIG"] = str(self.config)
        self.binary = self.root / "fake-rclone"
        self.binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "if sys.argv[1:2] == ['version']:\n"
            "    print('rclone vtest')\n"
            "elif sys.argv[1:2] == ['lsjson']:\n"
            "    print(json.dumps([{'Name':'Doc','Path':'Doc','IsDir':False,'Size':12,'MimeType':'text/plain'}]))\n"
            "else:\n"
            "    raise SystemExit(2)\n",
            encoding="utf-8",
        )
        self.binary.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace
        if self.previous_rclone_config is None:
            os.environ.pop("RCLONE_CONFIG", None)
        else:
            os.environ["RCLONE_CONFIG"] = self.previous_rclone_config

    def test_status_detects_drive_remote_without_tokens(self):
        from controller.rclone_drive_adapter import RcloneDriveAdapter

        status = RcloneDriveAdapter(binary=str(self.binary)).status()
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["drive_remotes"], ["gdrive"])
        self.assertFalse(status["tokens_returned"])

    def test_listing_requires_approval(self):
        from controller.rclone_drive_adapter import RcloneDriveAdapter

        result = RcloneDriveAdapter(binary=str(self.binary)).list_drive_files(approval="")
        self.assertEqual(result["status"], "blocked")

    def test_listing_writes_state_and_11d_records(self):
        from controller.rclone_drive_adapter import RcloneDriveAdapter, rclone_drive_state_path

        result = RcloneDriveAdapter(binary=str(self.binary)).list_drive_files(approval="Akkoord", max_items=5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["remote"], "gdrive")
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["records_11d"][0]["11d"]["vector"]), 11)

        state = rclone_drive_state_path()
        self.assertTrue(state.exists())
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
        self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["count"], 1)


if __name__ == "__main__":
    unittest.main()
