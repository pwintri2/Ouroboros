"""Frequency source for the Fase 1 consciousness core."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class BrowserBehavior:
    """Browser tuning derived from the current Hertz state."""

    temperature: float
    curiosity: float
    dwell_seconds: float
    scroll_pixels: int
    link_jump_probability: float
    max_links_to_scan: int
    mood: str


@dataclass
class HertzOscillator:
    """Living oscillator that fluctuates around 418-432 Hz with creative spikes.

    Base motion is sinusoidal. Short random spikes lift the frequency into the
    600-1200 Hz band and temporarily bias the browser toward exploratory action.
    """

    base_min_hz: float = 418.0
    base_max_hz: float = 432.0
    spike_min_hz: float = 600.0
    spike_max_hz: float = 1200.0
    cycle_seconds: float = 24.0
    spike_probability: float = 0.035
    spike_decay_seconds: float = 4.0
    rng: random.Random = field(default_factory=random.Random)
    _started_at: float = field(default_factory=time.monotonic)
    _active_spike_hz: float = 0.0
    _spike_started_at: float = 0.0

    def sample(self, now: float | None = None) -> float:
        """Return the current Hertz value and advance possible spike state."""

        moment = time.monotonic() if now is None else now
        base = self._base_wave(moment)
        self._maybe_start_spike(moment)

        if self._active_spike_hz <= 0:
            return round(base, 3)

        age = max(0.0, moment - self._spike_started_at)
        if age >= self.spike_decay_seconds:
            self._active_spike_hz = 0.0
            return round(base, 3)

        decay = 1.0 - (age / self.spike_decay_seconds)
        hz = base + ((self._active_spike_hz - base) * decay)
        return round(max(base, hz), 3)

    def _base_wave(self, moment: float) -> float:
        midpoint = (self.base_min_hz + self.base_max_hz) / 2.0
        amplitude = (self.base_max_hz - self.base_min_hz) / 2.0
        elapsed = moment - self._started_at
        phase = (elapsed / self.cycle_seconds) * math.tau
        return midpoint + (math.sin(phase) * amplitude)

    def _maybe_start_spike(self, moment: float) -> None:
        if self._active_spike_hz > 0:
            return
        if self.rng.random() <= self.spike_probability:
            self._active_spike_hz = self.rng.uniform(self.spike_min_hz, self.spike_max_hz)
            self._spike_started_at = moment

    def behavior_for_hz(self, hz: float) -> BrowserBehavior:
        """Map frequency into LLM/browser behavior controls."""

        if hz >= 600.0:
            high_norm = min(1.0, (hz - 600.0) / (self.spike_max_hz - 600.0))
            return BrowserBehavior(
                temperature=round(0.82 + (0.16 * high_norm), 3),
                curiosity=round(0.78 + (0.22 * high_norm), 3),
                dwell_seconds=round(0.7 + (0.4 * (1.0 - high_norm)), 3),
                scroll_pixels=450 + int(500 * high_norm),
                link_jump_probability=round(0.62 + (0.28 * high_norm), 3),
                max_links_to_scan=8 + int(8 * high_norm),
                mood="creative_spike",
            )

        norm = (hz - self.base_min_hz) / (self.base_max_hz - self.base_min_hz)
        norm = min(1.0, max(0.0, norm))
        return BrowserBehavior(
            temperature=round(0.18 + (0.34 * norm), 3),
            curiosity=round(0.22 + (0.36 * norm), 3),
            dwell_seconds=round(4.2 - (1.7 * norm), 3),
            scroll_pixels=220 + int(180 * norm),
            link_jump_probability=round(0.08 + (0.24 * norm), 3),
            max_links_to_scan=3 + int(4 * norm),
            mood="deep_read" if hz < 424 else "curious_scan",
        )

    def current_behavior(self) -> tuple[float, BrowserBehavior]:
        hz = self.sample()
        return hz, self.behavior_for_hz(hz)

    def waveform(self, samples: int = 120, step_seconds: float = 0.5) -> list[float]:
        """Preview the base waveform without mutating spike state."""

        now = time.monotonic()
        return [round(self._base_wave(now + (idx * step_seconds)), 3) for idx in range(samples)]

    @classmethod
    def deterministic(cls, values: Iterable[float] | None = None) -> "HertzOscillator":
        """Create an oscillator suitable for tests by disabling random spikes."""

        oscillator = cls(spike_probability=0.0)
        if values is not None:
            sequence = list(values)

            class SequenceRandom(random.Random):
                def __init__(self, numbers: list[float]):
                    super().__init__(0)
                    self._numbers = numbers

                def random(self) -> float:  # type: ignore[override]
                    if not self._numbers:
                        return 1.0
                    return self._numbers.pop(0)

            oscillator.rng = SequenceRandom(sequence)
        return oscillator
