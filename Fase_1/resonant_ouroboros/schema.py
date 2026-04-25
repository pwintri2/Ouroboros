"""Exact 11D hippocampus schema and vectorization helpers."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


ELEVEN_DIMENSIONS = (
    "physical_structure",
    "source_origin",
    "path_or_proprioception",
    "relative_temporal_position",
    "persona_actor",
    "intent_marker",
    "user_context_marker",
    "emotional_valence",
    "importance_score",
    "karmic_weight",
    "field_cluster_id",
)


@dataclass(frozen=True)
class Hippocampus11D:
    physical_structure: str
    source_origin: str
    path_or_proprioception: str
    relative_temporal_position: str
    persona_actor: str
    intent_marker: str
    user_context_marker: str
    emotional_valence: float
    importance_score: float
    karmic_weight: float
    field_cluster_id: str
    current_hz: float
    vibration_mood: str

    def metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = "ouroboros_11d_proto_1_1_fase_1"
        data["dimension_count"] = 11
        data["stored_at"] = datetime.now(UTC).isoformat()
        return data

    def vector(self) -> list[float]:
        """Return exactly 11 numeric dimensions for ChromaDB storage."""

        return [
            _hash_unit(self.physical_structure),
            _hash_unit(self.source_origin),
            _path_signal(self.path_or_proprioception),
            _temporal_signal(self.relative_temporal_position),
            _hash_unit(self.persona_actor),
            _hash_unit(self.intent_marker),
            _hash_unit(self.user_context_marker),
            _bounded(self.emotional_valence, -1.0, 1.0),
            _bounded(self.importance_score, 0.0, 1.0),
            _bounded(self.karmic_weight, -1.0, 1.0),
            _hash_unit(self.field_cluster_id),
        ]


def build_11d_record(
    *,
    physical_structure: str,
    source_origin: str,
    path_or_proprioception: str,
    relative_temporal_position: str,
    persona_actor: str,
    intent_marker: str,
    user_context_marker: str,
    emotional_valence: float,
    importance_score: float,
    karmic_weight: float,
    field_cluster_id: str,
    current_hz: float,
    vibration_mood: str,
) -> Hippocampus11D:
    return Hippocampus11D(
        physical_structure=physical_structure,
        source_origin=source_origin,
        path_or_proprioception=path_or_proprioception,
        relative_temporal_position=relative_temporal_position,
        persona_actor=persona_actor,
        intent_marker=intent_marker,
        user_context_marker=user_context_marker,
        emotional_valence=_bounded(emotional_valence, -1.0, 1.0),
        importance_score=_bounded(importance_score, 0.0, 1.0),
        karmic_weight=_bounded(karmic_weight, -1.0, 1.0),
        field_cluster_id=field_cluster_id,
        current_hz=round(float(current_hz), 3),
        vibration_mood=vibration_mood,
    )


def text_cluster_id(text: str, prefix: str = "field") -> str:
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def validate_11d_metadata(metadata: dict[str, Any]) -> None:
    missing = [name for name in ELEVEN_DIMENSIONS if name not in metadata]
    if missing:
        raise ValueError(f"missing 11D metadata fields: {', '.join(missing)}")
    for extra in ("current_hz", "vibration_mood"):
        if extra not in metadata:
            raise ValueError(f"missing required vibration field: {extra}")


def _hash_unit(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).digest()
    integer = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return round((integer / ((1 << 64) - 1)) * 2.0 - 1.0, 6)


def _path_signal(value: str) -> float:
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    depth = min(len(parts), 12) / 12.0
    return round((depth * 2.0) - 1.0, 6)


def _temporal_signal(value: str) -> float:
    lowered = value.lower()
    if lowered in {"now", "present", "current"}:
        return 1.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _hash_unit(value)
    age_seconds = max(0.0, (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds())
    one_year = 365.0 * 24.0 * 3600.0
    return round(1.0 - min(2.0, age_seconds / one_year), 6)


def _bounded(value: float, minimum: float, maximum: float) -> float:
    if math.isnan(float(value)):
        return minimum
    return round(max(minimum, min(maximum, float(value))), 6)
