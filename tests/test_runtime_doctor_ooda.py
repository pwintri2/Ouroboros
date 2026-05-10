import unittest

from controller.runtime_doctor import _check_ooda_hippocampus


class FakeCollection:
    def count(self):
        return 3


class TestRuntimeDoctorOoda(unittest.TestCase):
    def test_runtime_doctor_ooda_health_check_is_local_and_canonical(self):
        result = _check_ooda_hippocampus(collection=FakeCollection())

        self.assertEqual(result["status"], "online")
        self.assertEqual(result["collection"], "wintrip_ooda_dreamcycle_11d")
        self.assertEqual(result["dream_anchor_hz"], 418.0)
        self.assertGreaterEqual(float(result["dream_hz"]), 418.0)
        self.assertLessEqual(float(result["dream_hz"]), 432.0)
        self.assertEqual(result["frequency_band"], "418-432Hz")
        self.assertEqual(result["missing_11d_layers"], [])
        self.assertTrue(result["scalar_metadata"])
        self.assertEqual(result["count"], 3)


if __name__ == "__main__":
    unittest.main()
