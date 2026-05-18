"""Lightweight file context tracker for the agentic loop.

Mirrors the intent of Cline's FileContextTracker without depending on a file
watcher. The backend records every path the agent reads or edits during a
session. Before a subsequent edit the cockpit can ask whether the file is now
"stale" — meaning the on-disk mtime is newer than the agent's last recorded
read. That is the trigger to re-read before patching.

The tracker is intentionally read-only against the workspace: it never opens
file handles, only `os.stat` calls, and it stays within the workspace root.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Mapping


SOURCE_READ = "read"
SOURCE_EDIT = "edit"
SOURCE_MENTIONED = "mentioned"

STATUS_FRESH = "fresh"
STATUS_STALE = "stale"
STATUS_MISSING = "missing"
STATUS_UNKNOWN = "unknown"


class FileContextTracker:
    """Per-session map of file path -> last interaction record."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._files: dict[str, dict[str, dict[str, Any]]] = {}

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            self._files.pop(session_id, None)

    def reset_all(self) -> None:
        with self._lock:
            self._files.clear()

    def record(
        self,
        session_id: str,
        path: str,
        *,
        source: str = SOURCE_READ,
        workspace_root: str | None = None,
    ) -> dict[str, Any]:
        absolute = _resolve_path(path, workspace_root)
        mtime = _stat_mtime(absolute)
        record = {
            "path": _relative_or_absolute(absolute, workspace_root),
            "absolute_path": absolute,
            "source": str(source or SOURCE_READ),
            "recorded_mtime": mtime,
            "recorded_at": _ts(),
            "exists": mtime is not None,
        }
        if not session_id:
            return record
        with self._lock:
            files = self._files.setdefault(session_id, {})
            existing = files.get(absolute, {})
            existing.update(record)
            files[absolute] = existing
        return record

    def files(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._files.get(session_id, {}).values())
        for entry in entries:
            entry["status"] = self._status_for(entry)
        entries.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
        return entries

    def stale_files(self, session_id: str) -> list[dict[str, Any]]:
        return [entry for entry in self.files(session_id) if entry.get("status") == STATUS_STALE]

    def evaluate(self, session_id: str, path: str, *, workspace_root: str | None = None) -> dict[str, Any]:
        absolute = _resolve_path(path, workspace_root)
        with self._lock:
            entry = dict((self._files.get(session_id) or {}).get(absolute, {}))
        if not entry:
            return {
                "path": _relative_or_absolute(absolute, workspace_root),
                "status": STATUS_UNKNOWN,
                "reason": "Niet eerder geraadpleegd in deze sessie.",
                "fake_success": False,
            }
        entry["status"] = self._status_for(entry)
        entry["fake_success"] = False
        if entry["status"] == STATUS_STALE:
            entry["reason"] = "Bestand is na de laatste agent-actie gewijzigd; lees het opnieuw voor je het patcht."
        elif entry["status"] == STATUS_MISSING:
            entry["reason"] = "Bestand bestaat niet meer op disk."
        else:
            entry["reason"] = "Bestand is nog vers in de agent context."
        return entry

    def _status_for(self, entry: Mapping[str, Any]) -> str:
        absolute = str(entry.get("absolute_path") or "")
        if not absolute:
            return STATUS_UNKNOWN
        current = _stat_mtime(absolute)
        if current is None:
            return STATUS_MISSING
        recorded = entry.get("recorded_mtime")
        if recorded is None:
            return STATUS_UNKNOWN
        try:
            return STATUS_STALE if float(current) - float(recorded) > 0.5 else STATUS_FRESH
        except (TypeError, ValueError):
            return STATUS_UNKNOWN


_TRACKER = FileContextTracker()


def record_file_read(session_id: str, path: str, *, workspace_root: str | None = None) -> dict[str, Any]:
    return _TRACKER.record(session_id, path, source=SOURCE_READ, workspace_root=workspace_root)


def record_file_edit(session_id: str, path: str, *, workspace_root: str | None = None) -> dict[str, Any]:
    return _TRACKER.record(session_id, path, source=SOURCE_EDIT, workspace_root=workspace_root)


def record_file_mention(session_id: str, path: str, *, workspace_root: str | None = None) -> dict[str, Any]:
    return _TRACKER.record(session_id, path, source=SOURCE_MENTIONED, workspace_root=workspace_root)


def list_files(session_id: str) -> list[dict[str, Any]]:
    return _TRACKER.files(session_id)


def list_stale_files(session_id: str) -> list[dict[str, Any]]:
    return _TRACKER.stale_files(session_id)


def evaluate_path(session_id: str, path: str, *, workspace_root: str | None = None) -> dict[str, Any]:
    return _TRACKER.evaluate(session_id, path, workspace_root=workspace_root)


def reset_session(session_id: str) -> None:
    _TRACKER.reset_session(session_id)


def reset_all() -> None:
    _TRACKER.reset_all()


def _resolve_path(path: str, workspace_root: str | None) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    if os.path.isabs(text):
        return os.path.normpath(text)
    base = workspace_root or os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or os.getcwd()
    return os.path.normpath(os.path.join(base, text))


def _relative_or_absolute(absolute: str, workspace_root: str | None) -> str:
    base = workspace_root or os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or os.getcwd()
    try:
        relative = os.path.relpath(absolute, base)
    except ValueError:
        return absolute
    if relative.startswith(".."):
        return absolute
    return relative


def _stat_mtime(absolute: str) -> float | None:
    if not absolute:
        return None
    try:
        return os.path.getmtime(absolute)
    except OSError:
        return None


def _ts() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
