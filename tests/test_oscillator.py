import random

from resonant_ouroboros.oscillator import HertzOscillator


def test_base_wave_stays_in_418_432_band_without_spikes():
    oscillator = HertzOscillator(spike_probability=0.0)
    values = [oscillator.sample(oscillator._started_at + second) for second in range(60)]
    assert min(values) >= 418.0
    assert max(values) <= 432.0


def test_creative_spike_reaches_600_1200_band():
    oscillator = HertzOscillator(spike_probability=1.0, rng=random.Random(3))
    hz = oscillator.sample()
    behavior = oscillator.behavior_for_hz(hz)
    assert behavior.mood == "creative_spike"
    assert behavior.curiosity > 1.0


def test_low_frequency_behavior_is_deep_read():
    oscillator = HertzOscillator(spike_probability=0.0)
    behavior = oscillator.behavior_for_hz(418.0)
    assert behavior.mood == "deep_read"
    assert behavior.link_jump_probability < 0.1


def test_modulation_state_exposes_hz_temperature_and_curiosity():
    oscillator = HertzOscillator(spike_probability=0.0)
    state = oscillator.modulation_state()
    assert state.current_hz >= 418.0
    assert state.temperature_modifier >= 0.0
    assert state.curiosity_factor >= 0.0


def test_force_spike_enters_creative_spike_band():
    oscillator = HertzOscillator(spike_probability=0.0)
    hz = oscillator.force_spike(777.0)
    behavior = oscillator.behavior_for_hz(hz)
    assert hz >= 600.0
    assert behavior.mood == "creative_spike"
