from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .tool_registry import normalized_tools


DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "ouroboros:latest"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_slug(value: str, fallback: str = "persona") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-").lower()
    return (text[:80] or fallback).strip(".-") or fallback


def default_model_settings(name: str = DEFAULT_MODEL) -> dict[str, Any]:
    return {
        "provider": DEFAULT_PROVIDER,
        "name": name or DEFAULT_MODEL,
        "temperature": 0.7,
        "max_tokens": 2000,
        "fallback_model": DEFAULT_MODEL,
    }


def default_memory_settings(enabled: bool = True) -> dict[str, Any]:
    return {"enabled": enabled, "scope": "persona"}


def default_persona() -> dict[str, Any]:
    stamp = now_iso()
    return {
        "id": "ouroboros",
        "name": "Ouroboros",
        "description": "Local-first, practical Ouroboros chat persona.",
        "avatar": {"kind": "initials", "color": "#7bdcc3"},
        "role": "Local Ouroboros assistant",
        "introduction": "Ik ben Ouroboros, je lokale assistent.",
        "instructions": "Keep behavior practical, auditable, reversible, and safe.",
        "system_prompt": "Keep behavior practical, auditable, reversible, and safe.",
        "tone": "Grounded, practical, inspectable",
        "language": "nl",
        "rules": [
            "Do not claim autonomous personhood.",
            "Mutating or external actions require explicit approval through existing gated routes.",
        ],
        "tools": normalized_tools(None),
        "knowledge_sources": [],
        "knowledge_files": [],
        "memory": default_memory_settings(True),
        "model": DEFAULT_MODEL,
        "model_settings": default_model_settings(DEFAULT_MODEL),
        "conversation_starters": [],
        "builtin": True,
        "archived": False,
        "created_at": stamp,
        "updated_at": stamp,
    }


def normalize_persona_payload(payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}
    now = now_iso()
    clean_id = safe_slug(str(payload.get("id") or previous.get("id") or payload.get("name") or f"persona-{uuid.uuid4().hex[:8]}"))
    raw_model_settings = payload.get("model_settings") if isinstance(payload.get("model_settings"), dict) else {}
    model_name = str(
        raw_model_settings.get("name")
        or payload.get("model")
        or previous.get("model")
        or DEFAULT_MODEL
    ).strip() or DEFAULT_MODEL
    instructions = str(payload.get("instructions") or payload.get("system_prompt") or previous.get("instructions") or "").strip()
    memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else previous.get("memory")
    if not isinstance(memory, dict):
        memory = default_memory_settings(True)
    tools = normalized_tools(payload.get("tools") if "tools" in payload else previous.get("tools"))
    model_settings = {
        **default_model_settings(model_name),
        **{key: value for key, value in raw_model_settings.items() if key in {"provider", "name", "temperature", "max_tokens", "fallback_model"}},
    }
    model_settings["name"] = str(model_settings.get("name") or model_name)
    return {
        "id": clean_id,
        "name": str(payload.get("name") or previous.get("name") or "Nieuwe persona").strip()[:120],
        "description": str(payload.get("description") or previous.get("description") or "").strip()[:4000],
        "avatar": payload.get("avatar") if isinstance(payload.get("avatar"), dict) else previous.get("avatar", {"kind": "initials", "color": "#7bdcc3"}),
        "role": str(payload.get("role") or previous.get("role") or "").strip()[:240],
        "introduction": str(payload.get("introduction") or previous.get("introduction") or "").strip()[:1200],
        "instructions": instructions,
        "system_prompt": instructions,
        "tone": str(payload.get("tone") or previous.get("tone") or "Grounded, practical, inspectable").strip()[:240],
        "language": str(payload.get("language") or previous.get("language") or "nl").strip()[:40],
        "rules": [str(item).strip()[:400] for item in (payload.get("rules") or previous.get("rules") or [])[:24] if str(item).strip()],
        "tools": tools,
        "capabilities": [key for key, enabled in tools.items() if enabled],
        "knowledge_sources": payload.get("knowledge_sources") if isinstance(payload.get("knowledge_sources"), list) else previous.get("knowledge_sources", []),
        "knowledge_files": payload.get("knowledge_files") if isinstance(payload.get("knowledge_files"), list) else previous.get("knowledge_files", []),
        "memory": {
            "enabled": bool(memory.get("enabled", True)),
            "scope": str(memory.get("scope") or "persona"),
        },
        "model": model_name,
        "model_settings": model_settings,
        "conversation_starters": [str(item).strip()[:240] for item in (payload.get("conversation_starters") or previous.get("conversation_starters") or [])[:8] if str(item).strip()],
        "builtin": bool(previous.get("builtin", False)),
        "archived": bool(payload.get("archived", False)),
        "created_at": previous.get("created_at") or now,
        "updated_at": now,
    }

