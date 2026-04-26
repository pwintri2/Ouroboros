"""Frequency source for the Fase 1 signal-processing core."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
import time


@dataclass(frozen=True)
class BrowserBehavior:
    """Browser tuning derived from the current Hertz state."""

    temperature: float
    curiosity: float
    dwell_seconds: float
    scroll_pixels: int
    link_jump_probability: float
    max_links_to_scan: int
    mood: str


@dataclass(frozen=True)
class OscillatorState:
    """Current Hertz value and behavior modifiers exposed to orchestration."""

    current_hz: float
    temperature_modifier: float
    curiosity_factor: float
    mood: str


@dataclass
class HertzOscillator:
    """Living oscillator around 418-432 Hz with occasional creative spikes."""

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

    @property
    def current_hz(self) -> float:
        """Expose the current Hertz sample for dashboards and orchestration."""

        return self.sample()

    @property
    def temperature_modifier(self) -> float:
        """Expose the LLM temperature modifier derived from current Hertz."""

        return self.behavior_for_hz(self.current_hz).temperature

    @property
    def curiosity_factor(self) -> float:
        """Expose the browser exploration factor derived from current Hertz."""

        return self.behavior_for_hz(self.current_hz).curiosity

    def _base_wave(self, now: float) -> float:
        midpoint = (self.base_min_hz + self.base_max_hz) / 2.0
        amplitude = (self.base_max_hz - self.base_min_hz) / 2.0
        elapsed = now - self._started_at
        phase = (elapsed / max(self.cycle_seconds, 0.1)) * math.tau
        return midpoint + amplitude * math.sin(phase)

    def _maybe_start_spike(self, now: float) -> None:
        if self._active_spike_hz:
            return
        if self.rng.random() < self.spike_probability:
            self._active_spike_hz = self.rng.uniform(self.spike_min_hz, self.spike_max_hz)
            self._spike_started_at = now

    def sample(self, now: float | None = None) -> float:
        """Return the current Hertz value and advance possible spike state."""

        moment = now if now is not None else time.monotonic()
        base = self._base_wave(moment)
        self._maybe_start_spike(moment)

        if not self._active_spike_hz:
            return round(max(self.base_min_hz, min(self.base_max_hz, base)), 3)

        elapsed = moment - self._spike_started_at
        if elapsed >= self.spike_decay_seconds:
            self._active_spike_hz = 0.0
            return round(max(self.base_min_hz, min(self.base_max_hz, base)), 3)

        decay = 1.0 - (elapsed / max(self.spike_decay_seconds, 0.1))
        spike = base + (self._active_spike_hz - base) * decay
        return round(max(self.base_min_hz, spike), 3)

    def behavior_for_hz(self, hz: float) -> BrowserBehavior:
        if hz >= self.spike_min_hz:
            return BrowserBehavior(
                temperature=0.95,
                curiosity=1.8,
                dwell_seconds=0.4,
                scroll_pixels=950,
                link_jump_probability=0.75,
                max_links_to_scan=6,
                mood="creative_spike",
            )
        if hz <= 420.0:
            return BrowserBehavior(
                temperature=0.25,
                curiosity=0.45,
                dwell_seconds=2.2,
                scroll_pixels=320,
                link_jump_probability=0.05,
                max_links_to_scan=1,
                mood="deep_read",
            )
        return BrowserBehavior(
            temperature=0.55,
            curiosity=1.0,
            dwell_seconds=1.0,
            scroll_pixels=620,
            link_jump_probability=0.25,
            max_links_to_scan=3,
            mood="curious_scan",
        )

    def current_behavior(self) -> tuple[float, BrowserBehavior]:
        hz = self.sample()
        return hz, self.behavior_for_hz(hz)

    def force_spike(self, hz: float | None = None, now: float | None = None) -> float:
        """Force an immediate creative spike and return the current sample."""

        moment = now if now is not None else time.monotonic()
        target = hz if hz is not None else self.rng.uniform(self.spike_min_hz, self.spike_max_hz)
        self._active_spike_hz = max(self.spike_min_hz, min(self.spike_max_hz, target))
        self._spike_started_at = moment
        return self.sample(moment)

    def modulation_state(self, now: float | None = None) -> OscillatorState:
        hz = self.sample(now=now)
        behavior = self.behavior_for_hz(hz)
        return OscillatorState(
            current_hz=hz,
            temperature_modifier=behavior.temperature,
            curiosity_factor=behavior.curiosity,
            mood=behavior.mood,
        )

    def waveform(self, samples: int = 120, step_seconds: float = 0.5) -> list[float]:
        start = time.monotonic()
        return [self.sample(start + (index * step_seconds)) for index in range(max(0, samples))]
