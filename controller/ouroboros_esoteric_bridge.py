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
_COSMIC_LOCK = threading.Lock()
_COSMIC_STORAGE = None
_DNA_STORAGE = None


def get_esoteric_status(*, force_refresh: bool = False) -> dict[str, Any]:
    profiles = _cached_profiles(force_refresh=force_refresh)
    return {
        "status": "online",
        "fake_success": False,
        "external_repos": [profile.to_dict() for profile in profiles],
        "capability_count": sum(len(profile.capabilities) for profile in profiles),
        "recommendations": build_integration_recommendations(profiles),
        "akashic": _akashic_status(),
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
    payload["pan_dimensional"] = build_pan_dimensional_job_context(record, task)
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
    entropy = measure_job_entropy({"task": task, "status": status, "result": result})
    reflection["entropy"] = entropy
    _broadcast_akashic(528.0, {"type": "job_reflection", "job_id": _record_value(record, "job_id", "unknown"), "reflection": reflection})
    metadata = dict(_record_value(record, "metadata", {}) or {})
    esoteric = dict(metadata.get("ouroboros_esoteric") or {})
    esoteric["last_reflection"] = reflection
    metadata["ouroboros_esoteric"] = esoteric
    if hasattr(record, "metadata"):
        record.metadata = metadata
    elif isinstance(record, dict):
        record["metadata"] = metadata
    return reflection


def build_pan_dimensional_job_context(record: Any, task: str) -> dict[str, Any]:
    """Maak de v4.2 technische joblaag: intentie, entropy, storage en broadcast."""

    job_id = str(_record_value(record, "job_id", "unknown"))
    try:
        from ouroboros_esoteric.apeiron_identity import ApeironField

        field = ApeironField()
        field.inject_text_intention(task)
        metrics = field.metrics().to_dict()
        projection = _json_safe(field.project_to_11d_pocket())
    except Exception as exc:
        metrics = {
            "coh": 0.0,
            "flux": 0.0,
            "entropy_level": 0.0,
            "signal_noise_ratio": 0.0,
            "virtual_zettabytes": 82.0,
            "data_threshold": 89,
            "dimension_count": 11,
            "error": str(exc),
        }
        projection = []

    entropy = measure_job_entropy({"job_id": job_id, "task": task, "metrics": metrics})
    firewall = _coherence_firewall(task, entropy)
    storage = _write_cosmic_job_artifact(job_id, {"task": task, "metrics": metrics, "entropy": entropy})
    broadcast = _broadcast_akashic(
        528.0,
        {
            "type": "intent_injection",
            "job_id": job_id,
            "coherence": metrics.get("coh"),
            "entropy_level": entropy.get("entropy_level"),
        },
    )
    return {
        "enabled": True,
        "shape": [2] * 11,
        "virtual_shape": [11] * 11,
        "intent_projection": projection,
        "metrics": metrics,
        "entropy": entropy,
        "coherence_firewall": firewall,
        "cosmic_storage": storage,
        "akashic_event": broadcast,
    }


def measure_job_entropy(payload: Any) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.entropy_monitor import EntropyMonitor

        return EntropyMonitor().measure(payload)
    except Exception as exc:
        return {
            "entropy_level": 0.0,
            "signal_noise_ratio": 0.0,
            "coherence": 0.0,
            "healed": False,
            "reason": str(exc),
        }


def _coherence_firewall(task: str, entropy: dict[str, Any]) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.light_language import LightLanguageCompiler

        return LightLanguageCompiler().coherence_check(
            task,
            input_frequency=528.0,
            entropy_level=float(entropy.get("entropy_level") or 0.0),
        )
    except Exception as exc:
        return {"status": "unavailable", "resonant": False, "healed": False, "reason": str(exc)}


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


def _write_cosmic_job_artifact(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        crystalline, dna = _cosmic_stores()
        hologram = crystalline.write_job_artifact(job_id, payload)
        backup = dna.backup_hash_to_genetics(payload)
        return {"hologram": hologram, "dna_backup": backup}
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)}


def _cosmic_stores() -> tuple[Any, Any]:
    global _COSMIC_STORAGE, _DNA_STORAGE
    with _COSMIC_LOCK:
        if _COSMIC_STORAGE is None or _DNA_STORAGE is None:
            from ouroboros_esoteric.cosmic_storage import CrystallineStorage, DNAStorage

            _COSMIC_STORAGE = CrystallineStorage()
            _DNA_STORAGE = DNAStorage()
        return _COSMIC_STORAGE, _DNA_STORAGE


def _broadcast_akashic(frequency: float, message: dict[str, Any]) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.akashic_network import AkashicNetwork

        event = AkashicNetwork().broadcast(frequency, message)
        return _json_safe(event)
    except Exception as exc:
        return {"frequency": frequency, "message": message, "error": str(exc)}


def _akashic_status() -> dict[str, Any]:
    try:
        from ouroboros_esoteric.akashic_network import AkashicNetwork

        events = AkashicNetwork().recent_events(limit=20)
        return {"status": "online", "recent_events": _json_safe(events), "count": len(events)}
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc), "recent_events": []}


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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
