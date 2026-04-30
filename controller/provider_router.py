"""Disabled external provider router for backend-first Ouroboros.

The previous implementation invoked local CLI wrappers for cloud providers.
Ouroboros phase 1 keeps the agent-machine local-only: imports remain
compatible, but Gemini/Claude/Groq execution is explicitly unavailable.
"""

from __future__ import annotations

from typing import Any, Optional


GEMINI_MODELS = ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
CLAUDE_MODELS = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
GROQ_MODELS = ["llama-3.3-70b-versatile"]

DISABLED_EXTERNAL_PROVIDER_STATUS = "disabled_external_provider"
DISABLED_EXTERNAL_PROVIDERS: tuple[str, ...] = ("gemini", "claude", "groq", "chatgpt")
_PROVIDER_MODELS = {
    "gemini": GEMINI_MODELS,
    "claude": CLAUDE_MODELS,
    "groq": GROQ_MODELS,
    "chatgpt": [],
}
_PROVIDER_TRANSPORTS = {
    "gemini": "cli",
    "claude": "cli",
    "groq": "cloud_api",
    "chatgpt": "external_app",
}


def disabled_provider_status(
    provider: str,
    model: str = "",
    transport: Optional[str] = None,
) -> dict[str, Any]:
    name = str(provider or "external").lower()
    models = list(_PROVIDER_MODELS.get(name, []))
    target_model = model or (models[0] if models else "")
    transport_id = transport or _PROVIDER_TRANSPORTS.get(name, "external")
    reason = (
        "Ouroboros draait backend-first lokaal via Ollama; externe/cloud "
        "provider-uitvoering is disabled/legacy en geisoleerd."
    )
    message = (
        f"{DISABLED_EXTERNAL_PROVIDER_STATUS}: provider '{name}' is disabled/legacy; "
        f"no {transport_id} call was made."
    )
    return {
        "provider": name,
        "model": target_model,
        "models": models,
        "available": False,
        "enabled": False,
        "legacy": True,
        "status": DISABLED_EXTERNAL_PROVIDER_STATUS,
        "transport": transport_id,
        "local_only": True,
        "reason": reason,
        "message": message,
        "next_action": "Gebruik een lokaal Ollama-model via de Ouroboros modelrouter.",
    }


def disabled_external_provider_payload(
    provider: str,
    model: Optional[str] = None,
    transport: Optional[str] = None,
) -> dict[str, Any]:
    return disabled_provider_status(provider, model=model or "", transport=transport)


def disabled_provider_response(provider: str, model: str = "") -> str:
    status = disabled_provider_status(provider, model=model)
    return f"[{DISABLED_EXTERNAL_PROVIDER_STATUS}:{status['provider']}] {status['message']}"


def _run(cmd: list, timeout: int = 90) -> str:
    """Legacy compatibility shim: never execute CLI commands."""
    provider = cmd[0] if cmd else "external_cli"
    return disabled_provider_response(provider)


def route_gemini(
    prompt: str,
    model: str = "gemini-2.5-pro",
    system_prompt: Optional[str] = None,
) -> str:
    return disabled_provider_response("gemini", model=model)


def route_claude(
    prompt: str,
    model: str = "claude-opus-4-6",
    system_prompt: Optional[str] = None,
) -> str:
    return disabled_provider_response("claude", model=model)


def route_groq(
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    system_prompt: Optional[str] = None,
) -> str:
    return disabled_provider_response("groq", model=model)


def check_providers() -> dict[str, dict[str, Any]]:
    return {
        provider: disabled_provider_status(provider)
        for provider in DISABLED_EXTERNAL_PROVIDERS
    }


def disabled_external_providers() -> dict[str, dict[str, Any]]:
    return check_providers()
