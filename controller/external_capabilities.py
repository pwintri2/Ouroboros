"""Safe capability discovery for neighbouring agent workspaces.

The scanner intentionally reports structure and entrypoints only. It does not
read token files, environment files, logs, caches, browser profiles, or other
secret-like material.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_AGENT_ROOTS: dict[str, str] = {
    "agents": "/home/pwintri2/AgentS",
    "openhands": "/home/pwintri2/OpenHands",
    "deepseek": "/home/pwintri2/deepseek",
    "atlas": "/home/pwintri2/atlas",
}

SECRET_MARKERS = ("secret", "token", "key", "auth", "cookie", "session", ".env", "credential")

DEEPSEEK_ROLE_TAXONOMY: list[dict[str, str]] = [
    {"id": "general", "label": "general", "value": "Flexible child agent for broad multi-step work.", "source": "docs/SUBAGENTS.md"},
    {"id": "explore", "label": "explore", "value": "Read-only mapper for fast evidence gathering.", "source": "docs/SUBAGENTS.md"},
    {"id": "plan", "label": "plan", "value": "Strategy producer with minimal writes and minimal shell.", "source": "docs/SUBAGENTS.md"},
    {"id": "review", "label": "review", "value": "Read-and-grade posture with severity-first findings.", "source": "docs/SUBAGENTS.md"},
    {"id": "implementer", "label": "implementer", "value": "Tightly scoped code-change worker.", "source": "docs/SUBAGENTS.md"},
    {"id": "verifier", "label": "verifier", "value": "Validation/test runner that reports pass/fail evidence.", "source": "docs/SUBAGENTS.md"},
    {"id": "custom", "label": "custom", "value": "Locked-down child with explicit tool allowlist.", "source": "docs/SUBAGENTS.md"},
]

DEEPSEEK_AGENTIC_PATTERNS: list[dict[str, str]] = [
    {"id": "role_taxonomy", "label": "Sub-agent role taxonomy", "value": "general/explore/plan/review/implementer/verifier/custom.", "source": "docs/SUBAGENTS.md"},
    {"id": "structured_output", "label": "Sub-agent output contract", "value": "SUMMARY, CHANGES, EVIDENCE, RISKS, BLOCKERS.", "source": "docs/SUBAGENTS.md"},
    {"id": "tool_surface", "label": "Structured tool surface", "value": "Prefer typed file/search/task/gate tools; shell remains the escape hatch.", "source": "docs/TOOL_SURFACE.md"},
    {"id": "durable_tasks", "label": "Durable task and gate evidence", "value": "Long-running work is tracked with task records, gates and artifacts.", "source": "docs/TOOL_SURFACE.md"},
    {"id": "context_forking", "label": "Context forking", "value": "Fresh children for independent exploration, forked children for continuation.", "source": "docs/SUBAGENTS.md"},
]

ATLAS_ROLE_TAXONOMY: list[dict[str, str]] = [
    {"id": "atlas", "label": "Orchestrator", "value": "Routes work through the SDD pipeline or answers directly.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "athena", "label": "Product Manager", "value": "Clarifies vague requests and authors PRDs.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "prometheus", "label": "Architect", "value": "Turns PRDs into architecture and load-bearing decisions.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "aphrodite", "label": "UX Expert", "value": "Designs user-visible flows and tokens before UI code.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "hestia", "label": "Scrum Master", "value": "Breaks epics into implementation-ready stories.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "hercules", "label": "Developer", "value": "Implements ready stories with verification.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "nemesis", "label": "QA", "value": "Reviews, finds regressions and validates stories.", "source": "packages/core/src/builtins/index.ts"},
    {"id": "apollo", "label": "Documentation Engineer", "value": "Maintains README, examples and API docs.", "source": "packages/core/src/builtins/index.ts"},
]

ATLAS_AGENTIC_PATTERNS: list[dict[str, str]] = [
    {"id": "sdd_pipeline", "label": "Spec-driven delivery", "value": "PRD -> architecture -> UX -> epics -> stories -> implementation -> QA -> release/docs.", "source": "context/project-overview.md"},
    {"id": "context_pack", "label": "Six-file context pack", "value": "Shared project overview, architecture, standards, workflow rules and progress tracker.", "source": "context/ai-workflow-rules.md"},
    {"id": "hook_guardrails", "label": "Hook-driven guardrails", "value": "Typed lifecycle hooks can allow, block or modify tool activity.", "source": "ARCHITECTURE.md"},
    {"id": "skill_extensible", "label": "Skill-extensible agents", "value": "Agents load SKILL.md bodies on demand from triggers.", "source": "ARCHITECTURE.md"},
    {"id": "state_routing", "label": "Project-state routing", "value": "Pure project-state detection recommends the next agent and explains why.", "source": "packages/core/src/orchestrator/decide.ts"},
]


def external_capabilities_status(roots: dict[str, str] | None = None, prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge and roots is None:
        bridge = _bridge_request("GET", "/external/capabilities", timeout=5)
        if bridge:
            bridge["via_bridge"] = True
            bridge = _ensure_core_capabilities(bridge)
            return bridge
    configured = roots or _configured_agent_roots()
    capabilities = {name: _scan_root(name, Path(path).expanduser()) for name, path in configured.items()}
    return {
        "status": "online",
        "capabilities": capabilities,
        "tool_schemas": external_capability_tool_schemas(),
        "fake_success": False,
    }


def _configured_agent_roots() -> dict[str, str]:
    return {
        "agents": str(os.getenv("WINTRIP_AGENTS_PATH") or DEFAULT_AGENT_ROOTS["agents"]),
        "openhands": str(os.getenv("WINTRIP_OPENHANDS_PATH") or DEFAULT_AGENT_ROOTS["openhands"]),
        "deepseek": str(os.getenv("WINTRIP_DEEPSEEK_PATH") or DEFAULT_AGENT_ROOTS["deepseek"]),
        "atlas": str(os.getenv("WINTRIP_ATLAS_PATH") or DEFAULT_AGENT_ROOTS["atlas"]),
    }


def _ensure_core_capabilities(payload: dict[str, Any]) -> dict[str, Any]:
    """Augment stale bridge payloads with DeepSeek/Atlas when locally mounted."""

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
        payload["capabilities"] = capabilities
    configured = _configured_agent_roots()
    for name in ("deepseek", "atlas"):
        if name not in capabilities:
            capabilities[name] = _scan_root(name, Path(configured[name]).expanduser())
    payload["tool_schemas"] = external_capability_tool_schemas()
    payload.setdefault("fake_success", False)
    return payload


def external_capability_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "external_capabilities_status",
                "description": "Inspecteer veilig welke AgentS/OpenHands/DeepSeek/Atlas mogelijkheden lokaal aanwezig zijn zonder secrets te lezen.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agent_runtime_submit",
                "description": "Start een bestaande slash/agent-runtime job voor Codex/DeepSeek/Atlas/Ruflo/Roo/Claude wanneer de adapter beschikbaar is.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "Bijvoorbeeld codex, deepseek, atlas, ruflo, roo of claude."},
                        "task": {"type": "string", "description": "Concrete taak voor de agent."},
                        "approval": {"type": "string", "description": "Schrijf/host-acties blijven Akkoord-gated."},
                    },
                    "required": ["agent", "task"],
                },
            },
        },
    ]


def _scan_root(name: str, root: Path) -> dict[str, Any]:
    exists = root.exists()
    result: dict[str, Any] = {
        "name": name,
        "root": str(root),
        "exists": exists,
        "status": "available" if exists else "missing",
        "entrypoints": [],
        "packages": [],
        "safe_notes": [],
        "fake_success": False,
    }
    if not exists:
        result["safe_notes"].append("Root bestaat niet op deze host.")
        return result

    if name == "agents":
        _add_if_exists(result, root / "gui_agents", "package", "gui_agents")
        _add_if_exists(result, root / "integrations", "directory", "integrations")
        _add_if_exists(result, root / "evaluation_sets", "directory", "evaluation_sets")
        _add_if_exists(result, root / "WAA_setup.md", "doc", "WAA_setup.md")
        _add_if_exists(result, root / "README.md", "doc", "README.md")
        result["safe_notes"].append("Bruikbaar als GUI-agent/OSWorld capability catalogus; niet direct als credentialbron.")
    elif name == "openhands":
        _add_if_exists(result, root / "openhands", "package", "openhands")
        _add_if_exists(result, root / "frontend", "directory", "frontend")
        _add_if_exists(result, root / "skills", "directory", "skills")
        _add_if_exists(result, root / "start_openhands.sh", "script", "start_openhands.sh")
        _add_if_exists(result, root / "config.template.toml", "template", "config.template.toml")
        result["safe_notes"].append("Bruikbaar als OpenHands runtime/skills capability; configs en cache worden niet gelezen.")
    elif name == "deepseek":
        _add_if_exists(result, root / "docs" / "SUBAGENTS.md", "doc", "DeepSeek sub-agents")
        _add_if_exists(result, root / "docs" / "TOOL_SURFACE.md", "doc", "DeepSeek tool surface")
        _add_if_exists(result, root / "docs" / "ARCHITECTURE.md", "doc", "DeepSeek architecture")
        _add_if_exists(result, root / "Cargo.toml", "manifest", "Cargo workspace")
        _add_if_exists(result, root / "crates" / "agent", "package", "crates/agent")
        _add_if_exists(result, root / "crates" / "tui", "package", "crates/tui")
        result["role_taxonomy"] = list(DEEPSEEK_ROLE_TAXONOMY)
        result["agentic_patterns"] = list(DEEPSEEK_AGENTIC_PATTERNS)
        result["safe_notes"].append("Bruikbaar als lokaal patroonboek voor sub-agent rollen, task gates en tool-oppervlak; geen runtime secrets gelezen.")
    elif name == "atlas":
        _add_if_exists(result, root / "context" / "project-overview.md", "doc", "Atlas project overview")
        _add_if_exists(result, root / "context" / "ai-workflow-rules.md", "doc", "Atlas AI workflow rules")
        _add_if_exists(result, root / "ARCHITECTURE.md", "doc", "Atlas architecture")
        _add_if_exists(result, root / "packages" / "core" / "src" / "builtins" / "index.ts", "source", "built-in agents")
        _add_if_exists(result, root / "packages" / "core" / "src" / "orchestrator" / "decide.ts", "source", "state router")
        _add_if_exists(result, root / "packages" / "core", "package", "@atlas/core")
        result["role_taxonomy"] = list(ATLAS_ROLE_TAXONOMY)
        result["agentic_patterns"] = list(ATLAS_AGENTIC_PATTERNS)
        result["safe_notes"].append("Bruikbaar als SDD/agent-crew/context-pack patroonbron; ~/.atlas gebruikersstate wordt niet gelezen.")
    else:
        for child in sorted(root.iterdir())[:40]:
            if _safe_child(child):
                _add_if_exists(result, child, "entry", child.name)
    return result


def _bridge_request(method: str, path: str, timeout: float) -> dict[str, Any]:
    base_url = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
    if not base_url or not token_path:
        return {}
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    request = urllib.request.Request(
        f"{base_url}{path}",
        method=method,
        headers={"X-Ouroboros-Bridge-Token": token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except Exception:
            value = {}
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _safe_child(path: Path) -> bool:
    lowered = path.name.lower()
    return not any(marker in lowered for marker in SECRET_MARKERS)


def _add_if_exists(result: dict[str, Any], path: Path, kind: str, label: str) -> None:
    if not path.exists() or not _safe_child(path):
        return
    entry = {"kind": kind, "label": label, "path": str(path)}
    if kind == "package":
        result.setdefault("packages", []).append(entry)
    else:
        result.setdefault("entrypoints", []).append(entry)
