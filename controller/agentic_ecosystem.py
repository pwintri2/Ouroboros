"""Read-only agentic ecosystem enrichment for DeepSeek and Atlas.

This module turns neighbouring agent workspaces into compact local context for
Ouroboros. It reads only the safe capability summaries exposed by
``controller.external_capabilities`` and never opens secret/config/cache files.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from controller.external_capabilities import external_capabilities_status


ECOSYSTEM_SOURCES = ("deepseek", "atlas")


def agentic_ecosystem_context(goal: str = "", *, prefer_bridge: bool = True) -> dict[str, Any]:
    """Return compact DeepSeek/Atlas patterns that can enrich agentic planning."""

    capabilities_payload = external_capabilities_status(prefer_bridge=prefer_bridge)
    capabilities = capabilities_payload.get("capabilities") if isinstance(capabilities_payload, Mapping) else {}
    if not isinstance(capabilities, Mapping):
        capabilities = {}

    selected = {
        name: _compact_capability(capabilities.get(name))
        for name in ECOSYSTEM_SOURCES
        if isinstance(capabilities.get(name), Mapping)
    }
    available = [name for name, info in selected.items() if info.get("exists")]
    patterns = _collect_patterns(selected)
    roles = _collect_roles(selected)
    recommendations = _recommendations(str(goal or ""), available)
    status = "online" if available else "missing"
    payload = {
        "status": status,
        "query": " ".join(str(goal or "").split())[:800],
        "sources": available,
        "source_count": len(available),
        "capabilities": selected,
        "patterns": patterns[:12],
        "roles": roles[:18],
        "recommendations": recommendations,
        "visible_summary": _visible_summary(available, patterns, roles),
        "via_bridge": bool(capabilities_payload.get("via_bridge")) if isinstance(capabilities_payload, Mapping) else False,
        "fake_success": False,
    }
    return payload


def _compact_capability(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "name": str(value.get("name") or ""),
        "root": str(value.get("root") or ""),
        "exists": bool(value.get("exists")),
        "status": str(value.get("status") or "unknown"),
        "entrypoints": _compact_entries(value.get("entrypoints")),
        "packages": _compact_entries(value.get("packages")),
        "docs": _compact_entries(value.get("docs")),
        "agentic_patterns": _compact_patterns(value.get("agentic_patterns")),
        "role_taxonomy": _compact_patterns(value.get("role_taxonomy")),
        "safe_notes": [str(item)[:280] for item in list(value.get("safe_notes") or [])[:5]],
    }


def _compact_entries(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, str]] = []
    for item in value[:12]:
        if not isinstance(item, Mapping):
            continue
        output.append(
            {
                "kind": str(item.get("kind") or "entry")[:80],
                "label": str(item.get("label") or item.get("path") or "")[:140],
                "path": str(item.get("path") or "")[:500],
            }
        )
    return output


def _compact_patterns(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, str]] = []
    for item in value[:16]:
        if not isinstance(item, Mapping):
            continue
        output.append(
            {
                "id": str(item.get("id") or item.get("name") or item.get("label") or "")[:80],
                "label": str(item.get("label") or item.get("name") or "")[:140],
                "value": str(item.get("value") or item.get("stance") or item.get("description") or "")[:360],
                "source": str(item.get("source") or "")[:180],
            }
        )
    return output


def _collect_patterns(selected: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    patterns: list[dict[str, str]] = []
    for source, info in selected.items():
        for item in info.get("agentic_patterns") or []:
            if isinstance(item, Mapping):
                patterns.append({"source_system": source, **dict(item)})
    return patterns


def _collect_roles(selected: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    for source, info in selected.items():
        for item in info.get("role_taxonomy") or []:
            if isinstance(item, Mapping):
                roles.append({"source_system": source, **dict(item)})
    return roles


def _recommendations(goal: str, available: list[str]) -> list[dict[str, str]]:
    lowered = goal.lower()
    base = [
        {
            "label": "Plan fan-out with role boundaries",
            "action": "Use DeepSeek-style explore/plan/review/implementer/verifier roles before starting mutating work.",
            "reason": "Keeps background agent work bounded and auditable.",
        },
        {
            "label": "Keep Atlas context pack visible",
            "action": "Use Atlas-style project overview, architecture, workflow rules, and progress tracker as shared agent context.",
            "reason": "Keeps multi-agent work from drifting across handoffs.",
        },
        {
            "label": "Preserve Ouroboros approval gates",
            "action": "Treat these sources as local planning context; shell, file writes, browser/app control and outbound actions still require Akkoord.",
            "reason": "The neighbouring projects enrich the plan, not the safety boundary.",
        },
    ]
    if "ui" in lowered or "cockpit" in lowered or "zichtbaar" in lowered:
        base.insert(
            0,
            {
                "label": "Surface agent provenance",
                "action": "Show which local ecosystem sources shaped an agentic answer.",
                "reason": "The user asked for visible enrichment.",
            },
        )
    if not available:
        base.append(
            {
                "label": "Mount or configure sources",
                "action": "Configure WINTRIP_DEEPSEEK_PATH and WINTRIP_ATLAS_PATH or expose them through the host bridge.",
                "reason": "No local DeepSeek/Atlas roots were visible to this backend.",
            }
        )
    return base[:6]


def _visible_summary(available: list[str], patterns: list[dict[str, str]], roles: list[dict[str, str]]) -> str:
    if not available:
        return "DeepSeek/Atlas context niet gevonden op deze runtime."
    source_text = " + ".join(available)
    role_text = ", ".join(item.get("label") or item.get("id") or "role" for item in roles[:6])
    pattern_text = ", ".join(item.get("label") or item.get("id") or "pattern" for item in patterns[:4])
    return f"{source_text}: {len(patterns)} patronen, {len(roles)} rollen. Rollen: {role_text}. Patronen: {pattern_text}."
