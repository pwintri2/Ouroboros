"""Pure local Ollama model routing with a strict allowlist.

This module intentionally does not call Ollama or any external API. Pass a
``list_models`` callable or iterable when live availability should influence
selection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable


ALLOWED_OLLAMA_MODELS: tuple[str, ...] = (
    "deepseek-coder:latest",
    "llama2-uncensored:latest",
    "devstral:latest",
    "llama3.2:latest",
    "mistral:latest",
    "codellama:13b",
    "llama3:8b",
    "llama3:latest",
    "gemma4:latest",
    "phi3:latest",
)

_ALLOWED_MODEL_SET = frozenset(ALLOWED_OLLAMA_MODELS)

MODEL_ALIASES: dict[str, str] = {
    "deepseek-coder": "deepseek-coder:latest",
    "llama2-uncensored": "llama2-uncensored:latest",
    "devstral": "devstral:latest",
    "llama3.2": "llama3.2:latest",
    "llama3.1": "llama3.2:latest",
    "llama3.1:latest": "llama3.2:latest",
    "llama-3.1": "llama3.2:latest",
    "Llama-3.1": "llama3.2:latest",
    "mistral": "mistral:latest",
    "codellama": "codellama:13b",
    "llama3": "llama3:latest",
    "gemma4": "gemma4:latest",
    "phi3": "phi3:latest",
}

CODE_MODEL_PREFERENCES: tuple[str, ...] = (
    "deepseek-coder:latest",
    "codellama:13b",
    "devstral:latest",
)
QUICK_MODEL_PREFERENCES: tuple[str, ...] = (
    "phi3:latest",
    "mistral:latest",
    "llama3.2:latest",
)
CRITIC_MODEL_PREFERENCES: tuple[str, ...] = (
    "mistral:latest",
    "llama3.2:latest",
    "llama3:latest",
)
DEFAULT_MODEL_PREFERENCES: tuple[str, ...] = (
    "llama3.2:latest",
    "llama3:latest",
    "mistral:latest",
    "phi3:latest",
)

ROLE_MODEL_PREFERENCES: dict[str, tuple[str, ...]] = {
    "self_modification": CODE_MODEL_PREFERENCES,
    "code": CODE_MODEL_PREFERENCES,
    "architecture": ("devstral:latest", "gemma4:latest"),
    "reasoning": ("devstral:latest", "gemma4:latest"),
    "quick": ("phi3:latest", "llama3:8b"),
    "routing": ("phi3:latest", "llama3:8b"),
    "internal": QUICK_MODEL_PREFERENCES,
    "critic": CRITIC_MODEL_PREFERENCES,
    "test": CRITIC_MODEL_PREFERENCES,
    "research": CRITIC_MODEL_PREFERENCES,
    "default": DEFAULT_MODEL_PREFERENCES,
}

DEFAULT_OLLAMA_MODEL = DEFAULT_MODEL_PREFERENCES[0]

_ROLE_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "self_modification",
            "self-modification",
            "self modification",
            "code",
            "coder",
            "developer",
            "dev",
        ),
        "code",
    ),
    (("quick", "internal", "fast", "small"), "quick"),
    (("critic", "critique", "review", "test", "tester", "research", "researcher"), "critic"),
)


@dataclass(frozen=True)
class OllamaModelRoute:
    """Selection details for status endpoints and focused tests."""

    selected: str
    role: str
    requested: str
    preferences: tuple[str, ...]
    available_models: tuple[str, ...]
    reason: str


def resolve_model_name(model: str | None) -> str:
    """Return a canonical Ollama model name, or an empty string for no request."""

    if model is None:
        return ""
    clean = str(model).strip()
    if not clean:
        return ""
    return MODEL_ALIASES.get(clean, clean)


def is_allowed_model(model: str | None) -> bool:
    return resolve_model_name(model) in _ALLOWED_MODEL_SET


def normalize_role(role: str | None = "") -> str:
    """Map user/system role hints to one of the router's canonical roles."""

    if not role:
        return "default"
    text = str(role).strip().lower()
    if text in {"self_modification", "code"}:
        return "code"
    if text in {"architecture", "reasoning"}:
        return "architecture"
    if text in {"quick", "internal", "routing"}:
        return "quick"
    if text in {"critic", "test", "research"}:
        return "critic"
    if text == "default":
        return "default"

    compact = re.sub(r"[\s_-]+", "_", text)
    for aliases, canonical in _ROLE_ALIASES:
        if any(alias in text or alias.replace("-", "_") in compact for alias in aliases):
            return canonical
    return "default"


def _extract_model_name(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("name") or item.get("model") or item.get("id")
    else:
        value = item
    return resolve_model_name(str(value)) if value else ""


def allowed_available_models(models: Iterable[Any] | None) -> tuple[str, ...]:
    """Normalize, deduplicate, and filter model names to the allowlist."""

    if not models:
        return ()
    names: list[str] = []
    seen: set[str] = set()
    for item in models:
        name = _extract_model_name(item)
        if name in _ALLOWED_MODEL_SET and name not in seen:
            names.append(name)
            seen.add(name)
    return tuple(names)


def load_allowed_models(list_models: Callable[[], Iterable[Any]] | Iterable[Any] | None = None) -> tuple[str, ...]:
    """Load available models through injection, never by making network calls here."""

    if list_models is None:
        return ()
    try:
        models = list_models() if callable(list_models) else list_models
    except Exception:
        return ()
    return allowed_available_models(models)


def route_ollama_model(
    requested: str | None = None,
    role: str | None = "",
    list_models: Callable[[], Iterable[Any]] | Iterable[Any] | None = None,
) -> OllamaModelRoute:
    """Select one allowed local model for the requested role.

    Availability is optional. If no injected availability is available, the
    router still returns the first allowed preference for the role so callers
    can build deterministic local Ollama payloads.
    """

    available = load_allowed_models(list_models)
    canonical_role = normalize_role(role)
    preferences = ROLE_MODEL_PREFERENCES.get(canonical_role, DEFAULT_MODEL_PREFERENCES)
    requested_model = resolve_model_name(requested)

    if requested_model in _ALLOWED_MODEL_SET:
        if not available or requested_model in available:
            return OllamaModelRoute(
                selected=requested_model,
                role=canonical_role,
                requested=requested_model,
                preferences=preferences,
                available_models=available,
                reason="requested_allowed",
            )
        reason = "requested_allowed_but_unavailable"
    elif requested_model:
        reason = "requested_not_allowed"
    else:
        reason = "role_preference"

    if available:
        for candidate in preferences:
            if candidate in available:
                return OllamaModelRoute(
                    selected=candidate,
                    role=canonical_role,
                    requested=requested_model,
                    preferences=preferences,
                    available_models=available,
                    reason=reason,
                )
        for candidate in DEFAULT_MODEL_PREFERENCES:
            if candidate in available:
                return OllamaModelRoute(
                    selected=candidate,
                    role=canonical_role,
                    requested=requested_model,
                    preferences=preferences,
                    available_models=available,
                    reason="default_available_fallback",
                )
        return OllamaModelRoute(
            selected=available[0],
            role=canonical_role,
            requested=requested_model,
            preferences=preferences,
            available_models=available,
            reason="first_allowed_available",
        )

    return OllamaModelRoute(
        selected=preferences[0] if preferences else DEFAULT_OLLAMA_MODEL,
        role=canonical_role,
        requested=requested_model,
        preferences=preferences,
        available_models=available,
        reason=reason,
    )


def select_ollama_model(
    requested: str | None = None,
    role: str | None = "",
    list_models: Callable[[], Iterable[Any]] | Iterable[Any] | None = None,
) -> str:
    return route_ollama_model(requested=requested, role=role, list_models=list_models).selected


def ollama_router_status(
    list_models: Callable[[], Iterable[Any]] | Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Small status payload ready for future /api/ouroboros/status expansion."""

    available = load_allowed_models(list_models)
    return {
        "allowed_models": list(ALLOWED_OLLAMA_MODELS),
        "available_models": list(available),
        "roles": {role: list(models) for role, models in ROLE_MODEL_PREFERENCES.items()},
        "selected_by_role": {
            role: route_ollama_model(role=role, list_models=available).selected
            for role in ROLE_MODEL_PREFERENCES
        },
        "default_model": DEFAULT_OLLAMA_MODEL,
        "local_only": True,
    }
