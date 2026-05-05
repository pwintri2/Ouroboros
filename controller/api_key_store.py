"""Local provider API key store for the Ouroboros cockpit.

Keys are never returned by API responses. The store is a small JSON file with
0600 permissions so the backend can route model calls without requiring keys in
the UI on every request.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROVIDER_ALIASES: dict[str, str] = {
    "openai": "openai",
    "chatgpt": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "gemini": "google",
    "xai": "xai",
    "grok": "xai",
    "mistral": "mistral",
    "brave": "brave",
    "brave_search": "brave",
}

PROVIDER_KEY_ENVS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "xai": ("XAI_API_KEY", "GROK_API_KEY"),
    "mistral": ("MISTRAL_API_KEY",),
    "brave": ("BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"),
}


def normalize_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower().replace("-", "_")
    if normalized not in PROVIDER_ALIASES:
        raise ValueError(f"Unsupported provider: {provider}")
    return PROVIDER_ALIASES[normalized]


def key_store_path() -> Path:
    configured = os.getenv("WINTRIP_API_KEY_STORE") or os.getenv("OUROBOROS_API_KEY_STORE")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace")
    if not workspace.exists():
        workspace = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return (workspace / ".secrets" / "ouroboros_api_keys.json").resolve()


def load_provider_api_keys() -> dict[str, str]:
    stored = _load_store()
    keys: dict[str, str] = {}
    for provider, env_names in PROVIDER_KEY_ENVS.items():
        env_value = next((os.getenv(name) for name in env_names if os.getenv(name)), None)
        store_value = str(stored.get("providers", {}).get(provider, {}).get("api_key") or "")
        value = env_value or store_value
        if value:
            keys[provider] = value
    return keys


def provider_key_status() -> dict[str, dict[str, Any]]:
    stored = _load_store()
    loaded = load_provider_api_keys()
    status: dict[str, dict[str, Any]] = {}
    for provider, env_names in PROVIDER_KEY_ENVS.items():
        env_configured = any(bool(os.getenv(name)) for name in env_names)
        store_value = str(stored.get("providers", {}).get(provider, {}).get("api_key") or "")
        configured = provider in loaded
        source = "env" if env_configured else ("store" if store_value else "missing")
        status[provider] = {
            "provider": provider,
            "configured": configured,
            "source": source,
            "required_key_env": list(env_names),
            "masked": _mask_key(loaded.get(provider, "")),
            "store_path": str(key_store_path()),
            "writable": _store_writable(),
        }
    return status


def save_provider_api_key(provider: str, api_key: str) -> dict[str, Any]:
    provider_id = normalize_provider(provider)
    cleaned = str(api_key or "").strip()
    if len(cleaned) < 8:
        raise ValueError("API key is too short.")

    store = _load_store()
    providers = store.setdefault("providers", {})
    providers[provider_id] = {"api_key": cleaned}
    _write_store(store)
    return provider_key_status()[provider_id]


def delete_provider_api_key(provider: str) -> dict[str, Any]:
    provider_id = normalize_provider(provider)
    store = _load_store()
    providers = store.setdefault("providers", {})
    providers.pop(provider_id, None)
    _write_store(store)
    return provider_key_status()[provider_id]


def _load_store() -> dict[str, Any]:
    path = key_store_path()
    if not path.exists():
        return {"providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"providers": {}}
    if not isinstance(data, dict):
        return {"providers": {}}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        data["providers"] = {}
    return data


def _write_store(data: dict[str, Any]) -> None:
    path = key_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _store_writable() -> bool:
    path = key_store_path()
    parent = path.parent
    return parent.exists() and os.access(parent, os.W_OK) or (not parent.exists() and os.access(parent.parent, os.W_OK))


def _mask_key(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"
