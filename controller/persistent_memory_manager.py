"""Bounded ChromaDB memory helpers for agentic Ouroboros sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping


DEFAULT_AGENTIC_SESSION_COLLECTION = "wintrip_agentic_sessions_11d"
DEFAULT_AGENTIC_MEMORY_MAX = 300
SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|bearer|token|password|passwd|secret|authorization)\s*[:=]\s*['\"]?[^'\"\s,}]+"
)


def save_agentic_session(session: Mapping[str, Any], *, collection: Any | None = None) -> dict[str, Any]:
    """Store one redacted agentic run as a single bounded 11D ChromaDB memory."""

    payload = _redact(session)
    goal = str(payload.get("goal") or payload.get("prompt") or "agentic_session")
    status = str(payload.get("status") or "unknown")
    document = _compact_document(payload)
    digest = hashlib.sha256(document.encode("utf-8", errors="replace")).hexdigest()
    item_id = str(payload.get("session_id") or f"agentic_session_{uuid.uuid4()}")
    metadata = _flatten_metadata(
        {
            "type": "agentic_session_11d",
            "status": status,
            "goal": goal[:500],
            "route": str(payload.get("route") or "agentic_processor"),
            "dimension_count": 11,
            "content_hash": digest,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "step_count": len(payload.get("steps") or payload.get("step_results") or []),
            "approval_required": bool(payload.get("approval_required")),
            "source": "controller.agentic_processor",
            "source_type": "agentic_session",
        }
    )
    try:
        target = collection or _agentic_collection()
        _enforce_memory_cap(target, max_items=_agentic_memory_max() - 1)
        target.add(
            ids=[item_id],
            documents=[document],
            metadatas=[metadata],
            embeddings=[_embedding_11d(document)],
        )
        _enforce_memory_cap(target, max_items=_agentic_memory_max())
        return {
            "status": "stored",
            "stored": True,
            "collection": _agentic_collection_name(),
            "item_id": item_id,
            "content_hash": digest,
            "max_items": _agentic_memory_max(),
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "error",
            "stored": False,
            "collection": _agentic_collection_name(),
            "reason": str(exc),
            "fake_success": False,
        }


def _agentic_collection() -> Any:
    try:
        from controller.chroma_runtime import get_or_create_collection
    except Exception as exc:
        raise RuntimeError(f"chroma runtime is not available: {exc}") from exc
    return get_or_create_collection(name=_agentic_collection_name(), persist_dir=os.getenv("WINTRIP_DB_PATH", "wintrip_brain"))


def _agentic_collection_name() -> str:
    return str(os.getenv("WINTRIP_AGENTIC_SESSION_COLLECTION") or DEFAULT_AGENTIC_SESSION_COLLECTION)


def _agentic_memory_max() -> int:
    try:
        return max(25, min(int(os.getenv("WINTRIP_AGENTIC_MEMORY_MAX", str(DEFAULT_AGENTIC_MEMORY_MAX))), 5000))
    except ValueError:
        return DEFAULT_AGENTIC_MEMORY_MAX


def _enforce_memory_cap(collection: Any, *, max_items: int) -> None:
    if max_items < 1 or not callable(getattr(collection, "count", None)):
        return
    try:
        count = int(collection.count())
    except Exception:
        return
    overflow = count - max_items
    if overflow <= 0:
        return
    try:
        records = collection.get(limit=count, include=["metadatas"])
    except Exception:
        return
    rows = []
    for item_id, meta in zip(records.get("ids", []), records.get("metadatas", [])):
        meta = meta if isinstance(meta, dict) else {}
        rows.append((str(meta.get("stored_at") or ""), item_id))
    rows.sort(key=lambda row: row[0])
    delete_ids = [item_id for _stored_at, item_id in rows[:overflow] if item_id]
    if delete_ids and callable(getattr(collection, "delete", None)):
        try:
            collection.delete(ids=delete_ids)
        except Exception:
            pass


def _compact_document(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)
    return text[:12000]


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer", "authorization")):
                clean[str(key)] = "[REDACTED]"
            else:
                clean[str(key)] = _redact(item)
        return clean
    if isinstance(value, list):
        return [_redact(item) for item in value[:80]]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value[:80])
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)[:6000]
    return value


def _embedding_11d(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    values = []
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
