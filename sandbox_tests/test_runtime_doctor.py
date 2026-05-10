import os
import tempfile
import unittest
from pathlib import Path

from controller.runtime_doctor import _check_ooda_hippocampus, load_last_smoke_result, runtime_doctor_payload, save_smoke_result


class FakeOODACollection:
    def count(self):
        return 3


class TestRuntimeDoctor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_pending = os.environ.get("WINTRIP_PENDING_APPROVAL_PATH")
        self._old_smoke = os.environ.get("WINTRIP_RUNTIME_SMOKE_RESULT_PATH")
        root = Path(self._tmp.name)
        os.environ["WINTRIP_PENDING_APPROVAL_PATH"] = str(root / "pending.json")
        os.environ["WINTRIP_RUNTIME_SMOKE_RESULT_PATH"] = str(root / "smoke.json")

    def tearDown(self):
        if self._old_pending is None:
            os.environ.pop("WINTRIP_PENDING_APPROVAL_PATH", None)
        else:
            os.environ["WINTRIP_PENDING_APPROVAL_PATH"] = self._old_pending
        if self._old_smoke is None:
            os.environ.pop("WINTRIP_RUNTIME_SMOKE_RESULT_PATH", None)
        else:
            os.environ["WINTRIP_RUNTIME_SMOKE_RESULT_PATH"] = self._old_smoke
        self._tmp.cleanup()

    def test_doctor_reports_concrete_blockers_for_unreachable_runtime(self):
        payload = runtime_doctor_payload(
            backend_url="http://127.0.0.1:9",
            preview_url="http://127.0.0.1:9",
            bridge_url="http://127.0.0.1:9",
        )

        self.assertIn(payload["status"], {"degraded", "failed"})
        self.assertIn("backend_http", payload["checks"])
        self.assertIn("web_preview", payload["checks"])
        self.assertIn("host_bridge", payload["checks"])
        self.assertTrue(payload["blockers"])
        self.assertFalse(payload["fake_success"])

    def test_last_smoke_result_is_persistent_and_redacted(self):
        save_smoke_result({"status": "success", "route": "agentic_processor", "tool": "list_files", "token": "secret"})
        result = load_last_smoke_result()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["route"], "agentic_processor")
        self.assertEqual(result["tool"], "list_files")
        self.assertFalse(result["fake_success"])

    def test_ooda_hippocampus_health_check_is_canonical(self):
        result = _check_ooda_hippocampus(collection=FakeOODACollection())

        self.assertEqual(result["status"], "online")
        self.assertEqual(result["collection"], "wintrip_ooda_dreamcycle_11d")
        self.assertEqual(result["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(result["dream_hz"]), 418.0)
        self.assertLessEqual(float(result["dream_hz"]), 432.0)
        self.assertEqual(result["missing_11d_layers"], [])
        self.assertTrue(result["scalar_metadata"])


if __name__ == "__main__":
    unittest.main()
