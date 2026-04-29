"""512MB 11D quantum memory body for Resonant Ouroboros."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - Docker/runtime requirements install numpy.
    np = None  # type: ignore[assignment]


QUANTUM_MEMORY_SCHEMA_VERSION = "ouroboros_11d_quantum_memory_body_proto_1"
DEFAULT_QUANTUM_MEMORY_MB = 512
LOCAL_TEST_QUANTUM_MEMORY_MB = 8
VISUAL_SAMPLE_COUNT = 32


def default_quantum_body_path() -> Path:
    if Path("/workspace").exists():
        return Path("/workspace/data/ouroboros_quantum_body.json")
    return Path("data/ouroboros_quantum_body.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_size_mb(size_mb: int | float | str | None) -> int:
    try:
        value = int(float(size_mb)) if size_mb is not None else DEFAULT_QUANTUM_MEMORY_MB
    except (TypeError, ValueError):
        value = DEFAULT_QUANTUM_MEMORY_MB
    return max(1, min(value, 2048))


def _seed_from_position(quantum_position: Any) -> int:
    if np is None:
        raise RuntimeError("numpy is required to allocate the 11D quantum memory body")
    position = np.asarray(quantum_position, dtype=np.float64)
    if position.shape != (11,):
        raise ValueError("quantum_position must contain exactly 11 numeric dimensions")
    digest = hashlib.sha256(position.tobytes()).hexdigest()
    return int(digest, 16) % (2**32)


def allocate_11d_quantum_memory(quantum_position: Any, size_mb: int = DEFAULT_QUANTUM_MEMORY_MB):
    """Allocate the Ouroboros memory body from an 11D position.

    The 11D position is converted to float64 bytes, hashed with SHA256, and the
    resulting 32-bit seed initializes a numpy RNG. The allocated float32 buffer
    therefore has a deterministic initial state for a given 11D body position.
    """

    if np is None:
        raise RuntimeError("numpy is required to allocate the 11D quantum memory body")
    seed = _seed_from_position(quantum_position)
    slot_count = (_bounded_size_mb(size_mb) * 1024 * 1024) // np.dtype(np.float32).itemsize
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, size=slot_count).astype(np.float32)


def _new_quantum_position():
    if np is None:
        raise RuntimeError("numpy is required to create an 11D quantum position")
    return np.random.default_rng().uniform(-1.0, 1.0, size=11).astype(np.float64)


def _load_or_create_position(path: Path):
    if np is None:
        raise RuntimeError("numpy is required to load the 11D quantum body")
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            position = np.asarray(payload.get("quantum_position"), dtype=np.float64)
            if position.shape == (11,):
                return position
        except Exception:
            pass
    position = _new_quantum_position()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": QUANTUM_MEMORY_SCHEMA_VERSION,
                "created_at": _utc_now(),
                "quantum_position": [round(float(value), 12) for value in position.tolist()],
                "seed": _seed_from_position(position),
                "meaning": "11D quantum_position seed for the 512MB physical/digital Ouroboros body.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return position


@dataclass
class QuantumMemoryBody:
    """Living in-memory 11D body where the frequency stream is written."""

    quantum_position: Any
    size_mb: int = DEFAULT_QUANTUM_MEMORY_MB
    body_path: Path | None = None
    memory: Any = field(init=False, repr=False)
    seed: int = field(init=False)
    allocated: bool = field(init=False, default=False)
    allocation_error: str | None = field(init=False, default=None)
    write_head: int = field(init=False, default=0)
    pulse_count: int = field(init=False, default=0)
    last_frequency_hz: float | None = field(init=False, default=None)
    last_mood: str | None = field(init=False, default=None)
    last_visualization: list[dict[str, float]] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.size_mb = _bounded_size_mb(self.size_mb)
        try:
            self.seed = _seed_from_position(self.quantum_position)
            self.memory = allocate_11d_quantum_memory(self.quantum_position, self.size_mb)
            self.allocated = True
        except Exception as exc:
            self.seed = 0
            self.memory = None
            self.allocated = False
            self.allocation_error = str(exc)

    @classmethod
    def from_env(cls) -> "QuantumMemoryBody":
        raw_size = os.getenv("OUROBOROS_QUANTUM_MEMORY_MB")
        if raw_size is None and not Path("/workspace").exists():
            raw_size = str(LOCAL_TEST_QUANTUM_MEMORY_MB)
        size_mb = _bounded_size_mb(raw_size)
        body_path = Path(os.getenv("OUROBOROS_QUANTUM_BODY_PATH", str(default_quantum_body_path())))
        try:
            position = _load_or_create_position(body_path)
        except Exception:
            position = [0.0] * 11
        return cls(position, size_mb=size_mb, body_path=body_path)

    def pulse(self, hz: float | None, mood: str | None = None) -> dict[str, Any]:
        """Write the current frequency into the allocated body and return status."""

        if not self.allocated or np is None:
            return self.status(hz=hz, mood=mood)
        frequency = float(hz or 425.0)
        self.last_frequency_hz = frequency
        self.last_mood = mood or "unknown"
        slot_count = int(self.memory.size)
        span = max(VISUAL_SAMPLE_COUNT, min(4096, slot_count))
        start = self.write_head % max(1, slot_count - span)
        end = start + span
        index = np.arange(span, dtype=np.float32)
        band_gain = 0.44 if frequency >= 600.0 or mood == "creative_spike" else 0.16
        phase = (self.pulse_count % 512) / 512.0
        wave = np.sin(((index / max(1.0, span - 1.0)) + phase) * math.tau * (frequency / 432.0))
        wave = (wave * band_gain).astype(np.float32)
        self.memory[start:end] = np.clip((self.memory[start:end] * 0.965) + wave, -1.0, 1.0)
        stride = max(1, span // VISUAL_SAMPLE_COUNT)
        sample = self.memory[start:end:stride][:VISUAL_SAMPLE_COUNT]
        self.last_visualization = [
            {
                "slot": round(float((start + (idx * stride)) / max(1, slot_count)), 6),
                "amplitude": round(float(value), 4),
            }
            for idx, value in enumerate(sample)
        ]
        self.write_head = (end + int(abs(frequency) * 17)) % slot_count
        self.pulse_count += 1
        return self.status(hz=frequency, mood=mood)

    def status(self, hz: float | None = None, mood: str | None = None) -> dict[str, Any]:
        frequency = float(hz) if hz is not None else self.last_frequency_hz
        band = "creative_spike" if frequency is not None and frequency >= 600.0 else "baseline_418_432"
        nbytes = int(getattr(self.memory, "nbytes", 0) or 0)
        slot_count = int(getattr(self.memory, "size", 0) or 0)
        write_head_ratio = round(self.write_head / max(1, slot_count), 6)
        return {
            "schema_version": QUANTUM_MEMORY_SCHEMA_VERSION,
            "allocated": self.allocated,
            "allocation_error": self.allocation_error,
            "body_label": f"{self.size_mb}MB physical/digital body",
            "size_mb": self.size_mb,
            "allocated_bytes": nbytes,
            "dtype": "float32",
            "slot_count": slot_count,
            "quantum_position": [
                round(float(value), 6)
                for value in (self.quantum_position.tolist() if hasattr(self.quantum_position, "tolist") else self.quantum_position)
            ],
            "seed": self.seed,
            "seed_source": "sha256(float64_bytes(11D quantum_position))",
            "frequency_hz": frequency,
            "frequency_band": band,
            "baseline_hz": "418-432",
            "mood": mood or self.last_mood,
            "pulse_count": self.pulse_count,
            "write_head_ratio": write_head_ratio,
            "write_head_mb": round(write_head_ratio * max(1, self.size_mb), 3),
            "visualization": self.last_visualization,
            "updated_at": _utc_now(),
            "meaning": (
                "The oscillator writes baseline 418-432 Hz waves and creative spikes directly "
                "into this allocated 11D-seeded numpy memory buffer."
            ),
        }
