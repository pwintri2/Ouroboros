"""Canonical OODA DreamCycle Hippocampus facade.

This module is the single local integration point for durable OODA phase events:
418 Hz anchor, DreamCycle band sample, 11D metadata completeness and scalar
ChromaDB metadata compatibility.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from controller.stream.dreamcycle import DEFAULT_MAX_HZ, DreamCycle
from controller.stream.geometry_11d import measure_geometry_11d
from controller.stream.metadata_11d import missing_11d_layers


DREAM_ANCHOR_HZ = 418.0
DEFAULT_OODA_DREAM_COLLECTION = "wintrip_ooda_dreamcycle_11d"
SUPPORTED_OODA_PHASES = ("observe", "orient", "decide", "act", "reflect")
OODA_PHASE_INDEX = {phase: index for index, phase in enumerate(SUPPORTED_OODA_PHASES)}
REDACTION_VERSION = "ooda-hippocampus-redaction-v1"
MAX_DOCUMENT_CHARS = 12_000
MAX_TEXT_CHARS = 6_000
MAX_PAYLOAD_SUMMARY_CHARS = 900
MAX_LIST_ITEMS = 80
MAX_DICT_ITEMS = 120
SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|bearer|token|password|passwd|secret|authorization|cookie|session)\s*[:=]\s*['\"]?[^'\"\s,}]+"
)
SECRET_BEARER_RE = re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+")
SECRET_KEY_MARKERS = ("key", "token", "secret", "password", "passwd", "bearer", "authorization", "cookie")
SCALAR_TYPES = (str, int, float, bool)


def ooda_collection_name() -> str:
    """Return the local Chroma collection for canonical OODA episodic records."""

    return str(os.getenv("WINTRIP_OODA_DREAM_COLLECTION") or DEFAULT_OODA_DREAM_COLLECTION)


def build_ooda_metadata(
    *,
    phase: str,
    session_id: str,
    event_kind: str,
    route: str,
    status: str = "unknown",
    payload: Any | None = None,
    approval_required: bool = False,
    approval_status: str = "",
    source: str = "",
    source_type: str = "",
    taint: str = "local_audit",
    learnable: bool = False,
    audit_only: bool = True,
    collection_name: str | None = None,
    actor: str = "ouroboros",
    event_id: str | None = None,
    ts: str | None = None,
    content_hash: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, str | int | float | bool]:
    """Build validated scalar metadata for one canonical OODA event."""

    canonical_phase = _canonical_phase(phase)
    stored_at = ts or _utc_now()
    clean_session_id = _clean_text(session_id or f"ooda_session_{uuid.uuid4()}", limit=160)
    clean_event_kind = _clean_text(event_kind or "ooda_event", limit=120)
    clean_route = _clean_text(route or "unknown", limit=160)
    clean_status = _clean_text(status or "unknown", limit=80)
    clean_source = _clean_text(source or clean_route or "local", limit=160)
    clean_source_type = _clean_text(source_type or clean_event_kind, limit=120)
    clean_taint = _clean_text(taint or "local_audit", limit=120)
    approval = _clean_text(approval_status or ("required" if approval_required else "not_required"), limit=80)
    payload_summary = _payload_summary_text(payload)
    hash_value = content_hash or _content_hash(
        {
            "phase": canonical_phase,
            "session_id": clean_session_id,
            "event_kind": clean_event_kind,
            "route": clean_route,
            "status": clean_status,
            "payload_summary": payload_summary,
            "approval_status": approval,
            "source": clean_source,
            "source_type": clean_source_type,
            "taint": clean_taint,
        }
    )
    collection_target = collection_name or ooda_collection_name()
    sample = _canonical_dream_sample(f"{clean_session_id}|{canonical_phase}|{clean_event_kind}|{hash_value}")
    dream_hz = _clamp_dream_hz(sample.hz)
    sample_metadata = sample.metadata()
    sample_metadata["dream_hz"] = round(dream_hz, 6)
    sample_metadata["frequency_band"] = "418-432Hz"
    geometry = measure_geometry_11d(dream_hz)
    metadata: dict[str, Any] = {
        "type": "ooda_dreamcycle_11d_event",
        "event_id": event_id or f"ooda_{uuid.uuid4()}",
        "session_id": clean_session_id,
        "event_kind": clean_event_kind,
        "phase": canonical_phase,
        "phase_index": OODA_PHASE_INDEX[canonical_phase],
        "route": clean_route,
        "status": clean_status,
        "payload_summary": payload_summary,
        "content_hash": hash_value,
        "ooda_content_hash": hash_value,
        "approval_required": bool(approval_required),
        "approval_status": approval,
        "source": clean_source,
        "source_type": clean_source_type,
        "taint": clean_taint,
        "learnable": bool(learnable),
        "audit_only": bool(audit_only),
        "stored_at": stored_at,
        "redaction_version": REDACTION_VERSION,
        "dream_anchor_hz": DREAM_ANCHOR_HZ,
        "geometry_11d_available": True,
        "geometry_11d_radius": float(geometry["radius"]),
        "geometry_11d_volume": float(geometry["volume"]),
        "geometry_11d_oppervlakte": float(geometry["oppervlakte"]),
        "geometry_11d_surface_area": float(geometry["surface_area"]),
        "geometry_11d_source": "controller.stream.geometry_11d.measure_geometry_11d",
        "dimension_count": 11,
        "d1_physical_body": "canonical_ooda_event",
        "d2_physical_source": clean_source_type,
        "d3_physical_container": collection_target,
        "d4_chronology": stored_at,
        "d5_persona_actor": _clean_text(actor or "ouroboros", limit=120),
        "d6_persona_intent": f"{clean_event_kind}:{canonical_phase}",
        "d7_persona_relation": "wintrip_ooda_dreamcycle_hippocampus",
        "d8_karmic_taint": f"{clean_taint}:{approval}",
        "d9_resonance_frequency": f"{dream_hz:.6f}Hz",
        "d10_resonance_score": f"phase_index={OODA_PHASE_INDEX[canonical_phase]}:learnable={bool(learnable)}",
        "d11_field": f"ouroboros_field:session={clean_session_id}:anchor_hz={DREAM_ANCHOR_HZ:.1f}",
    }
    metadata.update(sample_metadata)
    for key, value in (extra or {}).items():
        clean_key = str(key)
        if clean_key in {
            "dimension_count",
            "d9_resonance_frequency",
            "dream_anchor_hz",
            "dream_hz",
            "frequency_band",
            "content_hash",
            "ooda_content_hash",
        }:
            continue
        if clean_key.startswith("geometry_11d_"):
            continue
        metadata[clean_key[:120]] = _redact(value)

    metadata.update(
        {
            "dimension_count": 11,
            "dream_anchor_hz": DREAM_ANCHOR_HZ,
            "dream_hz": round(dream_hz, 6),
            "frequency_band": "418-432Hz",
            "d9_resonance_frequency": f"{dream_hz:.6f}Hz",
            "geometry_11d_available": True,
            "geometry_11d_radius": float(geometry["radius"]),
            "geometry_11d_volume": float(geometry["volume"]),
            "geometry_11d_oppervlakte": float(geometry["oppervlakte"]),
            "geometry_11d_surface_area": float(geometry["surface_area"]),
        }
    )
    missing = missing_11d_layers(metadata)
    if missing:
        raise ValueError(f"canonical OODA metadata mist 11D lagen: {', '.join(missing)}")
    flattened = _flatten_metadata(metadata)
    if not scalar_metadata_compatible(flattened):
        raise ValueError("canonical OODA metadata bevat niet-scalar Chroma metadata")
    return flattened


def build_ooda_record(**kwargs: Any) -> dict[str, Any]:
    """Build a canonical ChromaDB add payload without touching ChromaDB."""

    metadata = build_ooda_metadata(**kwargs)
    document_payload = {
        "event_id": metadata["event_id"],
        "session_id": metadata["session_id"],
        "event_kind": metadata["event_kind"],
        "phase": metadata["phase"],
        "phase_index": metadata["phase_index"],
        "route": metadata["route"],
        "status": metadata["status"],
        "payload_summary": metadata["payload_summary"],
        "content_hash": metadata["content_hash"],
        "dream_anchor_hz": metadata["dream_anchor_hz"],
        "dream_hz": metadata["dream_hz"],
        "approval_status": metadata["approval_status"],
        "source": metadata["source"],
        "source_type": metadata["source_type"],
        "taint": metadata["taint"],
        "learnable": metadata["learnable"],
        "audit_only": metadata["audit_only"],
        "metadata_11d": {key: metadata[key] for key in metadata if key.startswith("d") or key == "dimension_count"},
    }
    document = json.dumps(document_payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)[:MAX_DOCUMENT_CHARS]
    return {
        "event_id": str(metadata["event_id"]),
        "document": document,
        "metadata": metadata,
        "embedding": _embedding_11d(document),
    }


def record_ooda_event(*, collection: Any | None = None, **kwargs: Any) -> dict[str, Any]:
    """Store one canonical OODA event in the local OODA DreamCycle collection."""

    try:
        record = build_ooda_record(**kwargs)
        target = collection or _ooda_collection()
        target.add(
            ids=[record["event_id"]],
            documents=[record["document"]],
            metadatas=[record["metadata"]],
            embeddings=[record["embedding"]],
        )
        return {
            "status": "stored",
            "stored": True,
            "event_id": record["event_id"],
            "collection": ooda_collection_name(),
            "content_hash": record["metadata"]["content_hash"],
            "phase": record["metadata"]["phase"],
            "session_id": record["metadata"]["session_id"],
            "dream_anchor_hz": DREAM_ANCHOR_HZ,
            "dream_hz": record["metadata"]["dream_hz"],
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "error",
            "stored": False,
            "collection": ooda_collection_name(),
            "reason": str(exc),
            "dream_anchor_hz": DREAM_ANCHOR_HZ,
            "fake_success": False,
        }


def ooda_hippocampus_status(*, collection: Any | None = None) -> dict[str, Any]:
    """Local health probe for canonical OODA DreamCycle Hippocampus wiring."""

    try:
        probe = build_ooda_record(
            phase="observe",
            session_id="runtime_doctor_ooda",
            event_kind="runtime_doctor_probe",
            route="runtime_doctor",
            status="probe",
            payload={"check": "ooda_hippocampus"},
            source="controller.runtime_doctor",
            source_type="runtime_doctor",
            taint="local_health_probe",
            learnable=False,
            audit_only=True,
        )
        metadata = probe["metadata"]
        missing = missing_11d_layers(metadata)
        scalar = scalar_metadata_compatible(metadata)
        target = collection or _ooda_collection()
        count = int(target.count()) if callable(getattr(target, "count", None)) else 0
        ok = not missing and scalar and float(metadata["dream_anchor_hz"]) == DREAM_ANCHOR_HZ and 418.0 <= float(metadata["dream_hz"]) <= 432.0
        return {
            "status": "online" if ok else "failed",
            "reason": "canonical OODA DreamCycle Hippocampus contract valid" if ok else "canonical OODA metadata validation failed",
            "collection": ooda_collection_name(),
            "count": count,
            "dream_anchor_hz": DREAM_ANCHOR_HZ,
            "dream_hz": metadata["dream_hz"],
            "frequency_band": metadata["frequency_band"],
            "supported_phases": list(SUPPORTED_OODA_PHASES),
            "missing_11d_layers": missing,
            "scalar_metadata": scalar,
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "collection": ooda_collection_name(),
            "dream_anchor_hz": DREAM_ANCHOR_HZ,
            "fake_success": False,
        }


def scalar_metadata_compatible(metadata: Mapping[str, Any]) -> bool:
    return all(isinstance(value, SCALAR_TYPES) or value is None for value in metadata.values())


def _ooda_collection() -> Any:
    from controller.chroma_runtime import get_or_create_collection

    return get_or_create_collection(name=ooda_collection_name(), persist_dir=os.getenv("WINTRIP_DB_PATH", "wintrip_brain"))


def _canonical_phase(phase: str) -> str:
    value = str(phase or "").strip().lower()
    if value not in OODA_PHASE_INDEX:
        raise ValueError(f"unsupported OODA phase: {phase!r}")
    return value


def _canonical_dream_sample(seed: object):
    return DreamCycle(band_min_hz=DREAM_ANCHOR_HZ, band_max_hz=DEFAULT_MAX_HZ).sample(seed)


def _clamp_dream_hz(value: float) -> float:
    return max(DREAM_ANCHOR_HZ, min(float(DEFAULT_MAX_HZ), float(value)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8", errors="replace")).hexdigest()


def _payload_summary_text(payload: Any) -> str:
    clean = _redact(payload if payload is not None else {})
    return json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)[:MAX_PAYLOAD_SUMMARY_CHARS]


def _clean_text(value: Any, *, limit: int) -> str:
    return str(_redact(value) if value is not None else "").replace("\x00", " ").strip()[:limit]


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_DICT_ITEMS:
                clean["__truncated__"] = True
                break
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_KEY_MARKERS):
                clean[str(key)[:120]] = "[REDACTED]"
            else:
                clean[str(key)[:120]] = _redact(item)
        return clean
    if isinstance(value, list):
        return [_redact(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, tuple):
        return [_redact(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, str):
        text = SECRET_BEARER_RE.sub("authorization: [REDACTED]", value)
        text = SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
        return text[:MAX_TEXT_CHARS]
    return value


def _embedding_11d(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    values: list[float] = []
    for index in range(11):
        raw = digest[index * 2] * 256 + digest[index * 2 + 1]
        values.append(round((raw / 65535.0) * 2.0 - 1.0, 6))
    return values


def _flatten_metadata(value: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    clean: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        if isinstance(item, SCALAR_TYPES):
            clean[str(key)] = item
        elif item is None:
            clean[str(key)] = ""
        else:
            clean[str(key)] = json.dumps(_redact(item), ensure_ascii=False, sort_keys=True, default=str)[:MAX_PAYLOAD_SUMMARY_CHARS]
    return clean
