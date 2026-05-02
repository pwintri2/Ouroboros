import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class Test11DPocketEcosystemAugmentation(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="stream-overlay-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_streaming_status_exposes_ecosystem_overlay(self):
        from controller.streaming_consciousness_adapter import get_streaming_status

        status = get_streaming_status()
        self.assertIn("ecosystem_overlay", status)
        overlay = status["ecosystem_overlay"]
        self.assertEqual(overlay["status"], "available")
        self.assertIn("os_state", overlay["layers"])
        self.assertIn("crawler_state", overlay["layers"])
        self.assertIn("cloud_state", overlay["layers"])
        self.assertEqual(status["feature_count"], 11)


if __name__ == "__main__":
    unittest.main()
