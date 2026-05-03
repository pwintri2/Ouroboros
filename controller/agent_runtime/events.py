"""Append-only event log for agent jobs.

Events are written as JSON lines so they can be tailed by the cockpit and
inspected on disk. Each event has a stable schema:

    {"ts": "<iso8601>", "type": "<string>", "data": {...}}

The log helpers tolerate corrupted lines (skip + continue) so a partial write
never breaks consumers.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_LOCK = threading.Lock()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_event(events_file: Path | str, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append a single event to the log file. Returns the event payload."""

    payload: dict[str, Any] = {
        "ts": _utc_iso(),
        "type": str(event_type or "event"),
        "data": dict(data or {}),
    }
    path = Path(events_file)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def read_events(events_file: Path | str, after_index: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    """Return events with line-index >= after_index, capped at limit."""

    path = Path(events_file)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < after_index:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                payload["index"] = index
                out.append(payload)
                if len(out) >= max(1, int(limit)):
                    break
    except FileNotFoundError:
        return []
    return out


class EventLog:
    """Tiny convenience wrapper so adapters can log without juggling paths."""

    def __init__(self, events_file: Path | str):
        self.path = Path(events_file)

    def append(self, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return append_event(self.path, event_type, data)

    def read(self, after_index: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        return read_events(self.path, after_index=after_index, limit=limit)

    def extend(self, events: Iterable[dict[str, Any]]) -> None:
        for event in events:
            self.append(event.get("type", "event"), event.get("data") or {})
