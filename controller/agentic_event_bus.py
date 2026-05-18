"""In-process event bus + JSONL persistence for agentic sessions.

The bus keeps a bounded ring buffer of recent sessions and events so the Tauri
cockpit can poll `/api/ouroboros/agentic/sessions/{session_id}/events` cheaply.
A JSONL log under `out/agentic_sessions/` is the durable record; it is
append-only, redacted, and safe to share for debugging.

Threading: a single module-level RLock protects both the sessions table and
the per-session event lists. Writes are O(events_kept), reads are O(1) per
session and O(N_sessions) for listings, which is fine at the small scales we
expect for an interactive cockpit.

Test hooks:
- `clear_event_bus()` wipes in-memory state so each unit test starts clean.
- `disable_event_bus_persistence()` skips JSONL writes during tests.
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict, deque
from collections.abc import Iterable
from typing import Any, Mapping

from controller.agentic_session_state import (
    EVENT_LOOP_BLOCKED,
    EVENT_LOOP_WARNING,
    EVENT_MEMORY_WRITE,
    EVENT_SESSION_CANCELLED,
    EVENT_SESSION_COMPLETED,
    EVENT_SESSION_FAILED,
    EVENT_TOOL_AWAITING_APPROVAL,
    EVENT_TOOL_BLOCKED,
    EVENT_TOOL_COMPLETED,
    EVENT_TOOL_FAILED,
    EVENT_TOOL_PLANNED,
    EVENT_TOOL_RUNNING,
    SESSION_STATUS_CANCELLED,
    SESSION_STATUS_RUNNING,
    compact_event_summary,
    compact_session_snapshot,
    make_event,
    redact,
    session_log_path,
    utc_now_iso,
)


DEFAULT_MAX_SESSIONS = 128
DEFAULT_MAX_EVENTS_PER_SESSION = 512
_PERSIST_DISABLED_ENV = "WINTRIP_AGENTIC_EVENT_BUS_NO_PERSIST"


class _EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._events: dict[str, deque[dict[str, Any]]] = {}
        self._sequences: dict[str, int] = {}
        self._cancellations: set[str] = set()

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._events.clear()
            self._sequences.clear()
            self._cancellations.clear()

    def register_session(self, session: dict[str, Any]) -> dict[str, Any]:
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            self._sessions[session_id] = session
            self._sessions.move_to_end(session_id)
            self._events.setdefault(session_id, deque(maxlen=_max_events_per_session()))
            self._sequences.setdefault(session_id, 0)
            self._trim_locked()
        return session

    def update_session(self, session_id: str, **fields: Any) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.update(fields)
            session["updated_at"] = utc_now_iso()
            self._sessions.move_to_end(session_id)
            return session

    def append_event(
        self,
        session_id: str,
        *,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        tool: str | None = None,
        status: str | None = None,
        duration_seconds: float | None = None,
        approval_required: bool | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            sequence = self._sequences.get(session_id, 0) + 1
            self._sequences[session_id] = sequence
            event = make_event(
                session_id=session_id,
                event_type=event_type,
                sequence=sequence,
                payload=payload,
                tool=tool,
                status=status,
                duration_seconds=duration_seconds,
                approval_required=approval_required,
            )
            self._events[session_id].append(event)
            self._apply_event_to_session_locked(session, event)
            self._sessions.move_to_end(session_id)
        _persist_event(event)
        return event

    def cancel_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            if session.get("status") in {SESSION_STATUS_RUNNING}:
                self._cancellations.add(session_id)
                return True
            return False

    def is_cancelled(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._cancellations

    def consume_cancellation(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._cancellations:
                self._cancellations.discard(session_id)
                return True
            return False

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return dict(session) if session is not None else None

    def list_sessions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        limit = max(1, min(int(limit or 20), DEFAULT_MAX_SESSIONS))
        return [compact_session_snapshot(item) for item in sessions[:limit]]

    def list_events(
        self,
        session_id: str,
        *,
        since_sequence: int = 0,
        limit: int = 200,
        compact: bool = False,
    ) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events.get(session_id, []))
        if since_sequence > 0:
            events = [event for event in events if int(event.get("sequence") or 0) > int(since_sequence)]
        limit = max(1, min(int(limit or 200), DEFAULT_MAX_EVENTS_PER_SESSION))
        events = events[-limit:]
        if compact:
            return [compact_event_summary(event) for event in events]
        return [redact(event) for event in events]

    def _trim_locked(self) -> None:
        max_sessions = _max_sessions()
        while len(self._sessions) > max_sessions:
            oldest_id, _ = self._sessions.popitem(last=False)
            self._events.pop(oldest_id, None)
            self._sequences.pop(oldest_id, None)
            self._cancellations.discard(oldest_id)

    def _apply_event_to_session_locked(self, session: dict[str, Any], event: Mapping[str, Any]) -> None:
        event_type = str(event.get("event_type") or "")
        tool_summary = session.setdefault(
            "tool_summary",
            {"planned": 0, "running": 0, "completed": 0, "blocked": 0, "failed": 0},
        )
        if event_type == EVENT_TOOL_PLANNED:
            tool_summary["planned"] = int(tool_summary.get("planned") or 0) + 1
        elif event_type == EVENT_TOOL_RUNNING:
            tool_summary["running"] = int(tool_summary.get("running") or 0) + 1
        elif event_type == EVENT_TOOL_COMPLETED:
            tool_summary["completed"] = int(tool_summary.get("completed") or 0) + 1
            tool_summary["running"] = max(0, int(tool_summary.get("running") or 0) - 1)
        elif event_type == EVENT_TOOL_BLOCKED:
            tool_summary["blocked"] = int(tool_summary.get("blocked") or 0) + 1
            session["approval_required"] = bool(event.get("approval_required") or session.get("approval_required"))
            blocked_tool = str(event.get("tool") or "")
            if blocked_tool:
                blocked_list = session.setdefault("blocked_tools", [])
                if blocked_tool not in blocked_list:
                    blocked_list.append(blocked_tool)
        elif event_type == EVENT_TOOL_FAILED:
            tool_summary["failed"] = int(tool_summary.get("failed") or 0) + 1
        elif event_type == EVENT_TOOL_AWAITING_APPROVAL:
            session["approval_required"] = True
            session["approval_status"] = "required"
        elif event_type == EVENT_LOOP_WARNING:
            session["loop_warning"] = True
        elif event_type == EVENT_LOOP_BLOCKED:
            session["loop_blocked"] = True
        elif event_type == EVENT_MEMORY_WRITE:
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
            if payload:
                session["memory_status"] = dict(payload)
        elif event_type == EVENT_SESSION_COMPLETED:
            session["status"] = "completed"
            session["completed_at"] = utc_now_iso()
        elif event_type == EVENT_SESSION_FAILED:
            session["status"] = "failed"
            session["completed_at"] = utc_now_iso()
        elif event_type == EVENT_SESSION_CANCELLED:
            session["status"] = SESSION_STATUS_CANCELLED
            session["completed_at"] = utc_now_iso()
        session["updated_at"] = utc_now_iso()


_BUS = _EventBus()
_PERSIST_LOCK = threading.Lock()


def register_session(session: dict[str, Any]) -> dict[str, Any]:
    return _BUS.register_session(session)


def update_session(session_id: str, **fields: Any) -> dict[str, Any] | None:
    return _BUS.update_session(session_id, **fields)


def append_event(
    session_id: str,
    *,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    tool: str | None = None,
    status: str | None = None,
    duration_seconds: float | None = None,
    approval_required: bool | None = None,
) -> dict[str, Any] | None:
    return _BUS.append_event(
        session_id,
        event_type=event_type,
        payload=payload,
        tool=tool,
        status=status,
        duration_seconds=duration_seconds,
        approval_required=approval_required,
    )


def get_session(session_id: str) -> dict[str, Any] | None:
    return _BUS.get_session(session_id)


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    return _BUS.list_sessions(limit=limit)


def list_events(
    session_id: str,
    *,
    since_sequence: int = 0,
    limit: int = 200,
    compact: bool = False,
) -> list[dict[str, Any]]:
    return _BUS.list_events(session_id, since_sequence=since_sequence, limit=limit, compact=compact)


def request_cancel(session_id: str) -> bool:
    return _BUS.cancel_session(session_id)


def is_cancelled(session_id: str) -> bool:
    return _BUS.is_cancelled(session_id)


def consume_cancellation(session_id: str) -> bool:
    return _BUS.consume_cancellation(session_id)


def clear_event_bus() -> None:
    """Test helper — drop all in-memory state."""

    _BUS.reset()


def disable_event_bus_persistence() -> None:
    """Test helper — skip JSONL writes."""

    os.environ[_PERSIST_DISABLED_ENV] = "1"


def enable_event_bus_persistence() -> None:
    """Test helper — restore JSONL writes."""

    os.environ.pop(_PERSIST_DISABLED_ENV, None)


def _persist_event(event: Mapping[str, Any]) -> None:
    if _persistence_disabled():
        return
    try:
        path = session_log_path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        line = json.dumps(redact(event), ensure_ascii=False, sort_keys=True, default=str)
        with _PERSIST_LOCK:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:
        # Persistence failures should never break the agentic run; the cockpit
        # still has the in-memory bus and the AgenticProcessor still finishes.
        pass


def _persistence_disabled() -> bool:
    value = str(os.getenv(_PERSIST_DISABLED_ENV) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _max_sessions() -> int:
    try:
        return max(8, min(int(os.getenv("WINTRIP_AGENTIC_MAX_SESSIONS", str(DEFAULT_MAX_SESSIONS))), 1024))
    except ValueError:
        return DEFAULT_MAX_SESSIONS


def _max_events_per_session() -> int:
    try:
        return max(32, min(int(os.getenv("WINTRIP_AGENTIC_MAX_EVENTS", str(DEFAULT_MAX_EVENTS_PER_SESSION))), 4096))
    except ValueError:
        return DEFAULT_MAX_EVENTS_PER_SESSION


def safe_iterable(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple, set)):
        return value
    if value is None:
        return ()
    return (value,)
