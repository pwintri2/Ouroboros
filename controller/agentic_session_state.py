"""Session and event schema for Cline-grade agentic Ouroboros runs.

This module defines the redacted, inspectable contract used by the Tauri cockpit
and `/api/ouroboros/agentic/*` routes. The schema is deliberately compact and
JSON-safe so it can be persisted in JSONL, polled by the UI, and reused for
post-run audit reports without leaking secrets.

Design notes
- Sessions and events are plain dictionaries — easy to ship over FastAPI, easy
  to redact, and they survive a process restart when persisted to JSONL.
- Redaction reuses the same key/value heuristics as
  `controller.persistent_memory_manager`: anything that looks like a key,
  token, bearer, password or authorization material is replaced before the
  event reaches the bus.
- The bus itself lives in `controller.agentic_event_bus` so the in-process
  state can stay separate from the schema definitions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping


SESSION_STATUS_RUNNING = "running"
SESSION_STATUS_COMPLETED = "completed"
SESSION_STATUS_BLOCKED = "blocked"
SESSION_STATUS_FAILED = "failed"
SESSION_STATUS_CANCELLED = "cancelled"

EVENT_SESSION_STARTED = "session_started"
EVENT_PLAN_BUILT = "plan_built"
EVENT_TOOL_PLANNED = "tool_planned"
EVENT_TOOL_VALIDATED = "tool_validated"
EVENT_TOOL_AWAITING_APPROVAL = "tool_awaiting_approval"
EVENT_TOOL_RUNNING = "tool_running"
EVENT_TOOL_COMPLETED = "tool_completed"
EVENT_TOOL_BLOCKED = "tool_blocked"
EVENT_TOOL_FAILED = "tool_failed"
EVENT_LOOP_WARNING = "loop_warning"
EVENT_LOOP_BLOCKED = "loop_blocked"
EVENT_MEMORY_WRITE = "memory_write"
EVENT_CHECKPOINT_RECORDED = "checkpoint_recorded"
EVENT_SESSION_COMPLETED = "session_completed"
EVENT_SESSION_FAILED = "session_failed"
EVENT_SESSION_CANCELLED = "session_cancelled"

PLAN_MODE_ACT = "act"
PLAN_MODE_PLAN = "plan"

APPROVAL_PHRASE = "Akkoord"

_SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "token",
    "password",
    "passwd",
    "bearer",
    "authorization",
    "session",
    "cookie",
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|bearer|token|password|passwd|secret|authorization)\s*[:=]\s*['\"]?[^'\"\s,}]+"
)
_REDACTED = "[REDACTED]"
_DEFAULT_TRUNCATE_STR = 1200
_DEFAULT_TRUNCATE_LIST = 40


def new_session_id() -> str:
    """Return a fresh agentic session id."""

    return f"agentic_{uuid.uuid4()}"


def normalize_session_id(value: Any) -> str:
    """Return a stable session id, generating one when the input is empty."""

    text = str(value or "").strip()
    if text:
        return text
    return new_session_id()


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with millisecond precision."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def make_session(
    *,
    session_id: str,
    goal: str,
    plan_mode: str,
    provider: str,
    model: str,
    conversation_id: str = "",
    route: str = "agentic_processor",
) -> dict[str, Any]:
    """Initial session record. The event log lives separately on the bus."""

    return {
        "schema_version": 1,
        "session_id": session_id,
        "conversation_id": str(conversation_id or ""),
        "route": str(route or "agentic_processor"),
        "goal": _clean_goal(goal),
        "plan_mode": str(plan_mode or PLAN_MODE_ACT),
        "provider": str(provider or ""),
        "model": str(model or ""),
        "status": SESSION_STATUS_RUNNING,
        "approval_required": False,
        "approval_status": "not_required",
        "blocked_tools": [],
        "tool_summary": {
            "planned": 0,
            "running": 0,
            "completed": 0,
            "blocked": 0,
            "failed": 0,
        },
        "loop_warning": False,
        "loop_blocked": False,
        "memory_status": {},
        "checkpoint": {},
        "files_touched": [],
        "duration_seconds": None,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "completed_at": None,
        "fake_success": False,
        "secrets_returned": False,
    }


def make_event(
    *,
    session_id: str,
    event_type: str,
    sequence: int,
    payload: Mapping[str, Any] | None = None,
    tool: str | None = None,
    status: str | None = None,
    duration_seconds: float | None = None,
    approval_required: bool | None = None,
) -> dict[str, Any]:
    """Build a single redacted event record ready for the event bus."""

    safe_payload = redact(payload or {})
    event: dict[str, Any] = {
        "schema_version": 1,
        "event_id": f"{session_id}:{sequence:06d}",
        "session_id": session_id,
        "sequence": int(sequence),
        "event_type": str(event_type),
        "ts": utc_now_iso(),
        "monotonic": round(time.monotonic(), 6),
        "payload": safe_payload,
        "fake_success": False,
        "secrets_returned": False,
    }
    if tool is not None:
        event["tool"] = str(tool)
    if status is not None:
        event["status"] = str(status)
    if duration_seconds is not None:
        event["duration_seconds"] = round(float(duration_seconds), 3)
    if approval_required is not None:
        event["approval_required"] = bool(approval_required)
    return event


def compact_event_summary(event: Mapping[str, Any]) -> dict[str, Any]:
    """Lightweight view used in session list responses."""

    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    return {
        "event_id": event.get("event_id"),
        "sequence": event.get("sequence"),
        "event_type": event.get("event_type"),
        "ts": event.get("ts"),
        "tool": event.get("tool"),
        "status": event.get("status"),
        "duration_seconds": event.get("duration_seconds"),
        "approval_required": event.get("approval_required"),
        "summary": _payload_summary(payload),
    }


def compact_session_snapshot(session: Mapping[str, Any]) -> dict[str, Any]:
    """Trim a session record for sidebar/list rendering."""

    return {
        "session_id": session.get("session_id"),
        "conversation_id": session.get("conversation_id"),
        "route": session.get("route"),
        "goal": (str(session.get("goal") or "")[:180]),
        "plan_mode": session.get("plan_mode"),
        "provider": session.get("provider"),
        "model": session.get("model"),
        "status": session.get("status"),
        "approval_required": session.get("approval_required"),
        "approval_status": session.get("approval_status"),
        "blocked_tools": list(session.get("blocked_tools") or [])[:10],
        "tool_summary": dict(session.get("tool_summary") or {}),
        "loop_warning": bool(session.get("loop_warning")),
        "loop_blocked": bool(session.get("loop_blocked")),
        "memory_status": _compact_memory_status(session.get("memory_status")),
        "checkpoint": _compact_checkpoint(session.get("checkpoint")),
        "files_touched": list(session.get("files_touched") or [])[:20],
        "duration_seconds": session.get("duration_seconds"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "completed_at": session.get("completed_at"),
        "fake_success": False,
        "secrets_returned": False,
    }


def merge_completion_into_session(session: dict[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Fold the AgenticProcessor final state into the persisted session record."""

    status_value = str(state.get("status") or "").lower()
    if status_value in {"success", "completed", "stored", "opened"}:
        session["status"] = SESSION_STATUS_COMPLETED
    elif status_value in {"blocked", "approval_required", "configuration_required"}:
        session["status"] = SESSION_STATUS_BLOCKED
    elif status_value in {"error", "failed", "rejected"}:
        session["status"] = SESSION_STATUS_FAILED
    elif status_value:
        session["status"] = status_value
    session["approval_required"] = bool(state.get("approval_required"))
    session["approval_status"] = (
        "required" if session["approval_required"] else "approved" if status_value in {"success", "completed", "stored"} else "not_required"
    )
    blocked = state.get("blocked_tools")
    if isinstance(blocked, list):
        session["blocked_tools"] = [str(item) for item in blocked][:20]
    memory_status = state.get("memory_status")
    if isinstance(memory_status, Mapping):
        session["memory_status"] = _compact_memory_status(memory_status)
    duration = state.get("duration_seconds")
    if duration is not None:
        try:
            session["duration_seconds"] = round(float(duration), 3)
        except (TypeError, ValueError):
            pass
    session["completed_at"] = utc_now_iso()
    session["updated_at"] = utc_now_iso()
    return session


def redact(value: Any, *, max_str: int = _DEFAULT_TRUNCATE_STR, max_list: int = _DEFAULT_TRUNCATE_LIST) -> Any:
    """Recursive redaction matching the persistent memory manager rules."""

    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                clean[str(key)] = _REDACTED
            else:
                clean[str(key)] = redact(item, max_str=max_str, max_list=max_list)
        return clean
    if isinstance(value, list):
        trimmed = list(value)[: max(0, int(max_list))]
        return [redact(item, max_str=max_str, max_list=max_list) for item in trimmed]
    if isinstance(value, tuple):
        trimmed = list(value)[: max(0, int(max_list))]
        return tuple(redact(item, max_str=max_str, max_list=max_list) for item in trimmed)
    if isinstance(value, set):
        trimmed = list(value)[: max(0, int(max_list))]
        return sorted(redact(item, max_str=max_str, max_list=max_list) for item in trimmed)
    if isinstance(value, str):
        truncated = value[: max(0, int(max_str))]
        return _SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}={_REDACTED}", truncated)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact(str(value), max_str=max_str, max_list=max_list)


def session_log_path() -> str:
    """JSONL session log path. Configurable via env, defaults under out/."""

    configured = os.getenv("WINTRIP_AGENTIC_SESSION_LOG", "").strip()
    if configured:
        return configured
    workspace = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "."
    return os.path.normpath(os.path.join(workspace, "out", "agentic_sessions", "events.jsonl"))


def goal_digest(goal: str) -> str:
    return hashlib.sha256(str(goal or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def _clean_goal(goal: Any) -> str:
    text = str(goal or "").replace("\x00", " ")
    return " ".join(text.split())[:1600]


def _payload_summary(payload: Mapping[str, Any]) -> str:
    if not payload:
        return ""
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        text = str(payload)
    return text[:240]


def _compact_memory_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    keys = (
        "status",
        "stored",
        "collection",
        "item_id",
        "fallback_path",
        "persist_dir",
        "reason",
        "primary_error",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key in value:
            out[key] = value.get(key)
    return out


def _compact_checkpoint(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    keys = (
        "status",
        "checkpoint_id",
        "head_before",
        "changed_files_count",
        "method",
        "reason",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key in value:
            out[key] = value.get(key)
    return out
