# sandbox_tests/test_validation_script.py

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.dreamcycle import DreamCycle
from controller.stream.metadata_11d import build_11d_metadata
from controller.stream.normalize import normalize
from validation_script import validate_records


class TestValidationScript(unittest.TestCase):

    def _valid_record(self):
        item = normalize({"title": "A", "text": "B", "source_type": "manual"})
        sample = DreamCycle().sample(item.content_hash, stable_seconds=0.0)
        metadata = {
            "dream_hz": sample.hz,
            **build_11d_metadata(
                item=item,
                resonance_score=0.7,
                importance=4.0,
                ingested_at="2026-04-29T10:00:00+00:00",
                dream_hz=sample.hz,
                relative_temporal_position=sample.relative_temporal_position,
            ),
        }
        return {"id": item.id, "metadata": metadata}

    def test_valid_record_passes(self):
        report = validate_records([self._valid_record()])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["invalid_chunks"], 0)

    def test_missing_layer_fails(self):
        record = self._valid_record()
        del record["metadata"]["d11_field"]
        report = validate_records([record])
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("d11_field", report["issues"][0]["missing_11d_layers"])

    def test_frequency_outside_band_fails(self):
        record = self._valid_record()
        record["metadata"]["dream_hz"] = 500.0
        report = validate_records([record])
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("buiten 418-432Hz", report["issues"][0]["frequency_issue"])


if __name__ == "__main__":
    unittest.main()
