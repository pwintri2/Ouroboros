import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHostSensoryAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.previous_bridge_url = os.environ.get("WINTRIP_RCLONE_BRIDGE_URL")
        self.tmp = tempfile.TemporaryDirectory(prefix="host-sensory-")
        self.root = Path(self.tmp.name)
        os.environ["WINTRIP_WORKSPACE"] = str(self.root)
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace
        if self.previous_bridge_url is None:
            os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)
        else:
            os.environ["WINTRIP_RCLONE_BRIDGE_URL"] = self.previous_bridge_url

    def test_snapshot_requires_approval(self):
        from controller.host_sensory_adapter import snapshot_host_sensory

        result = snapshot_host_sensory(approval="")
        self.assertEqual(result["status"], "blocked")

    def test_snapshot_writes_state_without_packet_capture(self):
        from controller.host_sensory_adapter import get_host_sensory_status, host_sensory_state_path, snapshot_host_sensory

        result = snapshot_host_sensory(
            approval="Akkoord",
            max_processes=10,
            max_flows=10,
            max_windows=10,
            max_recent=10,
        )
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["real_packet_capture"])
        self.assertFalse(result["real_forwarding"])
        self.assertEqual(len(result["record"]["11d"]["vector"]), 11)

        state = host_sensory_state_path()
        self.assertTrue(state.exists())
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
        state_data = json.loads(state.read_text(encoding="utf-8"))
        self.assertIn("process_count", state_data)

        status = get_host_sensory_status()
        self.assertEqual(status["status"], "success")
        self.assertFalse(status["real_packet_capture"])


if __name__ == "__main__":
    unittest.main()
