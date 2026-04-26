"""Exact 11D hippocampus schema and vectorization helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
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


def _hash_unit(text: str) -> float:
    digest = hashlib.sha256((text or "").encode("utf-8", errors="ignore")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) / float(2**64 - 1)


def _bounded(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


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
        data["stored_at"] = datetime.now(timezone.utc).isoformat()
        return data

    def vector(self) -> list[float]:
        """Return exactly 11 numeric dimensions for ChromaDB storage."""

        vector = [
            _hash_unit(self.physical_structure),
            _hash_unit(self.source_origin),
            _hash_unit(self.path_or_proprioception),
            _hash_unit(self.relative_temporal_position),
            _hash_unit(self.persona_actor),
            _hash_unit(self.intent_marker),
            _hash_unit(self.user_context_marker),
            _bounded((float(self.emotional_valence) + 1.0) / 2.0),
            _bounded(float(self.importance_score)),
            _bounded(float(self.karmic_weight)),
            _hash_unit(self.field_cluster_id),
        ]
        return [round(value, 6) for value in vector]


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
        emotional_valence=float(emotional_valence),
        importance_score=float(importance_score),
        karmic_weight=float(karmic_weight),
        field_cluster_id=field_cluster_id,
        current_hz=float(current_hz),
        vibration_mood=vibration_mood,
    )


def text_cluster_id(text: str, prefix: str = "field") -> str:
    digest = hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def validate_11d_metadata(metadata: dict[str, Any]) -> None:
    missing = [name for name in ELEVEN_DIMENSIONS if name not in metadata]
    if missing:
        raise ValueError(f"missing 11D metadata fields: {', '.join(missing)}")
    vibration_missing = [name for name in ("current_hz", "vibration_mood") if name not in metadata]
    if vibration_missing:
        raise ValueError(f"missing required vibration field: {', '.join(vibration_missing)}")
    if int(metadata.get("dimension_count", 11)) != 11:
        raise ValueError("dimension_count must be 11")
