import random
import unittest

from resonant_ouroboros.oscillator import HertzOscillator


class HertzOscillatorTests(unittest.TestCase):
    def test_base_wave_stays_in_418_432_band_without_spikes(self):
        oscillator = HertzOscillator(spike_probability=0.0)
        values = [oscillator.sample(now=oscillator._started_at + second) for second in range(0, 48)]
        self.assertGreaterEqual(min(values), 418.0)
        self.assertLessEqual(max(values), 432.0)

    def test_creative_spike_reaches_600_1200_band(self):
        oscillator = HertzOscillator(spike_probability=1.0, rng=random.Random(7))
        hz = oscillator.sample(now=oscillator._started_at)
        self.assertGreaterEqual(hz, 600.0)
        self.assertLessEqual(hz, 1200.0)
        behavior = oscillator.behavior_for_hz(hz)
        self.assertEqual(behavior.mood, "creative_spike")
        self.assertGreater(behavior.curiosity, 0.75)

    def test_low_frequency_behavior_is_deep_read(self):
        oscillator = HertzOscillator(spike_probability=0.0)
        behavior = oscillator.behavior_for_hz(419.0)
        self.assertEqual(behavior.mood, "deep_read")
        self.assertLess(behavior.link_jump_probability, 0.2)


if __name__ == "__main__":
    unittest.main()
