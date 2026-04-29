# controller/stream/metadata_11d.py
# WINTRIP-AGENT/1.0 — 11-dimensional Hippocampus metadata contract.

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from controller.stream.normalize import NormalizedItem


@dataclass(frozen=True)
class LayerSpec:
    key: str
    group: str
    label: str


REQUIRED_11D_LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec("d1_physical_body", "physical", "Chunk body in Hippocampus"),
    LayerSpec("d2_physical_source", "physical", "Source medium and provenance"),
    LayerSpec("d3_physical_container", "physical", "Storage container"),
    LayerSpec("d4_chronology", "chronology", "Observed or published time"),
    LayerSpec("d5_persona_actor", "persona", "Actor/persona"),
    LayerSpec("d6_persona_intent", "persona", "Intent inside OODA loop"),
    LayerSpec("d7_persona_relation", "persona", "Relation to Philip/Wintrip"),
    LayerSpec("d8_karmic_taint", "karmic_resonance", "Trust, taint and consequence"),
    LayerSpec("d9_resonance_frequency", "karmic_resonance", "DreamCycle frequency"),
    LayerSpec("d10_resonance_score", "karmic_resonance", "Resonance/importance trace"),
    LayerSpec("d11_field", "field", "Shared Ouroboros field"),
)

REQUIRED_11D_KEYS: tuple[str, ...] = tuple(layer.key for layer in REQUIRED_11D_LAYERS)


def build_11d_metadata(
    item: NormalizedItem,
    resonance_score: float,
    importance: float,
    ingested_at: str,
    dream_hz: float,
    relative_temporal_position: str,
) -> dict[str, str | int | float]:
    taint = item.taint or "local_stream"
    approval = item.approval_status or "not_required"
    return {
        "dimension_count": 11,
        "d1_physical_body": "stream_chunk",
        "d2_physical_source": item.source_type or "unknown",
        "d3_physical_container": "hippocampus_chromadb",
        "d4_chronology": item.published_at or ingested_at,
        "d5_persona_actor": "philip",
        "d6_persona_intent": "observe_orient_decide_act_reflect",
        "d7_persona_relation": "wintrip_ouroboros_stream",
        "d8_karmic_taint": f"{taint}:{approval}",
        "d9_resonance_frequency": f"{dream_hz:.6f}Hz",
        "d10_resonance_score": f"{resonance_score:.6f}:importance={importance:.1f}",
        "d11_field": f"ouroboros_field:relative_temporal_position={relative_temporal_position}",
    }


def missing_11d_layers(metadata: Mapping[str, object]) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_11D_KEYS:
        value = metadata.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
    if int_or_none(metadata.get("dimension_count")) != 11:
        missing.append("dimension_count")
    return missing


def is_11d_complete(metadata: Mapping[str, object]) -> bool:
    return not missing_11d_layers(metadata)


def int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
