# sandbox_tests/test_dreamcycle_11d_validation.py

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.dreamcycle import DreamCycle, relative_temporal_position
from controller.stream.metadata_11d import build_11d_metadata, is_11d_complete, missing_11d_layers
from controller.stream.normalize import normalize


class TestDreamCycle(unittest.TestCase):

    def test_frequency_stays_inside_418_432_band(self):
        cycle = DreamCycle(cycle_seconds=11.0)
        for stable_seconds in (0.0, 1.0, 7.5, 123.456):
            sample = cycle.sample("seed-a", stable_seconds=stable_seconds)
            self.assertGreaterEqual(sample.hz, 418.0)
            self.assertLessEqual(sample.hz, 432.0)

    def test_fixed_seed_and_stable_seconds_are_deterministic(self):
        cycle = DreamCycle(cycle_seconds=11.0)
        first = cycle.sample("same-seed", stable_seconds=42.0)
        second = cycle.sample("same-seed", stable_seconds=42.0)
        self.assertEqual(first.relative_temporal_position, second.relative_temporal_position)
        self.assertAlmostEqual(first.hz, second.hz)

    def test_relative_temporal_position_is_normalized_string(self):
        rtp = relative_temporal_position("chunk-123")
        self.assertGreaterEqual(float(rtp), 0.0)
        self.assertLessEqual(float(rtp), 1.0)


class TestMetadata11D(unittest.TestCase):

    def test_build_11d_metadata_is_complete(self):
        item = normalize(
            {
                "title": "Wintrip stream",
                "text": "Ouroboros resonance",
                "source_type": "manual",
                "published_at": "2026-04-29T10:00:00+00:00",
            }
        )
        metadata = build_11d_metadata(
            item=item,
            resonance_score=0.75,
            importance=4.0,
            ingested_at="2026-04-29T10:00:01+00:00",
            dream_hz=418.5,
            relative_temporal_position="0.123",
        )
        self.assertTrue(is_11d_complete(metadata))
        self.assertEqual(missing_11d_layers(metadata), [])
        self.assertEqual(metadata["dimension_count"], 11)
        self.assertIn("418.500000Hz", metadata["d9_resonance_frequency"])


if __name__ == "__main__":
    unittest.main()
