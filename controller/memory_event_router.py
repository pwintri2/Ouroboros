"""Redacted 11D Chroma audit records for Ouroboros trigger/action events."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


TRIGGER_ACTION_COLLECTION = "wintrip_trigger_actions_11d"
MAX_DOCUMENT_CHARS = 12_000
MAX_TEXT_CHARS = 6_000
MAX_LIST_ITEMS = 80
REDACTION_VERSION = "trigger-action-redaction-v1"
SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|bearer|token|password|passwd|secret|authorization)\s*[:=]\s*['\"]?[^'\"\s,}]+"
)
SECRET_BEARER_RE = re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+")
SECRET_KEY_MARKERS = ("key", "token", "secret", "password", "passwd", "bearer", "authorization", "cookie", "session")


@dataclass(frozen=True)
class TriggerActionRecord:
    event_id: str
    ts: str
    route: str
    trigger: str
    action: str
    status: str = "unknown"
    approval_required: bool = False
    approval_status: str = "not_required"
    source_trace: dict[str, Any] = field(default_factory=dict)
    metadata_11d: dict[str, Any] = field(default_factory=dict)
    pocket: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    payload_summary: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    redaction_version: str = REDACTION_VERSION


def record_trigger_action(
    *,
    trigger: str,
    action: str,
    route: str = "unknown",
    status: str = "unknown",
    payload: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    approval_required: bool = False,
    approval_status: str = "",
    source_trace: Mapping[str, Any] | None = None,
    metadata_11d: Mapping[str, Any] | None = None,
    pocket: Mapping[str, Any] | None = None,
    collection: Any | None = None,
) -> dict[str, Any]:
    """Build and store one redacted trigger/action record.

    The router intentionally stores compact audit data, not raw private payloads.
    Tests can inject a Chroma-like collection; production uses a dedicated local
    Chroma collection with deterministic 11D embeddings.
    """

    record = build_trigger_action_record(
        trigger=trigger,
        action=action,
        route=route,
        status=status,
        payload=payload,
        result=result,
        approval_required=approval_required,
        approval_status=approval_status,
        source_trace=source_trace,
        metadata_11d=metadata_11d,
        pocket=pocket,
    )
    document = _record_document(record)
    try:
        target = collection or _trigger_action_collection()
        target.add(
            ids=[record.event_id],
            documents=[document],
            metadatas=[_record_metadata(record)],
            embeddings=[_embedding_11d(document)],
        )
        return {
            "status": "stored",
            "stored": True,
            "event_id": record.event_id,
            "collection": _collection_name(),
            "content_hash": record.content_hash,
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "error",
            "stored": False,
            "event_id": record.event_id,
            "collection": _collection_name(),
            "reason": str(exc),
            "fake_success": False,
        }


def build_trigger_action_record(
    *,
    trigger: str,
    action: str,
    route: str = "unknown",
    status: str = "unknown",
    payload: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    approval_required: bool = False,
    approval_status: str = "",
    source_trace: Mapping[str, Any] | None = None,
    metadata_11d: Mapping[str, Any] | None = None,
    pocket: Mapping[str, Any] | None = None,
) -> TriggerActionRecord:
    ts = datetime.now(timezone.utc).isoformat()
    clean_payload = _redact(payload or {})
    clean_result = _summarize_result(_redact(result or {}))
    clean_source = _redact(source_trace or {})
    clean_pocket = _redact(pocket or {})
    clean_metadata = _metadata_11d(
        route=route,
        trigger=trigger,
        action=action,
        status=status,
        ts=ts,
        approval_required=approval_required,
        approval_status=approval_status,
        source_trace=source_trace or {},
        extra=metadata_11d or {},
    )
    draft = {
        "ts": ts,
        "route": route,
        "trigger": trigger,
        "action": action,
        "status": status,
        "approval_required": bool(approval_required),
        "approval_status": approval_status or ("required" if approval_required else "not_required"),
        "source_trace": clean_source,
        "metadata_11d": clean_metadata,
        "pocket": clean_pocket,
        "result_summary": clean_result,
        "payload_summary": clean_payload,
        "redaction_version": REDACTION_VERSION,
    }
    content_hash = hashlib.sha256(
        json.dumps(draft, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8", errors="replace")
    ).hexdigest()
    return TriggerActionRecord(
        event_id=f"trigger_action_{uuid.uuid4()}",
        ts=ts,
        route=str(route or "unknown")[:120],
        trigger=str(trigger or "unknown")[:500],
        action=str(action or "unknown")[:160],
        status=str(status or "unknown")[:80],
        approval_required=bool(approval_required),
        approval_status=str(approval_status or ("required" if approval_required else "not_required"))[:80],
        source_trace=clean_source if isinstance(clean_source, dict) else {},
        metadata_11d=clean_metadata,
        pocket=clean_pocket if isinstance(clean_pocket, dict) else {},
        result_summary=clean_result if isinstance(clean_result, dict) else {},
        payload_summary=clean_payload if isinstance(clean_payload, dict) else {},
        content_hash=content_hash,
    )


def trigger_action_status(limit: int = 8, *, collection: Any | None = None) -> dict[str, Any]:
    try:
        target = collection or _trigger_action_collection()
        count = int(target.count()) if callable(getattr(target, "count", None)) else 0
        records = target.get(limit=max(1, min(int(limit or 8), 50)), include=["metadatas"])
        return {
            "status": "online",
            "collection": _collection_name(),
            "count": count,
            "recent_event_ids": list(records.get("ids") or [])[:limit],
            "recent_metadatas": list(records.get("metadatas") or [])[:limit],
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "error", "collection": _collection_name(), "reason": str(exc), "fake_success": False}


def _trigger_action_collection() -> Any:
    from controller.chroma_runtime import get_or_create_collection

    return get_or_create_collection(name=_collection_name(), persist_dir=os.getenv("WINTRIP_DB_PATH", "wintrip_brain"))


def _collection_name() -> str:
    return str(os.getenv("WINTRIP_TRIGGER_ACTION_COLLECTION") or TRIGGER_ACTION_COLLECTION)


def _record_document(record: TriggerActionRecord) -> str:
    return json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, indent=2, default=str)[:MAX_DOCUMENT_CHARS]


def _record_metadata(record: TriggerActionRecord) -> dict[str, str | int | float | bool]:
    metadata = {
        "type": "trigger_action_record",
        "event_id": record.event_id,
        "route": record.route,
        "trigger": record.trigger[:500],
        "action": record.action,
        "status": record.status,
        "approval_required": record.approval_required,
        "approval_status": record.approval_status,
        "content_hash": record.content_hash,
        "stored_at": record.ts,
        "source": "controller.memory_event_router",
        "source_type": "trigger_action",
        "redaction_version": record.redaction_version,
        **record.metadata_11d,
    }
    metadata["type"] = "trigger_action_record"
    metadata["event_id"] = record.event_id
    metadata["content_hash"] = record.content_hash
    return _flatten_metadata(metadata)


def _metadata_11d(
    *,
    route: str,
    trigger: str,
    action: str,
    status: str,
    ts: str,
    approval_required: bool,
    approval_status: str,
    source_trace: Mapping[str, Any],
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    from controller.ooda_hippocampus import build_ooda_metadata

    session_id = str((source_trace or {}).get("session_id") or f"trigger_action:{route or 'unknown'}")[:160]
    return dict(
        build_ooda_metadata(
            phase="act",
            session_id=session_id,
            event_kind="trigger_action",
            route=route,
            status=status,
            payload={"trigger": trigger, "action": action},
            approval_required=approval_required,
            approval_status=approval_status,
            source="controller.memory_event_router",
            source_type="trigger_action",
            taint="local_audit",
            learnable=False,
            audit_only=True,
            collection_name=_collection_name(),
            ts=ts,
            extra=extra or {},
        )
    )


def _summarize_result(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return _redact(value)
    interesting = {
        key: value.get(key)
        for key in (
            "status",
            "tool",
            "action",
            "reason",
            "stderr",
            "stdout",
            "exit_code",
            "result",
            "job_id",
            "category",
            "fake_success",
        )
        if key in value
    }
    return _redact(interesting or value)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_KEY_MARKERS):
                clean[str(key)[:120]] = "[REDACTED]"
            else:
                clean[str(key)[:120]] = _redact(item)
        return clean
    if isinstance(value, list):
        return [_redact(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value[:MAX_LIST_ITEMS])
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
        if isinstance(item, (str, int, float, bool)):
            clean[str(key)] = item
        elif item is None:
            clean[str(key)] = ""
        else:
            clean[str(key)] = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)[:900]
    return clean
