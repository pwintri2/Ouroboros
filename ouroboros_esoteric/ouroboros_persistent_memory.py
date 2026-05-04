"""Persistent memory for the Living Ouroboros runtime.

This stores non-secret reflective events under `.secrets/` so the runtime can
show continuity after Docker/backend restarts. It deliberately stores short,
scrubbed summaries only; API keys, bearer tokens and passwords are redacted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_VERSION = "v4.6"
MAX_MEMORY_ENTRIES = 1000
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)


@dataclass
class PersistentMemoryEntry:
    id: str
    ts: str
    kind: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OuroborosPersistentMemory:
    """Thread-safe JSON memory timeline."""

    def __init__(self, path: Path | str | None = None, *, max_entries: int = MAX_MEMORY_ENTRIES):
        self.path = Path(path) if path else persistent_memory_path()
        self.max_entries = max(10, int(max_entries or MAX_MEMORY_ENTRIES))
        self._lock = threading.RLock()

    def append(self, kind: str, text: str, *, source: str = "living_loop", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_text = scrub_text(text)[:2000]
        entry = PersistentMemoryEntry(
            id=_entry_id(kind, clean_text, source),
            ts=_utc_iso(),
            kind=str(kind or "event"),
            text=clean_text,
            source=str(source or "unknown"),
            metadata=_scrub_metadata(metadata or {}),
        )
        with self._lock:
            payload = self._load_unlocked()
            entries = list(payload.get("entries") or [])
            entries.append(entry.to_dict())
            payload["entries"] = entries[-self.max_entries:]
            payload["version"] = MEMORY_VERSION
            payload["updated_at"] = entry.ts
            payload["counts"] = _counts(payload["entries"])
            self._save_unlocked(payload)
        return entry.to_dict()

    def load(self) -> dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def timeline(self, *, limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
        payload = self.load()
        entries = list(payload.get("entries") or [])
        if kind:
            entries = [entry for entry in entries if entry.get("kind") == kind]
        return entries[-max(1, int(limit)):]

    def status(self, *, limit: int = 12) -> dict[str, Any]:
        payload = self.load()
        entries = list(payload.get("entries") or [])
        return {
            "status": "online",
            "version": payload.get("version") or MEMORY_VERSION,
            "path": str(self.path),
            "entry_count": len(entries),
            "counts": payload.get("counts") or _counts(entries),
            "recent": entries[-max(1, int(limit)):],
            "updated_at": payload.get("updated_at"),
            "secrets_returned": False,
            "fake_success": False,
        }

    def reset(self) -> None:
        with self._lock:
            self._save_unlocked({"version": MEMORY_VERSION, "entries": [], "counts": {}, "updated_at": None})

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": MEMORY_VERSION, "entries": [], "counts": {}, "updated_at": None}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": MEMORY_VERSION, "entries": [], "counts": {}, "updated_at": None, "load_error": True}
        if not isinstance(payload, dict):
            return {"version": MEMORY_VERSION, "entries": [], "counts": {}, "updated_at": None}
        entries = payload.get("entries")
        if not isinstance(entries, list):
            payload["entries"] = []
        payload.setdefault("version", MEMORY_VERSION)
        payload["counts"] = _counts(payload["entries"])
        return payload

    def _save_unlocked(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def persistent_memory_path() -> Path:
    configured = os.getenv("WINTRIP_OUROBOROS_PERSISTENT_MEMORY")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/home/pwintri2/WintripAI")
    if not workspace.exists():
        workspace = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return (workspace / ".secrets" / "ouroboros_persistent_memory.json").resolve()


def get_persistent_memory() -> OuroborosPersistentMemory:
    return OuroborosPersistentMemory()


def scrub_text(text: Any) -> str:
    clean = str(text or "")
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _scrub_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer")):
            out[key] = "[REDACTED]"
        elif isinstance(value, str):
            out[key] = scrub_text(value)[:1000]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, dict):
            out[key] = _scrub_metadata(value)
        elif isinstance(value, list):
            out[key] = [scrub_text(item)[:500] if isinstance(item, str) else item for item in value[:20]]
        else:
            out[key] = scrub_text(value)[:500]
    return out


def _counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        kind = str(entry.get("kind") or "event")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _entry_id(kind: str, text: str, source: str) -> str:
    digest = hashlib.sha256(f"{kind}\n{text}\n{source}\n{_utc_iso()}".encode("utf-8", errors="replace")).hexdigest()
    return f"mem_{digest[:16]}"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
