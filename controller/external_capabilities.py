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
}

SECRET_MARKERS = ("secret", "token", "key", "auth", "cookie", "session", ".env", "credential")


def external_capabilities_status(roots: dict[str, str] | None = None, prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge and roots is None:
        bridge = _bridge_request("GET", "/external/capabilities", timeout=5)
        if bridge:
            bridge["via_bridge"] = True
            return bridge
    configured = roots or DEFAULT_AGENT_ROOTS
    capabilities = {name: _scan_root(name, Path(path).expanduser()) for name, path in configured.items()}
    return {
        "status": "online",
        "capabilities": capabilities,
        "tool_schemas": external_capability_tool_schemas(),
        "fake_success": False,
    }


def external_capability_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "external_capabilities_status",
                "description": "Inspecteer veilig welke AgentS/OpenHands mogelijkheden lokaal aanwezig zijn zonder secrets te lezen.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agent_runtime_submit",
                "description": "Start een bestaande slash/agent-runtime job voor Codex/Ruflo/Roo/Claude wanneer de adapter beschikbaar is.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "Bijvoorbeeld codex, ruflo, roo of claude."},
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
