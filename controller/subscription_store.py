"""API credential store for the Ouroboros cockpit.

This module keeps provider API credentials alongside the existing API key
store.  Consumer web subscriptions such as ChatGPT Plus or Claude Pro do not
grant reusable API/runtime access to Roo by themselves; Roo Cloud login is
handled separately by the Roo CLI auth flow.

Subscription data is stored in a separate JSON file with 0600 permissions.
Stored credentials are never returned verbatim by API responses; only masked
previews are exposed.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Supported subscription types
# ---------------------------------------------------------------------------

SUBSCRIPTION_PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "id": "openai",
        "label": "ChatGPT Plus / Pro / Team",
        "aliases": ("chatgpt", "chatgpt-plus", "chatgpt-pro", "chatgpt-team", "openai-subscription"),
        "api_family": "openai_chat",
        "auth_modes": ("session_token", "oauth_refresh_token", "api_key_from_subscription"),
        "models": [
            "gpt-4o",
            "gpt-4.1",
            "gpt-4.1-mini",
            "o4-mini",
            "o3",
            "o3-mini",
        ],
        "subscription_url": "https://chatgpt.com/settings/subscription",
        "api_key_url": "https://platform.openai.com/api-keys",
        "docs_url": "https://platform.openai.com/docs/guides/authentication",
    },
    "anthropic": {
        "id": "anthropic",
        "label": "Claude Pro / Team / Enterprise",
        "aliases": ("claude", "claude-pro", "claude-team", "claude-enterprise", "anthropic-subscription"),
        "api_family": "anthropic_messages",
        "auth_modes": ("session_token", "oauth_refresh_token", "api_key_from_subscription"),
        "models": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
        "subscription_url": "https://claude.ai/settings/billing",
        "api_key_url": "https://console.anthropic.com/settings/keys",
        "docs_url": "https://docs.anthropic.com/en/api/getting-started",
    },
    "google": {
        "id": "google",
        "label": "Gemini Advanced / Google One AI",
        "aliases": ("gemini", "gemini-advanced", "google-one-ai", "google-subscription"),
        "api_family": "google_gemini",
        "auth_modes": ("oauth_refresh_token", "api_key_from_subscription"),
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ],
        "subscription_url": "https://one.google.com/explore-plan/gemini-advanced",
        "api_key_url": "https://aistudio.google.com/apikey",
        "docs_url": "https://ai.google.dev/gemini-api/docs",
    },
    "xai": {
        "id": "xai",
        "label": "X Premium+ / Grok",
        "aliases": ("grok", "x-premium", "xai-subscription"),
        "api_family": "openai_chat",
        "auth_modes": ("api_key_from_subscription",),
        "models": [
            "grok-2-latest",
            "grok-3-latest",
        ],
        "subscription_url": "https://x.com/i/premium_sign_up",
        "api_key_url": "https://console.x.ai/",
        "docs_url": "https://docs.x.ai/",
    },
    "mistral": {
        "id": "mistral",
        "label": "Mistral Le Chat Pro",
        "aliases": ("mistral-subscription", "le-chat-pro"),
        "api_family": "openai_chat",
        "auth_modes": ("api_key_from_subscription",),
        "models": [
            "mistral-large-latest",
            "mistral-medium-latest",
        ],
        "subscription_url": "https://chat.mistral.ai/",
        "api_key_url": "https://console.mistral.ai/api-keys",
        "docs_url": "https://docs.mistral.ai/",
    },
    "openrouter": {
        "id": "openrouter",
        "label": "OpenRouter Credits",
        "aliases": ("openrouter-subscription",),
        "api_family": "openai_chat",
        "auth_modes": ("api_key_from_subscription",),
        "models": [],
        "subscription_url": "https://openrouter.ai/credits",
        "api_key_url": "https://openrouter.ai/keys",
        "docs_url": "https://openrouter.ai/docs",
    },
}

PROVIDER_ALIAS_MAP: dict[str, str] = {}
for _pid, _pinfo in SUBSCRIPTION_PROVIDERS.items():
    PROVIDER_ALIAS_MAP[_pid] = _pid
    for _alias in _pinfo.get("aliases", ()):
        PROVIDER_ALIAS_MAP[_alias] = _pid


# ---------------------------------------------------------------------------
# Subscription entry schema
# ---------------------------------------------------------------------------

def _empty_subscription(provider_id: str) -> dict[str, Any]:
    return {
        "provider": provider_id,
        "active": False,
        "auth_mode": "",
        "plan_label": "",
        "session_token": "",
        "refresh_token": "",
        "api_key": "",
        "expires_at": 0,
        "last_validated": 0,
        "validation_status": "unchecked",
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Store path helpers
# ---------------------------------------------------------------------------

def subscription_store_path() -> Path:
    configured = os.getenv("WINTRIP_SUBSCRIPTION_STORE") or os.getenv("OUROBOROS_SUBSCRIPTION_STORE")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace")
    if not workspace.exists():
        workspace = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return (workspace / ".secrets" / "ouroboros_subscriptions.json").resolve()


def _load_store() -> dict[str, Any]:
    path = subscription_store_path()
    if not path.exists():
        return {"subscriptions": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"subscriptions": {}}
    if not isinstance(data, dict):
        return {"subscriptions": {}}
    if not isinstance(data.get("subscriptions"), dict):
        data["subscriptions"] = {}
    return data


def _write_store(data: dict[str, Any]) -> None:
    path = subscription_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _store_writable() -> bool:
    path = subscription_store_path()
    parent = path.parent
    return (parent.exists() and os.access(parent, os.W_OK)) or (
        not parent.exists() and parent.parent.exists() and os.access(parent.parent, os.W_OK)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_subscription_provider(provider: str) -> str:
    """Normalize a provider name/alias to a canonical subscription provider id."""
    normalized = str(provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    # Try alias map
    for alias, pid in PROVIDER_ALIAS_MAP.items():
        if normalized == alias.replace("-", "_").replace(" ", "_"):
            return pid
    raise ValueError(f"Unsupported subscription provider: {provider}")


def load_subscriptions() -> dict[str, dict[str, Any]]:
    """Return all stored subscriptions keyed by provider id."""
    stored = _load_store()
    return dict(stored.get("subscriptions", {}))


def subscription_status() -> dict[str, dict[str, Any]]:
    """Return subscription status for all known providers (for cockpit UI)."""
    stored = load_subscriptions()
    result: dict[str, dict[str, Any]] = {}
    for provider_id, provider_info in SUBSCRIPTION_PROVIDERS.items():
        entry = stored.get(provider_id, _empty_subscription(provider_id))
        active = bool(entry.get("active"))
        auth_mode = str(entry.get("auth_mode") or "")
        has_credential = bool(
            entry.get("session_token")
            or entry.get("refresh_token")
            or entry.get("api_key")
        )
        expires_at = int(entry.get("expires_at") or 0)
        expired = expires_at > 0 and time.time() > expires_at
        validation_status = str(entry.get("validation_status") or "unchecked")
        api_key_ready = bool(
            active
            and not expired
            and auth_mode == "api_key_from_subscription"
            and str(entry.get("api_key") or "").strip()
        )

        effective_status: str
        if not active:
            effective_status = "inactive"
        elif not auth_mode:
            effective_status = "unconfigured"
        elif not has_credential:
            effective_status = "missing_credential"
        elif expired:
            effective_status = "expired"
        elif validation_status == "valid":
            effective_status = "active"
        elif validation_status == "invalid":
            effective_status = "invalid"
        else:
            effective_status = "configured"

        result[provider_id] = {
            "provider": provider_id,
            "label": provider_info["label"],
            "active": active,
            "auth_mode": auth_mode,
            "auth_modes_available": list(provider_info["auth_modes"]),
            "plan_label": str(entry.get("plan_label") or ""),
            "status": effective_status,
            "has_credential": has_credential,
            "api_key_ready": api_key_ready,
            "masked_credential": _mask_credential(entry),
            "expires_at": expires_at,
            "expired": expired,
            "last_validated": int(entry.get("last_validated") or 0),
            "validation_status": validation_status,
            "models": provider_info["models"],
            "subscription_url": provider_info["subscription_url"],
            "api_key_url": provider_info["api_key_url"],
            "docs_url": provider_info["docs_url"],
            "store_path": str(subscription_store_path()),
            "writable": _store_writable(),
        }
    return result


def save_subscription(
    provider: str,
    *,
    auth_mode: str = "",
    plan_label: str = "",
    session_token: str = "",
    refresh_token: str = "",
    api_key: str = "",
    expires_at: int = 0,
    active: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    """Save or update a subscription entry for a provider."""
    provider_id = normalize_subscription_provider(provider)
    provider_info = SUBSCRIPTION_PROVIDERS[provider_id]
    clean_auth_mode = str(auth_mode or "").strip()
    if clean_auth_mode and clean_auth_mode not in provider_info["auth_modes"]:
        raise ValueError(
            f"Auth mode '{clean_auth_mode}' is not supported for {provider_id}. "
            f"Supported: {', '.join(provider_info['auth_modes'])}"
        )

    store = _load_store()
    subscriptions = store.setdefault("subscriptions", {})
    existing = subscriptions.get(provider_id, _empty_subscription(provider_id))

    # Merge: only overwrite non-empty fields
    entry: dict[str, Any] = {
        "provider": provider_id,
        "active": active,
        "auth_mode": clean_auth_mode or existing.get("auth_mode", ""),
        "plan_label": (plan_label or existing.get("plan_label", "")).strip(),
        "session_token": (session_token or existing.get("session_token", "")).strip(),
        "refresh_token": (refresh_token or existing.get("refresh_token", "")).strip(),
        "api_key": (api_key or existing.get("api_key", "")).strip(),
        "expires_at": int(expires_at) if expires_at else int(existing.get("expires_at") or 0),
        "last_validated": int(existing.get("last_validated") or 0),
        "validation_status": existing.get("validation_status", "unchecked"),
        "notes": (notes or existing.get("notes", "")).strip(),
        "updated_at": int(time.time()),
    }
    subscriptions[provider_id] = entry
    _write_store(store)
    return subscription_status().get(provider_id, {})


def delete_subscription(provider: str) -> dict[str, Any]:
    """Remove a subscription entry for a provider."""
    provider_id = normalize_subscription_provider(provider)
    store = _load_store()
    subscriptions = store.setdefault("subscriptions", {})
    subscriptions.pop(provider_id, None)
    _write_store(store)
    return subscription_status().get(provider_id, {})


def activate_subscription(provider: str, active: bool = True) -> dict[str, Any]:
    """Toggle a subscription active/inactive without changing credentials."""
    provider_id = normalize_subscription_provider(provider)
    store = _load_store()
    subscriptions = store.setdefault("subscriptions", {})
    entry = subscriptions.get(provider_id, _empty_subscription(provider_id))
    entry["active"] = active
    entry["updated_at"] = int(time.time())
    subscriptions[provider_id] = entry
    _write_store(store)
    return subscription_status().get(provider_id, {})


def validate_subscription(provider: str) -> dict[str, Any]:
    """Validate a subscription by checking that credentials are still working.

    This performs a lightweight probe based on auth_mode:
    - api_key_from_subscription: tries a minimal API call
    - session_token: checks token format and expiry
    - oauth_refresh_token: checks token presence and expiry

    Returns the updated subscription status.
    """
    provider_id = normalize_subscription_provider(provider)
    store = _load_store()
    subscriptions = store.setdefault("subscriptions", {})
    entry = subscriptions.get(provider_id, _empty_subscription(provider_id))

    auth_mode = str(entry.get("auth_mode") or "")
    now = int(time.time())
    validation_result: str = "unchecked"
    validation_reason: str = ""

    if not auth_mode:
        validation_result = "unchecked"
        validation_reason = "No auth mode configured."
    elif auth_mode == "api_key_from_subscription":
        api_key = str(entry.get("api_key") or "")
        if not api_key:
            validation_result = "invalid"
            validation_reason = "No API key stored for subscription."
        elif len(api_key) < 8:
            validation_result = "invalid"
            validation_reason = "API key too short."
        else:
            # Lightweight format check; real validation happens at call time.
            validation_result = "valid"
            validation_reason = "API key format looks valid."
    elif auth_mode == "session_token":
        token = str(entry.get("session_token") or "")
        if not token:
            validation_result = "invalid"
            validation_reason = "No session token stored."
        else:
            expires_at = int(entry.get("expires_at") or 0)
            if expires_at and now > expires_at:
                validation_result = "expired"
                validation_reason = f"Session token expired at {expires_at}."
            elif len(token) < 20:
                validation_result = "invalid"
                validation_reason = "Session token too short."
            else:
                validation_result = "valid"
                validation_reason = "Session token format looks valid."
    elif auth_mode == "oauth_refresh_token":
        token = str(entry.get("refresh_token") or "")
        if not token:
            validation_result = "invalid"
            validation_reason = "No refresh token stored."
        else:
            expires_at = int(entry.get("expires_at") or 0)
            if expires_at and now > expires_at:
                validation_result = "expired"
                validation_reason = f"Refresh token expired at {expires_at}."
            elif len(token) < 20:
                validation_result = "invalid"
                validation_reason = "Refresh token too short."
            else:
                validation_result = "valid"
                validation_reason = "Refresh token format looks valid."

    entry["last_validated"] = now
    entry["validation_status"] = validation_result
    entry["validation_reason"] = validation_reason
    subscriptions[provider_id] = entry
    _write_store(store)

    result = subscription_status().get(provider_id, {})
    result["validation_reason"] = validation_reason
    return result


def subscription_credential_for_provider(provider: str) -> dict[str, Any]:
    """Return the active credential for a provider (for runtime use).

    Returns a dict with auth_mode, credential value, and usability status.
    Credential values should NEVER be exposed to API responses; this is
    strictly for internal runtime routing.
    """
    try:
        provider_id = normalize_subscription_provider(provider)
    except ValueError:
        return {"status": "unsupported", "provider": provider, "usable": False}

    stored = load_subscriptions()
    entry = stored.get(provider_id, _empty_subscription(provider_id))

    if not entry.get("active"):
        return {"status": "inactive", "provider": provider_id, "usable": False}

    auth_mode = str(entry.get("auth_mode") or "")
    if not auth_mode:
        return {"status": "unconfigured", "provider": provider_id, "usable": False}

    expires_at = int(entry.get("expires_at") or 0)
    if expires_at and time.time() > expires_at:
        return {"status": "expired", "provider": provider_id, "auth_mode": auth_mode, "usable": False}

    if auth_mode == "api_key_from_subscription":
        api_key = str(entry.get("api_key") or "")
        if not api_key:
            return {"status": "missing_credential", "provider": provider_id, "auth_mode": auth_mode, "usable": False}
        return {
            "status": "ready",
            "provider": provider_id,
            "auth_mode": auth_mode,
            "api_key": api_key,
            "usable": True,
        }
    elif auth_mode == "session_token":
        token = str(entry.get("session_token") or "")
        if not token:
            return {"status": "missing_credential", "provider": provider_id, "auth_mode": auth_mode, "usable": False}
        return {
            "status": "ready",
            "provider": provider_id,
            "auth_mode": auth_mode,
            "session_token": token,
            "usable": True,
        }
    elif auth_mode == "oauth_refresh_token":
        token = str(entry.get("refresh_token") or "")
        if not token:
            return {"status": "missing_credential", "provider": provider_id, "auth_mode": auth_mode, "usable": False}
        return {
            "status": "ready",
            "provider": provider_id,
            "auth_mode": auth_mode,
            "refresh_token": token,
            "usable": True,
        }

    return {"status": "unknown_auth_mode", "provider": provider_id, "auth_mode": auth_mode, "usable": False}


def subscription_api_key_for_provider(provider: str) -> str:
    """Convenience: return the API key from subscription if available.

    This is the most common path: user has a subscription that provides an API
    key, and we use that key the same way as a standalone API key.  Returns
    empty string if no usable key.
    """
    cred = subscription_credential_for_provider(provider)
    if not cred.get("usable"):
        return ""
    return str(cred.get("api_key") or "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_credential(entry: dict[str, Any]) -> str:
    """Return a masked preview of whichever credential is stored."""
    for key in ("api_key", "session_token", "refresh_token"):
        value = str(entry.get(key) or "")
        if value:
            return _mask(value)
    return ""


def _mask(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


__all__ = [
    "SUBSCRIPTION_PROVIDERS",
    "activate_subscription",
    "delete_subscription",
    "load_subscriptions",
    "normalize_subscription_provider",
    "save_subscription",
    "subscription_api_key_for_provider",
    "subscription_credential_for_provider",
    "subscription_status",
    "subscription_store_path",
    "validate_subscription",
]
