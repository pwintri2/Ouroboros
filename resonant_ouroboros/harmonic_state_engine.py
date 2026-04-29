"""Harmonic State Engine for signal-routing trials."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable


BASELINE_MIN_HZ = 418.0
BASELINE_MAX_HZ = 432.0
VECTOR_DIMENSIONS = 11

SYSTEM_KEYWORDS = ("system_anomaly", "anomaly", "fault", "traceback", "exception", "regression", "integrity breach", "latency spike")
ABSTRACT_KEYWORDS = ("abstract_task", "nonlinear", "temporal", "state-space", "matrix", "proof", "optimization", "constraint", "complex abstract")


@dataclass(frozen=True)
class SignalRecord:
    """Incoming record for Continuous Ambient State Ingestion."""

    record_id: str
    source: str
    title: str
    text: str
    band: str = "curious_scan"
    priority: str = "standard"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VibrationalState:
    """Tagged Harmonic Resonance output for one routed record."""

    record_id: str
    frequency_hz: float
    bandwidth: str
    route: str
    vector: tuple[float, ...]
    signal_fidelity: float
    processed_at: str
    tags: tuple[str, ...]

    def log_line(self) -> str:
        vector_head = ",".join(f"{value:.3f}" for value in self.vector[:4])
        return (
            f"{self.record_id} | route={self.route} | hz={self.frequency_hz:.3f} "
            f"| fidelity={self.signal_fidelity:.3f} | vector=[{vector_head},...] | tags={','.join(self.tags)}"
        )


class HarmonicStateEngine:
    """Routes records through baseline and elevated Harmonic Resonance bands."""

    def process(self, record: SignalRecord, *, now: datetime | None = None) -> VibrationalState:
        processed_at = (now or datetime.now(timezone.utc)).isoformat()
        vector = self._vectorize(record)
        text = f"{record.band} {record.priority} {record.title} {record.text}".lower()
        tags: list[str] = []

        if record.priority == "high" or any(keyword in text for keyword in SYSTEM_KEYWORDS):
            tags.append("system_anomaly")
            frequency = float(600 + int(vector[0] * 600))
            route = "integer_frequency"
            bandwidth = "critical"
        elif any(keyword in text for keyword in ABSTRACT_KEYWORDS):
            tags.append("abstract_task")
            frequency = float(500 + int(vector[1] * 300))
            route = "integer_frequency"
            bandwidth = "abstract"
        else:
            tags.append("baseline_418_432_hz")
            frequency = BASELINE_MIN_HZ + (BASELINE_MAX_HZ - BASELINE_MIN_HZ) * vector[2]
            route = "baseline_418_432_hz"
            bandwidth = "standard"

        fidelity = min(1.0, 0.55 + min(len(record.text), 2000) / 4000.0)
        return VibrationalState(
            record_id=record.record_id,
            frequency_hz=round(frequency, 3),
            bandwidth=bandwidth,
            route=route,
            vector=tuple(round(value, 6) for value in vector),
            signal_fidelity=round(fidelity, 6),
            processed_at=processed_at,
            tags=tuple(tags),
        )

    def process_stream(self, records: Iterable[SignalRecord], *, now: datetime | None = None) -> list[VibrationalState]:
        return [self.process(record, now=now) for record in records]

    def _vectorize(self, record: SignalRecord) -> tuple[float, ...]:
        values: list[float] = []
        base = f"{record.record_id}|{record.source}|{record.title}|{record.text}|{record.band}|{record.priority}"
        for index in range(VECTOR_DIMENSIONS):
            digest = hashlib.sha256(f"{base}|{index}".encode("utf-8", errors="ignore")).digest()
            values.append(int.from_bytes(digest[:8], "big") / float(2**64 - 1))
        return tuple(values)


def mock_record_at_432_hz() -> SignalRecord:
    return SignalRecord(
        record_id="mock-432",
        source="unit",
        title="Instruction set architecture deterministic sample",
        text="A stable baseline record about processor interfaces and implementation details.",
        band="curious_scan",
        priority="standard",
    )
