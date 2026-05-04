"""Bridge tussen agent-runtime events en de esoterische Ouroboros laag."""

from __future__ import annotations

import threading
import time
from typing import Any

from ouroboros_esoteric.repository_integration import (
    ExternalRepoProfile,
    build_integration_recommendations,
    scan_external_repositories,
)


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"ts": 0.0, "profiles": []}
_CACHE_TTL_SECONDS = 30.0


def get_esoteric_status(*, force_refresh: bool = False) -> dict[str, Any]:
    profiles = _cached_profiles(force_refresh=force_refresh)
    return {
        "status": "online",
        "fake_success": False,
        "external_repos": [profile.to_dict() for profile in profiles],
        "capability_count": sum(len(profile.capabilities) for profile in profiles),
        "recommendations": build_integration_recommendations(profiles),
        "memory_policy": {
            "episodic": "Job events and outcomes become recallable experiences.",
            "semantic": "Repo capabilities become stable Ouroboros facts.",
            "procedural": "Repeated successful patterns can be promoted to workflows.",
        },
    }


def enrich_job_record(record: Any, *, force_refresh: bool = False) -> dict[str, Any]:
    """Plaats externe capability-context in `JobRecord.metadata`."""

    profiles = _cached_profiles(force_refresh=force_refresh)
    task = _record_value(record, "task", "")
    payload = build_job_esoteric_context(task, profiles)
    metadata = dict(_record_value(record, "metadata", {}) or {})
    metadata["ouroboros_esoteric"] = payload
    if hasattr(record, "metadata"):
        record.metadata = metadata
    elif isinstance(record, dict):
        record["metadata"] = metadata
    return payload


def reflect_job_result(record: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Vat een agent-job afloop samen als episodisch geheugenmateriaal."""

    result = result or {}
    status = result.get("status") or _record_value(record, "status", "unknown")
    task = _record_value(record, "task", "")
    reflection = {
        "memory_kind": "episodic",
        "summary": f"Agent job {_record_value(record, 'job_id', 'unknown')} ended as {status}.",
        "status": status,
        "task_preview": str(task)[:240],
        "exit_code": result.get("exit_code"),
        "promote_to_procedure": status == "completed" and _looks_procedural(task),
        "tags": sorted(_task_tags(task)),
    }
    metadata = dict(_record_value(record, "metadata", {}) or {})
    esoteric = dict(metadata.get("ouroboros_esoteric") or {})
    esoteric["last_reflection"] = reflection
    metadata["ouroboros_esoteric"] = esoteric
    if hasattr(record, "metadata"):
        record.metadata = metadata
    elif isinstance(record, dict):
        record["metadata"] = metadata
    return reflection


def build_job_esoteric_context(task: str, profiles: list[ExternalRepoProfile]) -> dict[str, Any]:
    """Bouw taakgerichte context uit externe repo-profielen."""

    task_tags = _task_tags(task)
    matched_patterns: list[dict[str, Any]] = []
    for profile in profiles:
        if not profile.exists:
            continue
        for signal in profile.signals:
            if signal.family in task_tags or signal.name in task.lower():
                matched_patterns.append(
                    {
                        "origin": profile.origin,
                        "name": signal.name,
                        "family": signal.family,
                        "summary": signal.summary,
                        "strength": signal.strength,
                    }
                )

    if not matched_patterns:
        for profile in profiles:
            if profile.exists and profile.signals:
                top = profile.signals[0]
                matched_patterns.append(
                    {
                        "origin": profile.origin,
                        "name": top.name,
                        "family": top.family,
                        "summary": top.summary,
                        "strength": top.strength,
                    }
                )

    matched_patterns.sort(key=lambda item: float(item.get("strength") or 0.0), reverse=True)
    return {
        "enabled": True,
        "phase": "external_repo_lattice",
        "task_tags": sorted(task_tags),
        "sources": [
            {
                "origin": profile.origin,
                "exists": profile.exists,
                "capabilities": profile.capabilities,
            }
            for profile in profiles
        ],
        "recommended_patterns": matched_patterns[:8],
    }


def _cached_profiles(*, force_refresh: bool = False) -> list[ExternalRepoProfile]:
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force_refresh and _CACHE["profiles"] and now - float(_CACHE["ts"]) < _CACHE_TTL_SECONDS:
            return list(_CACHE["profiles"])
        profiles = scan_external_repositories()
        _CACHE["ts"] = now
        _CACHE["profiles"] = profiles
        return list(profiles)


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _task_tags(task: str) -> set[str]:
    lower = str(task or "").lower()
    tags: set[str] = set()
    if any(word in lower for word in ("memory", "remember", "context", "geheugen")):
        tags.add("memory")
    if any(word in lower for word in ("search", "retrieve", "retrieval", "rag", "research", "zoek")):
        tags.add("retrieval")
    if any(word in lower for word in ("agent", "swarm", "runtime", "orchestr")):
        tags.add("orchestration")
    if any(word in lower for word in ("safe", "guard", "approval", "dedup", "security")):
        tags.add("safety")
    if any(word in lower for word in ("connector", "drive", "gmail", "surf", "source")):
        tags.add("connectors")
    if any(word in lower for word in ("workflow", "procedure", "test", "deploy", "pipeline")):
        tags.add("learning")
        tags.add("persistence")
    if not tags:
        tags.add("semantic")
    return tags


def _looks_procedural(task: str) -> bool:
    lower = str(task or "").lower()
    return any(word in lower for word in ("test", "workflow", "procedure", "pipeline", "deploy", "fix"))
