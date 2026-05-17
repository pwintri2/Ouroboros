"""Best-effort read-only trainer status when the full router cannot load.

The trainer API pulls in many optional adapters. One failing import should not
make the cockpit look dead; this module keeps status endpoints available while
making the degraded state explicit and auditable.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def trainer_fallback_status(reason: object = "") -> dict[str, Any]:
    """Return the trainer status contract without requiring the full API module."""
    route_reason = _clean_reason(reason)
    approved_count = _safe_count(
        "controller.training_dataset_builder",
        "count_approved_records",
        default=0,
    )
    codex_registry = _safe_status(
        "controller.codex_registry",
        "get_codex_registry_status",
        _codex_registry_default(route_reason),
    )
    monitor = _safe_status(
        "controller.codex_registry",
        "get_codex_monitor",
        _codex_monitor_default(route_reason),
    )
    if isinstance(codex_registry, dict):
        codex_registry.setdefault("monitor", monitor)

    return {
        "status": "degraded",
        "routes_available": False,
        "reason": route_reason,
        "pipeline": _safe_status(
            "controller.trainer_jobs",
            "get_pipeline_status",
            _pipeline_default(route_reason),
        ),
        "litgpt": _safe_status(
            "controller.litgpt_adapter",
            "get_litgpt_status",
            _component_default(route_reason),
        ),
        "unsloth": _safe_status(
            "controller.unsloth_adapter",
            "get_unsloth_status",
            _component_default(route_reason),
        ),
        "blue_brain": _safe_status(
            "controller.blue_brain_adapter",
            "get_blue_brain_status",
            _component_default(route_reason),
        ),
        "rotating_blue": _safe_status(
            "controller.rotating_blue_brain",
            "get_rotating_status",
            _rotating_default(route_reason),
        ),
        "streaming_consciousness": _safe_status(
            "controller.streaming_consciousness_adapter",
            "get_streaming_status",
            _streaming_default(route_reason),
        ),
        "codex_registry": codex_registry,
        "codex_agent": _safe_status(
            "controller.codex_agent",
            "get_codex_agent_status",
            _codex_agent_default(route_reason),
        ),
        "codeneuron": _safe_status(
            "controller.codeneuron_adapter",
            "get_codeneuron_status",
            _codeneuron_default(route_reason),
        ),
        "ecosystem": _safe_status(
            "controller.ecosystem_status",
            "get_ecosystem_status",
            _ecosystem_default(route_reason),
        ),
        "popos_diagnostics": _safe_status(
            "controller.popos_diagnostics_adapter",
            "get_popos_diagnostics_status",
            _component_default(route_reason),
        ),
        "google_workspace": _safe_status(
            "controller.google_workspace_adapter",
            "get_google_workspace_status",
            _component_default(route_reason),
        ),
        "rclone_drive": _safe_status(
            "controller.rclone_drive_adapter",
            "get_rclone_drive_status",
            _component_default(route_reason),
        ),
        "microsoft_graph": _safe_status(
            "controller.microsoft_graph_adapter",
            "get_microsoft_graph_status",
            _component_default(route_reason),
        ),
        "sharepoint": _safe_status(
            "controller.sharepoint_pnp_adapter",
            "get_sharepoint_status",
            _component_default(route_reason),
        ),
        "agentic_crawler": _safe_status(
            "controller.agentic_crawler",
            "get_agentic_crawler_status",
            _crawler_default(route_reason),
        ),
        "program_inventory": _safe_status(
            "controller.host_program_inventory",
            "get_host_program_inventory_status",
            _program_inventory_default(route_reason),
        ),
        "host_sensory": _safe_status(
            "controller.host_sensory_adapter",
            "get_host_sensory_status",
            _host_sensory_default(route_reason),
        ),
        "ecosystem_knowledge": _safe_status(
            "controller.ecosystem_knowledge_ingest",
            "get_ecosystem_knowledge_status",
            _ecosystem_knowledge_default(route_reason),
        ),
        "curriculum": _safe_status(
            "controller.training_curriculum",
            "curriculum_status",
            _curriculum_default(route_reason),
        ),
        "knowledge_acquisition": _safe_status(
            "controller.knowledge_acquisition",
            "get_knowledge_acquisition_status",
            _knowledge_default(route_reason),
        ),
        "local_machine": _safe_status(
            "controller.local_machine_profile",
            "get_local_machine_status",
            _local_machine_default(route_reason),
        ),
        "independence": _safe_status(
            "controller.ouroboros_independence",
            "compute_independence_score",
            _independence_default(route_reason),
        ),
        "continuous": _safe_status(
            "controller.trainer_continuous",
            "get_continuous_status",
            _continuous_default(route_reason, approved_count),
        ),
        "artifacts": _safe_status(
            "controller.model_artifacts",
            "get_artifacts_summary",
            _artifacts_default(route_reason),
        ),
        "approved_dataset_records": approved_count,
        "fake_success": False,
    }


def trainer_fallback_jobs(reason: object = "") -> dict[str, Any]:
    """Return the trainer jobs list if storage is readable, otherwise an empty list."""
    route_reason = _clean_reason(reason)
    try:
        module = import_module("controller.trainer_jobs")
        jobs = module.list_jobs()
        if not isinstance(jobs, list):
            jobs = []
    except Exception:
        jobs = []
    return {
        "status": "degraded",
        "routes_available": False,
        "reason": route_reason,
        "jobs": jobs,
        "count": len(jobs),
        "fake_success": False,
    }


def trainer_fallback_component(key: str, reason: object = "") -> dict[str, Any]:
    """Return one component from the fallback status payload."""
    status = trainer_fallback_status(reason)
    value = status.get(key)
    if isinstance(value, dict):
        value.setdefault("routes_available", False)
        return value
    return _component_default(_clean_reason(reason))


def trainer_fallback_codex_functions(reason: object = "") -> dict[str, Any]:
    route_reason = _clean_reason(reason)
    try:
        module = import_module("controller.codex_registry")
        value = module.list_codex_functions()
        if isinstance(value, dict):
            value.setdefault("routes_available", False)
            return value
    except Exception:
        pass
    return {
        "status": "degraded",
        "routes_available": False,
        "reason": route_reason,
        "functions": [],
        "count": 0,
        "fake_success": False,
    }


def trainer_fallback_codex_monitor(reason: object = "") -> dict[str, Any]:
    return _safe_status(
        "controller.codex_registry",
        "get_codex_monitor",
        _codex_monitor_default(_clean_reason(reason)),
    )


def trainer_fallback_codex_agent_memory(reason: object = "", limit: int = 20) -> dict[str, Any]:
    route_reason = _clean_reason(reason)
    try:
        module = import_module("controller.codex_agent")
        value = module.get_codex_agent_memory(limit=limit)
        if isinstance(value, dict):
            value.setdefault("routes_available", False)
            return value
    except Exception:
        pass
    return {
        "status": "degraded",
        "routes_available": False,
        "reason": route_reason,
        "memory": [],
        "conversation": [],
        "memory_count": 0,
        "conversation_count": 0,
        "fake_success": False,
    }


def trainer_fallback_pocket_map(reason: object = "") -> dict[str, Any]:
    return _safe_status(
        "controller.codeneuron_adapter",
        "get_codeneuron_pocket_map",
        {
            "status": "degraded",
            "routes_available": False,
            "reason": _clean_reason(reason),
            "dimension_count": 11,
            "dimensions": [],
            "fake_success": False,
        },
    )


def _safe_status(module_name: str, function_name: str, default: dict[str, Any]) -> dict[str, Any]:
    try:
        module = import_module(module_name)
        value = getattr(module, function_name)()
        if isinstance(value, dict):
            return value
        result = dict(default)
        result["reason"] = "Status function did not return an object."
        return result
    except Exception as exc:
        result = dict(default)
        result["reason"] = _clean_reason(exc)
        result["fake_success"] = False
        return result


def _safe_count(module_name: str, function_name: str, *, default: int) -> int:
    try:
        module = import_module(module_name)
        value = getattr(module, function_name)()
        return int(value)
    except Exception:
        return default


def _clean_reason(reason: object) -> str:
    text = str(reason or "trainer pipeline routes unavailable").strip()
    return text[:500] if text else "trainer pipeline routes unavailable"


def _component_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "available": False,
        "reason": reason,
        "fake_success": False,
    }


def _pipeline_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "total_jobs": 0,
        "by_state": {},
        "recent_jobs": [],
        "reason": reason,
        "fake_success": False,
    }


def _continuous_default(reason: str, approved_count: int) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "enabled": False,
        "methods": [],
        "worker_alive": False,
        "approved_dataset_records": approved_count,
        "new_records_available": 0,
        "reason": reason,
        "fake_success": False,
    }


def _rotating_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "enabled": False,
        "rotation_count": 0,
        "training_rotation_count": 0,
        "last_projection": [],
        "reason": reason,
        "fake_success": False,
    }


def _streaming_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "enabled": False,
        "step_count": 0,
        "last_projection": [],
        "runtime_input": {"source": "unavailable", "real_observation": False},
        "ecosystem_overlay": {"status": "unavailable"},
        "reason": reason,
        "fake_success": False,
    }


def _codex_registry_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "callable_count": 0,
        "functions": [],
        "monitor": _codex_monitor_default(reason),
        "reason": reason,
        "fake_success": False,
    }


def _codex_monitor_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "total_calls": 0,
        "success_calls": 0,
        "error_calls": 0,
        "recent_calls": [],
        "reason": reason,
        "fake_success": False,
    }


def _codex_agent_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "memory_count": 0,
        "capability_gap_count": 0,
        "recent_events": [],
        "reason": reason,
        "fake_success": False,
    }


def _codeneuron_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "indexed": False,
        "file_count": 0,
        "total_lines": 0,
        "reason": reason,
        "fake_success": False,
    }


def _ecosystem_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "ecosystem_adapters": {},
        "crawl_stats": _crawler_default(reason),
        "program_inventory": _program_inventory_default(reason),
        "host_sensory": _host_sensory_default(reason),
        "ecosystem_knowledge": _ecosystem_knowledge_default(reason),
        "approval_required": True,
        "reason": reason,
        "fake_success": False,
    }


def _crawler_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "indexed_files": 0,
        "skipped_private": 0,
        "pending_approvals": [],
        "reason": reason,
        "fake_success": False,
    }


def _program_inventory_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "desktop_app_count": 0,
        "package_count": 0,
        "reason": reason,
        "fake_success": False,
    }


def _host_sensory_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "active_flow_count": 0,
        "process_count": 0,
        "reason": reason,
        "fake_success": False,
    }


def _ecosystem_knowledge_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "topic_count": 0,
        "record_count": 0,
        "reason": reason,
        "fake_success": False,
    }


def _curriculum_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "record_count": 0,
        "curricula": [],
        "label_counts": {},
        "reason": reason,
        "fake_success": False,
    }


def _knowledge_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "topic_count": 0,
        "total_records": 0,
        "gemma_completed": 0,
        "brave_completed": 0,
        "browser_completed": 0,
        "recent_records": [],
        "reason": reason,
        "fake_success": False,
    }


def _local_machine_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "has_snapshot": False,
        "environment": {"scope": "unknown"},
        "reason": reason,
        "fake_success": False,
    }


def _independence_default(reason: str) -> dict[str, Any]:
    return {
        "independence_score": 0.0,
        "label": "external_dependent",
        "external_model_needed": True,
        "recommendations": [],
        "signals": {},
        "reason": reason,
        "fake_success": False,
    }


def _artifacts_default(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "total_artifacts": 0,
        "by_type": {},
        "online_ollama_models": 0,
        "reason": reason,
        "fake_success": False,
    }
