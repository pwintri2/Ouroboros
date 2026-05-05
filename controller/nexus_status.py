"""Operational Ω Nexus state service.

The legacy `quantum_corruption_nexus` is a per-job entropy/coherence monitor.
This module sits on top of that and gives the cockpit a real, evidence-based
state model:

    - which subsystems have produced events recently (ingestion freshness)
    - how many agent jobs are active / failed / completed
    - a coherence score derived from the most recent QCN events
    - explicit reasoning ("why is the badge online vs degraded?")

Every value comes from real local sources — orchestrator job store, the QCN
event ring, and the Living loop's last tick. Nothing is invented.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from controller.status_contracts import freshness_seconds, is_fresh, normalize_status


NEXUS_STATE_VERSION = "v1"
RECENT_WINDOW_SECONDS = 5 * 60
DEFAULT_FRESHNESS_SECONDS = 5 * 60
DEFAULT_EVENT_LIMIT = 200


@dataclass
class IngestedEvent:
    """A small Nexus-level event record (separate from QCN raw events)."""

    ts: str
    source: str
    kind: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "source": self.source,
            "kind": self.kind,
            "summary": self.summary[:1000],
            "metadata": _scrub(self.metadata),
        }


class NexusState:
    """In-process Ω Nexus state, fed by orchestrator/living/world hooks."""

    _instance: "NexusState | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "NexusState":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=DEFAULT_EVENT_LIMIT)
        self._last_seen: dict[str, float] = {}
        self._counts = {
            "ingested": 0,
            "by_source": {},
        }
        self._initialized = True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_seen.clear()
            self._counts = {"ingested": 0, "by_source": {}}

    def ingest(
        self,
        source: str,
        kind: str,
        summary: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a subsystem event into the Nexus event ring."""

        event = IngestedEvent(
            ts=_utc_iso(),
            source=str(source or "unknown")[:64],
            kind=str(kind or "event")[:64],
            summary=str(summary or "")[:1000],
            metadata=dict(metadata or {}),
        )
        payload = event.to_dict()
        now = time.time()
        with self._lock:
            self._events.append(payload)
            self._counts["ingested"] += 1
            by_source = dict(self._counts.get("by_source") or {})
            by_source[event.source] = int(by_source.get(event.source, 0)) + 1
            self._counts["by_source"] = by_source
            self._last_seen[event.source] = now
        return payload

    def recent(self, *, limit: int = 50, source: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
        if source:
            events = [event for event in events if event.get("source") == source]
        limit = max(1, min(int(limit), DEFAULT_EVENT_LIMIT))
        return events[-limit:]

    def summary(self, *, freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS) -> dict[str, Any]:
        """Compute a real, explainable Nexus summary."""

        with self._lock:
            counts = {
                "ingested": int(self._counts.get("ingested", 0)),
                "by_source": dict(self._counts.get("by_source") or {}),
            }
            last_seen = dict(self._last_seen)

        sources_fresh = {source: is_fresh(ts, max_age_seconds=freshness_seconds) for source, ts in last_seen.items()}
        sources_age = {source: int(time.time() - ts) for source, ts in last_seen.items()}

        agent_runtime = _safe_agent_runtime_snapshot()
        qcn = _safe_qcn_snapshot()
        coherence_score = _coherence_score_from_qcn(qcn)
        recent_errors = _recent_error_count(agent_runtime)
        active = int(agent_runtime.get("active", 0))

        ingestion_health = "healthy" if any(sources_fresh.values()) else "stale"
        if active == 0 and not last_seen:
            ingestion_health = "idle"

        if recent_errors >= 3 and coherence_score < 0.6:
            status = "degraded"
            reason = f"{recent_errors} recent failures with coherence {coherence_score:.2f}; subsystem stalled."
        elif ingestion_health == "stale" and not active:
            status = "degraded"
            reason = "No fresh subsystem events within freshness window and no active jobs."
        elif ingestion_health in {"healthy", "idle"}:
            status = "online" if (qcn.get("status") == "online" or coherence_score >= 0.55) else "degraded"
            reason = "Receiving runtime, world, and living events within freshness window." if status == "online" else "Telemetry available but coherence below threshold."
        else:
            status = "degraded"
            reason = "Mixed evidence; subsystem reachable but not fresh."

        return {
            "status": status,
            "version": NEXUS_STATE_VERSION,
            "event_ingestion": ingestion_health,
            "active_job_count": active,
            "recent_error_count": recent_errors,
            "coherence_score": round(coherence_score, 4),
            "converged": bool(qcn.get("omega_vector", {}).get("converged")),
            "qcn_status": qcn.get("status", "unknown"),
            "qcn_counts": {
                key: int(qcn.get(key, 0))
                for key in ("healing_events", "sacred_corruptions", "total_corruption_events", "omega_convergences", "tool_rejections")
            },
            "sources_seen": counts["by_source"],
            "sources_fresh": sources_fresh,
            "sources_age_seconds": sources_age,
            "ingested_events_total": counts["ingested"],
            "freshness_window_seconds": freshness_seconds,
            "reason": reason,
            "fake_success": False,
        }


def get_nexus_state() -> NexusState:
    return NexusState()


def ingest_event(source: str, kind: str, summary: str, **metadata: Any) -> dict[str, Any]:
    return get_nexus_state().ingest(source, kind, summary, metadata=metadata)


def nexus_summary(freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS) -> dict[str, Any]:
    return get_nexus_state().summary(freshness_seconds=freshness_seconds)


def nexus_recent(limit: int = 50, source: str | None = None) -> list[dict[str, Any]]:
    return get_nexus_state().recent(limit=limit, source=source)


def recompute() -> dict[str, Any]:
    """Force a fresh summary; same data, just useful as a deliberate refresh trigger."""

    return nexus_summary()


def _safe_agent_runtime_snapshot() -> dict[str, Any]:
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        jobs = get_orchestrator().list_jobs(limit=50)
    except Exception:
        return {"active": 0, "jobs": [], "reason": "agent_runtime_unavailable"}
    active = 0
    for job in jobs:
        status = str(job.get("status") or "").lower()
        if status in {"queued", "planning", "running", "testing", "waiting_for_human"}:
            active += 1
    return {"active": active, "jobs": jobs}


def _safe_qcn_snapshot(limit: int = 5) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.quantum_corruption_nexus import quantum_nexus_status

        return quantum_nexus_status(limit=limit) or {}
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:300]}


def _coherence_score_from_qcn(qcn: dict[str, Any]) -> float:
    omega = qcn.get("omega_vector") if isinstance(qcn, dict) else None
    if isinstance(omega, dict):
        coherence = omega.get("coherence")
        try:
            return max(0.0, min(1.0, float(coherence)))
        except (TypeError, ValueError):
            pass
    events: Iterable[dict[str, Any]] = qcn.get("recent_events") or [] if isinstance(qcn, dict) else []
    coherences = [float(event.get("coherence", 0.0) or 0.0) for event in events if isinstance(event, dict)]
    if not coherences:
        return 0.0
    return max(0.0, min(1.0, sum(coherences) / len(coherences)))


def _recent_error_count(snapshot: dict[str, Any]) -> int:
    jobs = snapshot.get("jobs") or []
    cutoff = time.time() - RECENT_WINDOW_SECONDS
    count = 0
    for job in jobs:
        status = str(job.get("status") or "").lower()
        if status not in {"failed", "error"}:
            continue
        finished_raw = job.get("finished_at") or job.get("updated_at") or job.get("created_at") or ""
        try:
            ts = _parse_iso(str(finished_raw))
        except Exception:
            ts = None
        if ts is None or ts >= cutoff:
            count += 1
    return count


def _parse_iso(value: str) -> float | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _scrub(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        return {str(key)[:64]: _scrub(item, depth=depth + 1) for key, item in list(value.items())[:32]}
    if isinstance(value, (list, tuple)):
        return [_scrub(item, depth=depth + 1) for item in list(value)[:32]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    return text[:500]


__all__ = [
    "IngestedEvent",
    "NexusState",
    "get_nexus_state",
    "ingest_event",
    "nexus_recent",
    "nexus_summary",
    "recompute",
]
