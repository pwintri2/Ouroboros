"""Composable status contract for the Ouroboros control surface.

The functions in this module are intentionally dependency-injected and
side-effect light. They can be exercised with fakes and later wired into
``controller.main`` without requiring live Ollama, ChromaDB, or external CLIs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


DEFAULT_MODEL_NAME = "ouroboros"
DEFAULT_ROLES: tuple[str, ...] = ("Developer", "Researcher", "Critic", "Trainer", "Tester")
DEFAULT_EXTERNAL_PROVIDERS: tuple[str, ...] = ("chatgpt", "claude", "gemini", "groq")
PROVIDER_IDS: frozenset[str] = frozenset(("ollama", *DEFAULT_EXTERNAL_PROVIDERS))

ROLE_MODEL_PREFERENCES: dict[str, tuple[str, ...]] = {
    "developer": ("deepseek-coder:latest", "codellama:13b", "devstral:latest", "llama3.2:latest", "llama3:latest"),
    "researcher": ("mistral:latest", "llama3.2:latest", "llama3:latest"),
    "critic": ("mistral:latest", "llama3.2:latest", "llama3:latest"),
    "trainer": ("llama3.2:latest", "mistral:latest", "phi3:latest", "llama3:latest"),
    "tester": ("mistral:latest", "llama3.2:latest", "llama3:latest"),
}


def compose_ouroboros_status(
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    ollama_client: Any = None,
    available_models: Sequence[Any] | None = None,
    active_base: str | None = None,
    role_model_overrides: Mapping[str, str] | None = None,
    roles: Sequence[str] = DEFAULT_ROLES,
    provider_status: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None = None,
    agent_tools: Any = None,
    last_tool_result: Mapping[str, Any] | None = None,
    records: Mapping[str, Any] | None = None,
    geometry_11d: Mapping[str, Any] | None = None,
    browser_research: Mapping[str, Any] | None = None,
    model_state: Mapping[str, Any] | None = None,
    capabilities: Mapping[str, Any] | None = None,
    roo_adapter: Any = None,
    self_modification_pipeline: Mapping[str, Any] | None = None,
    training_events: Sequence[Mapping[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the extended Ouroboros status payload.

    No success is invented here: unknown live systems are reported as
    unavailable/not_run instead of being treated as green.
    """

    models, model_inventory_error = _model_inventory(ollama_client=ollama_client, available_models=available_models)
    state = dict(model_state or {})
    base = _active_base(models=models, requested=active_base, model_state=state, ollama_client=ollama_client)
    model_online = model_name in models
    tool = _last_tool(agent_tools=agent_tools, explicit=last_tool_result)
    normalized_records = _records(records)
    normalized_geometry = _geometry(geometry_11d, normalized_records)
    learning = _learning_11d(normalized_records, normalized_geometry, training_events)
    providers = _external_providers(provider_status)
    role_models = _role_models(
        roles=roles,
        models=models,
        active_base=base,
        overrides=role_model_overrides,
    )
    self_mod = _self_modification(self_modification_pipeline)
    fine_tune = _fine_tune_status(state)

    payload: dict[str, Any] = {
        "status": "online",
        "model": {
            "name": model_name,
            "online": model_online,
            "status": "online" if model_online else "offline",
            "active_base": base,
            "available_bases": models,
            "ollama_online": bool(models),
            "create_flow": dict(state.get("create_flow") or {}),
        },
        "active_base": base,
        "ollama": {
            "online": bool(models),
            "available_models": models,
            "count": len(models),
            "inventory_error": model_inventory_error,
        },
        "role_models": role_models,
        "external_providers": providers,
        "blocked_external_providers": list(providers["blocked"].keys()),
        "roo_adapter": _roo_adapter(roo_adapter),
        "browser_research": dict(
            browser_research
            or {
                "status": "idle",
                "last_query": "",
                "last_url": "",
                "flags": [],
            }
        ),
        "geometry_11d": normalized_geometry,
        "records": normalized_records,
        "learning_11d": learning,
        "last_tool_call": tool,
        "stdout": str(tool.get("stdout", "")),
        "stderr": str(tool.get("stderr") or tool.get("error") or ""),
        "self_modification_pipeline": self_mod,
        "fine_tune": fine_tune,
        "integrity": {
            "fake_fine_tune_success": False,
            "fake_tool_success": False,
            "tool_success_source": "agent_tools.last_tool_result" if tool["status"] != "not_run" else "none",
            "fine_tune_success_source": "none" if fine_tune["status"] != "completed" else fine_tune.get("source", "explicit_pipeline"),
            "claims": [
                "Only local Ollama inventory is listed as model availability.",
                "Tool success mirrors the last real registry result; absent tools are not marked successful.",
                "Fine-tune status is never upgraded from missing state to success.",
            ],
        },
        "learned": "Status gelezen: lokaal model, rolkeuzes, providers, tools en 11D leerstatus zijn gecomposeerd.",
        "mentor": "Geen externe provider, tool-call of fine-tune wordt als gelukt gemarkeerd zonder expliciete statusbron.",
        "next_action": "Create/Refresh Ouroboros Model" if not model_online else "Research Missing Knowledge",
        "capabilities": dict(capabilities or {}),
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _model_inventory(
    *,
    ollama_client: Any,
    available_models: Sequence[Any] | None,
) -> tuple[list[str], str]:
    raw: Sequence[Any]
    error = ""
    if available_models is not None:
        raw = available_models
    else:
        raw = ()
        list_models = getattr(ollama_client, "list_models", None)
        if callable(list_models):
            try:
                raw = list_models() or ()
            except Exception as exc:  # pragma: no cover - exact exception type belongs to dependency.
                error = str(exc)

    names: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            value = item.get("name") or item.get("id") or item.get("model")
        else:
            value = item
        if value:
            text = str(value).strip()
            if text and text not in names:
                names.append(text)
    return names, error


def _active_base(
    *,
    models: Sequence[str],
    requested: str | None,
    model_state: Mapping[str, Any],
    ollama_client: Any,
) -> str:
    for candidate in (
        requested,
        model_state.get("active_base"),
        getattr(ollama_client, "model", None),
        models[0] if models else None,
        "llama3.2:latest",
    ):
        value = str(candidate or "").strip()
        if value and value not in PROVIDER_IDS:
            return value
    return "llama3.2:latest"


def _role_models(
    *,
    roles: Sequence[str],
    models: Sequence[str],
    active_base: str,
    overrides: Mapping[str, str] | None,
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    available = list(models)
    for role in roles:
        role_name = str(role)
        override = _lookup_role_override(overrides or {}, role_name)
        if override:
            model = override
            source = "override"
        else:
            model = _preferred_model_for_role(role_name, available, active_base)
            source = "role_preference" if model in available else "fallback"
        selected[role_name] = {
            "model": model,
            "available": model in available,
            "source": source,
        }
    return selected


def _lookup_role_override(overrides: Mapping[str, str], role: str) -> str:
    lowered = role.casefold()
    for key, value in overrides.items():
        if str(key).casefold() == lowered and str(value or "").strip():
            return str(value).strip()
    return ""


def _preferred_model_for_role(role: str, models: Sequence[str], active_base: str) -> str:
    available = list(models)
    preferences = ROLE_MODEL_PREFERENCES.get(role.casefold(), ())
    for candidate in preferences:
        if candidate in available:
            return candidate
    if active_base:
        return active_base
    return available[0] if available else "llama3.2:latest"


def _external_providers(
    provider_status: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    raw: Mapping[str, Any] = {}
    error = ""
    if callable(provider_status):
        try:
            raw = provider_status() or {}
        except Exception as exc:  # pragma: no cover - exact exception type belongs to dependency.
            error = str(exc)
            raw = {}
    elif isinstance(provider_status, Mapping):
        raw = provider_status

    blocked: dict[str, dict[str, Any]] = {}
    observed: dict[str, dict[str, Any]] = {}
    for provider in DEFAULT_EXTERNAL_PROVIDERS:
        entry = raw.get(provider, {}) if isinstance(raw, Mapping) else {}
        normalized = dict(entry) if isinstance(entry, Mapping) else {"detail": str(entry)}
        available = bool(normalized.get("available"))
        reason = "external_providers_blocked_by_policy"
        if not available:
            reason = str(normalized.get("reason") or normalized.get("version") or "provider_unavailable")
        if error and provider not in raw:
            reason = f"provider_status_unavailable: {error}"
        observed[provider] = {
            **normalized,
            "available": available,
            "blocked": True,
            "reason": reason,
        }
        blocked[provider] = observed[provider]
    return {
        "policy": "blocked_by_default",
        "available": {},
        "blocked": blocked,
        "observed": observed,
    }


def _roo_adapter(roo_adapter: Any) -> dict[str, Any]:
    if roo_adapter is None:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "roo_adapter_not_configured",
        }
    if isinstance(roo_adapter, Mapping):
        available = bool(roo_adapter.get("available"))
        return {
            **dict(roo_adapter),
            "available": available,
            "status": str(roo_adapter.get("status") or ("available" if available else "unavailable")),
            "reason": str(roo_adapter.get("reason") or ("" if available else "roo_adapter_not_configured")),
        }
    return {
        "available": True,
        "status": "available",
        "adapter": roo_adapter.__class__.__name__,
        "reason": "",
    }


def _last_tool(agent_tools: Any, explicit: Mapping[str, Any] | None) -> dict[str, Any]:
    raw: Mapping[str, Any] | None = explicit
    if raw is None and agent_tools is not None:
        raw = getattr(agent_tools, "last_tool_result", None)
        if raw is None:
            status = getattr(agent_tools, "status", None)
            if callable(status):
                try:
                    registry_status = status() or {}
                    if isinstance(registry_status, Mapping):
                        maybe_tool = registry_status.get("last_tool_result")
                        raw = maybe_tool if isinstance(maybe_tool, Mapping) else None
                except Exception:
                    raw = None
    if not isinstance(raw, Mapping) or not raw:
        return {
            "tool_name": "",
            "status": "not_run",
            "stdout": "",
            "stderr": "",
            "error": "",
            "stored_to_memory": False,
        }
    return {
        "tool_name": str(raw.get("tool_name") or ""),
        "status": str(raw.get("status") or "unknown"),
        "stdout": str(raw.get("stdout") or ""),
        "stderr": str(raw.get("stderr") or raw.get("error") or ""),
        "error": str(raw.get("error") or ""),
        "stored_to_memory": bool(raw.get("stored_to_memory")),
        "approval_status": str(raw.get("approval_status") or ""),
    }


def _records(records: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(records or {})
    main_count = _int(source.get("main_collection_count"), 0)
    training_count = _int(source.get("training_collection_count"), 0)
    total = _int(source.get("total_count"), main_count + training_count)
    return {
        "main_collection_count": main_count,
        "training_collection_count": training_count,
        "total_count": total,
        "recent_training_ids": list(source.get("recent_training_ids") or []),
        "recent_training_metadatas": list(source.get("recent_training_metadatas") or []),
        "recent_training_documents": list(source.get("recent_training_documents") or []),
    }


def _geometry(geometry_11d: Mapping[str, Any] | None, records: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(geometry_11d or {})
    oppervlakte = _float(source.get("oppervlakte", source.get("surface_area")), 0.0)
    return {
        "dimension_count": _int(source.get("dimension_count"), 11),
        "dream_hz": round(_float(source.get("dream_hz"), 422.0), 6),
        "radius": round(_float(source.get("radius"), 0.0), 6),
        "volume": round(_float(source.get("volume"), 0.0), 6),
        "oppervlakte": round(oppervlakte, 6),
        "surface_area": round(_float(source.get("surface_area"), oppervlakte), 6),
        "record_count": _int(source.get("record_count"), _int(records.get("total_count"), 0)),
    }


def _learning_11d(
    records: Mapping[str, Any],
    geometry: Mapping[str, Any],
    training_events: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    total = _int(records.get("total_count"), 0)
    training_count = _int(records.get("training_collection_count"), 0)
    has_metadata = bool(records.get("recent_training_metadatas"))
    available = total > 0 or training_count > 0 or has_metadata
    if not available:
        status = "unavailable"
    elif training_count == 0:
        status = "available_empty_training"
    else:
        status = "learning"
    events = list(training_events or [])
    return {
        "status": status,
        "chromadb": {
            "available": available,
            "main_collection_count": _int(records.get("main_collection_count"), 0),
            "training_collection_count": training_count,
            "total_count": total,
        },
        "geometry": dict(geometry),
        "recent_training_ids": list(records.get("recent_training_ids") or []),
        "last_event": dict(events[-1]) if events else None,
        "fake_store_success": False,
    }


def _self_modification(pipeline: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(pipeline, Mapping) and pipeline:
        result = dict(pipeline)
        result.setdefault("status", "unknown")
        result.setdefault("approval_required", True)
        result.setdefault("fake_success", False)
        return result
    return {
        "status": "not_configured",
        "approval_required": True,
        "stages": [
            {"name": "proposal", "status": "idle"},
            {"name": "patch", "status": "idle"},
            {"name": "tests", "status": "idle"},
            {"name": "approval", "status": "required"},
        ],
        "last_run": None,
        "fake_success": False,
    }


def _fine_tune_status(model_state: Mapping[str, Any]) -> dict[str, Any]:
    raw = model_state.get("fine_tune") if isinstance(model_state, Mapping) else None
    if isinstance(raw, Mapping) and raw:
        result = dict(raw)
        result.setdefault("status", "unknown")
        result.setdefault("fake_success", False)
        return result
    return {
        "status": "not_configured",
        "method": "none",
        "last_run": None,
        "fake_success": False,
    }


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
