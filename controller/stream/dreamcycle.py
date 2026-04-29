# controller/stream/dreamcycle.py
# WINTRIP-AGENT/1.0 — internal oscillator decoupled from wall-clock time.

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass


DEFAULT_MIN_HZ = 418.0
DEFAULT_MAX_HZ = 432.0
DEFAULT_CYCLE_SECONDS = 11.0


@dataclass(frozen=True)
class DreamCycleSample:
    relative_temporal_position: str
    stable_seconds: float
    phase: float
    hz: float
    band_min_hz: float
    band_max_hz: float

    def metadata(self) -> dict[str, str | float]:
        return {
            "relative_temporal_position": self.relative_temporal_position,
            "dreamcycle_stable_seconds": round(self.stable_seconds, 6),
            "dreamcycle_phase": round(self.phase, 6),
            "dream_hz": round(self.hz, 6),
            "frequency_band": f"{self.band_min_hz:.0f}-{self.band_max_hz:.0f}Hz",
        }


class RelativeTemporalPositionEngine:
    """Maps an event key into a deterministic 0..1 position inside the cycle."""

    @staticmethod
    def position(seed: object) -> str:
        digest = hashlib.sha256(str(seed or "wintrip").encode("utf-8", errors="replace")).hexdigest()
        as_int = int(digest[:16], 16)
        normalized = as_int / float(0xFFFFFFFFFFFFFFFF)
        return f"{normalized:.12f}"


def relative_temporal_position(seed: object) -> str:
    return RelativeTemporalPositionEngine.position(seed)


class DreamCycle:
    """
    Oscillator for the Ouroboros DreamCycle.

    It uses time.monotonic(), not wall-clock time, so browser/system clock changes
    do not rewrite the internal temporal phase.
    """

    def __init__(
        self,
        band_min_hz: float = DEFAULT_MIN_HZ,
        band_max_hz: float = DEFAULT_MAX_HZ,
        cycle_seconds: float = DEFAULT_CYCLE_SECONDS,
    ):
        self.band_min_hz = float(band_min_hz)
        self.band_max_hz = float(band_max_hz)
        self.cycle_seconds = max(0.1, float(cycle_seconds))
        if self.band_max_hz <= self.band_min_hz:
            raise ValueError("DreamCycle band_max_hz moet groter zijn dan band_min_hz.")

    @classmethod
    def from_env(cls) -> "DreamCycle":
        return cls(
            band_min_hz=_env_float("WINTRIP_DREAM_MIN_HZ", DEFAULT_MIN_HZ),
            band_max_hz=_env_float("WINTRIP_DREAM_MAX_HZ", DEFAULT_MAX_HZ),
            cycle_seconds=_env_float("WINTRIP_DREAMCYCLE_SECONDS", DEFAULT_CYCLE_SECONDS),
        )

    def stable_seconds(self) -> float:
        return time.monotonic()

    def sample(self, seed: object, stable_seconds: float | None = None) -> DreamCycleSample:
        rtp = relative_temporal_position(seed)
        stable = self.stable_seconds() if stable_seconds is None else float(stable_seconds)
        phase_offset = float(rtp)
        phase = ((stable / self.cycle_seconds) + phase_offset) % 1.0
        wave = (math.sin(phase * math.tau) + 1.0) / 2.0
        hz = self.band_min_hz + wave * (self.band_max_hz - self.band_min_hz)
        return DreamCycleSample(
            relative_temporal_position=rtp,
            stable_seconds=stable,
            phase=phase,
            hz=hz,
            band_min_hz=self.band_min_hz,
            band_max_hz=self.band_max_hz,
        )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return float(default)
