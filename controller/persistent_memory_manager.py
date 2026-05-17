"""Bounded ChromaDB memory helpers for agentic Ouroboros sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
    canonical_metadata: dict[str, Any] = {}
    try:
        from controller.ooda_hippocampus import build_ooda_metadata

        canonical_metadata = build_ooda_metadata(
            phase="reflect",
            session_id=item_id,
            event_kind="agentic_session",
            route=str(payload.get("route") or "agentic_processor"),
            status=status,
            payload=payload,
            approval_required=bool(payload.get("approval_required")),
            approval_status=str(payload.get("approval_status") or ("required" if payload.get("approval_required") else "not_required")),
            source="controller.persistent_memory_manager",
            source_type="agentic_session",
            taint=str(payload.get("taint") or "local_agentic_session"),
            learnable=False,
            audit_only=True,
            collection_name=_agentic_collection_name(),
            content_hash=digest,
        )
    except Exception:
        canonical_metadata = {}
    metadata = _flatten_metadata(
        {
            **canonical_metadata,
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
    metadata["type"] = "agentic_session_11d"
    metadata["content_hash"] = digest
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
        if collection is None:
            recovered = _store_agentic_session_recovery_chroma(
                item_id=item_id,
                document=document,
                metadata=metadata,
                digest=digest,
                primary_error=str(exc),
            )
            if recovered.get("stored"):
                return recovered
        return _store_agentic_session_fallback(
            item_id=item_id,
            document=document,
            metadata=metadata,
            digest=digest,
            primary_error=str(exc),
        )


def _agentic_collection(persist_dir: str | None = None) -> Any:
    try:
        from controller.chroma_runtime import get_or_create_collection
    except Exception as exc:
        raise RuntimeError(f"chroma runtime is not available: {exc}") from exc
    return get_or_create_collection(name=_agentic_collection_name(), persist_dir=persist_dir or _agentic_primary_persist_dir())


def _agentic_collection_name() -> str:
    return str(os.getenv("WINTRIP_AGENTIC_SESSION_COLLECTION") or DEFAULT_AGENTIC_SESSION_COLLECTION)


def _agentic_memory_max() -> int:
    try:
        return max(25, min(int(os.getenv("WINTRIP_AGENTIC_MEMORY_MAX", str(DEFAULT_AGENTIC_MEMORY_MAX))), 5000))
    except ValueError:
        return DEFAULT_AGENTIC_MEMORY_MAX


def _store_agentic_session_recovery_chroma(
    *,
    item_id: str,
    document: str,
    metadata: Mapping[str, Any],
    digest: str,
    primary_error: str,
) -> dict[str, Any]:
    primary = Path(_agentic_primary_persist_dir()).expanduser().resolve()
    for persist_dir in _agentic_recovery_persist_dirs():
        recovery = Path(persist_dir).expanduser().resolve()
        if recovery == primary:
            continue
        try:
            target = _agentic_collection(str(recovery))
            _enforce_memory_cap(target, max_items=_agentic_memory_max() - 1)
            target.add(
                ids=[item_id],
                documents=[document],
                metadatas=[dict(metadata)],
                embeddings=[_embedding_11d(document)],
            )
            _enforce_memory_cap(target, max_items=_agentic_memory_max())
            return {
                "status": "stored_recovered",
                "stored": True,
                "collection": _agentic_collection_name(),
                "item_id": item_id,
                "content_hash": digest,
                "persist_dir": str(recovery),
                "reason": "Primary ChromaDB session memory failed; stored in recovery ChromaDB.",
                "primary_error": str(primary_error)[:500],
                "fake_success": False,
            }
        except Exception:
            continue
    return {"status": "unavailable", "stored": False, "fake_success": False}


def _agentic_primary_persist_dir() -> str:
    return os.getenv("WINTRIP_DB_PATH", "wintrip_brain")


def _agentic_recovery_persist_dirs() -> list[str]:
    configured = os.getenv("WINTRIP_AGENTIC_SESSION_RECOVERY_DB_PATH")
    candidates = [configured] if configured else []
    candidates.extend(["data/chromadb", "wintrip_brain_recovered"])
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _store_agentic_session_fallback(
    *,
    item_id: str,
    document: str,
    metadata: Mapping[str, Any],
    digest: str,
    primary_error: str,
) -> dict[str, Any]:
    fallback_path = _agentic_fallback_path()
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "id": item_id,
        "collection": _agentic_collection_name(),
        "document": document,
        "metadata": _redact(dict(metadata)),
        "content_hash": digest,
        "primary_error": str(primary_error)[:1000],
        "stored_at": datetime.now(timezone.utc).isoformat(),
        "fallback_reason": "primary_chroma_unavailable",
    }
    with fallback_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return {
        "status": "stored_fallback",
        "stored": True,
        "collection": _agentic_collection_name(),
        "item_id": item_id,
        "content_hash": digest,
        "fallback_path": str(fallback_path),
        "reason": "Primary ChromaDB session memory failed; redacted JSONL fallback stored.",
        "primary_error": str(primary_error)[:500],
        "fake_success": False,
    }


def _agentic_fallback_path() -> Path:
    configured = os.getenv("WINTRIP_AGENTIC_SESSION_FALLBACK_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "."
    return (Path(workspace).expanduser().resolve() / "out" / "agentic_sessions_fallback.jsonl").resolve()


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
