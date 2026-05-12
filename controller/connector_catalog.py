"""Cockpit connector catalog and enable/disable state.

This module is the product layer above the existing adapters. It keeps only
non-secret connector preferences in ``.secrets/ouroboros_connectors.json`` and
builds a status surface for the cockpit without executing live connector work.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
CATALOG_VERSION = "2026-05-12.connector-cockpit.v1"
STATUS_TOOLS = {
    "gmail_status",
    "google_drive_status",
    "microsoft_graph_status",
    "sharepoint_status",
    "github_status",
    "vps_status",
    "chroma_sync_status",
    "voice_chat_status",
}


def connector_settings_path() -> Path:
    configured = os.getenv("WINTRIP_CONNECTOR_SETTINGS_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (workspace_root() / ".secrets" / "ouroboros_connectors.json").resolve()


def get_connector_catalog(*, include_status: bool = True) -> dict[str, Any]:
    settings = _read_settings()
    connectors = [_connector_payload(spec, settings, include_status=include_status) for spec in CONNECTOR_SPECS]
    tool_index = _tool_index(connectors)
    enabled_count = sum(1 for item in connectors if item.get("enabled"))
    configured_count = sum(1 for item in connectors if item.get("configured"))
    disabled_tools = sorted(name for name, item in tool_index.items() if not item.get("enabled"))
    return {
        "status": "online",
        "version": CATALOG_VERSION,
        "generated_at": _now(),
        "settings_path": str(connector_settings_path()),
        "approval_phrase": APPROVAL_PHRASE,
        "connector_count": len(connectors),
        "enabled_count": enabled_count,
        "disabled_count": len(connectors) - enabled_count,
        "configured_count": configured_count,
        "connectors": connectors,
        "tool_index": tool_index,
        "disabled_tools": disabled_tools,
        "agent_work_packages": get_connector_agent_work_packages(),
        "policy": {
            "toggle_requires_approval": True,
            "private_reads_still_require_per_action_approval": True,
            "writes_still_require_per_action_approval": True,
            "approval_phrase": APPROVAL_PHRASE,
            "status_tools_always_readable": True,
            "secrets_returned": False,
        },
        "secrets_returned": False,
        "fake_success": False,
    }


def get_connector_agent_work_packages() -> list[dict[str, Any]]:
    """Return concrete next tasks for the connector-building agents."""

    return [
        {
            "id": "codex_connector_execution_slice",
            "agent": "Codex",
            "role": "De Bouwer",
            "status": "ready",
            "priority": 1,
            "target": "backend",
            "command_hint": "/codex",
            "title": "Maak connector-uitvoering echt voor Microsoft/SharePoint en Google preview-acties.",
            "prompt": (
                "Werk in /home/pwintri2/WintripAI. Breid de connector-cockpit backend uit zonder secrets te lekken. "
                "Voeg AgentToolRegistry-tools toe voor microsoft_graph_status, teams_list, onedrive_list, outlook_read, "
                "sharepoint_status, sharepoint_sites en sharepoint_libraries op basis van bestaande adapters. "
                "Alle private reads blijven exact Akkoord vereisen, writes blijven preview/blocked tenzij al veilig geïmplementeerd. "
                "Voeg unit tests toe en draai de relevante connector/agent-tool tests."
            ),
            "scope": [
                "controller/agent_tools.py",
                "controller/connector_catalog.py",
                "sandbox_tests/test_agent_tools.py",
                "sandbox_tests/test_connector_catalog.py",
            ],
            "acceptance": [
                "Nieuwe Microsoft/SharePoint tools verschijnen in de registry-schema's.",
                "Disabled connector blokkeert de nieuwe tools echt.",
                "Private reads zonder Akkoord geven status blocked.",
                "Geen token/OAuth/session-materiaal in output.",
            ],
            "approval": {
                "required_for_execution": True,
                "phrase": APPROVAL_PHRASE,
                "note": "Codewijzigingen en tests mogen via Codex/Roo; live connector-mutaties niet.",
            },
        },
        {
            "id": "web_scout_connector_docs_cards",
            "agent": "Web-Scout",
            "role": "Onderzoeker",
            "status": "ready",
            "priority": 2,
            "target": "research",
            "command_hint": "/deepseek or /atlas",
            "title": "Maak install capability cards voor echte connector-loginflows.",
            "prompt": (
                "Onderzoek alleen officiële documentatie voor Gmail/Drive OAuth, Microsoft Graph delegated permissions, "
                "Teams/SharePoint/OneDrive Graph endpoints, GitHub fine-grained tokens, Brave Search API en rclone Drive setup. "
                "Lever gestructureerde install capability cards: platform, vereisten, scopes/permissions, privileges, setupstappen, rollback en risico's. "
                "Geen tokens verzamelen, geen login-bypass, geen live mutaties."
            ),
            "scope": [
                "docs or handoff markdown",
                "connector setup cards",
            ],
            "acceptance": [
                "Elke card noemt officiële broncategorie en benodigde scopes.",
                "Windows/macOS/Linux/iPhone verschillen zijn expliciet.",
                "Risico's en rollback staan per connector apart.",
            ],
            "approval": {
                "required_for_execution": False,
                "phrase": APPROVAL_PHRASE,
                "note": "Publiek documentatieonderzoek mag read-only; browser_research blijft approval-gated wanneer gebruikt.",
            },
        },
        {
            "id": "communicator_connector_guidance_ui",
            "agent": "Communicator",
            "role": "Begeleider",
            "status": "ready",
            "priority": 3,
            "target": "frontend",
            "command_hint": "/codex",
            "title": "Maak begeleide setupkaarten voor connectoren.",
            "prompt": (
                "Werk in de cockpit UI. Voeg per connector rustige setup/workflow-kaarten toe met: doel, huidige status, "
                "benodigde toestemming, eerste veilige stap, uitvoerknop of fallback-instructie. "
                "Gebruik bestaande compacte cockpit-stijl, geen landingpage, geen nested cards. "
                "Toggles blijven via /api/cockpit/connectors lopen."
            ),
            "scope": [
                "ouroboros_cockpit/src/App.tsx",
                "ouroboros_cockpit/src/styles.css",
            ],
            "acceptance": [
                "Een gebruiker ziet per connector wat nog ontbreekt.",
                "Setup-instructies passen in de panelen zonder overlap.",
                "Buttons zijn disabled wanneer Akkoord nodig maar ontbreekt.",
                "npm run build slaagt.",
            ],
            "approval": {
                "required_for_execution": True,
                "phrase": APPROVAL_PHRASE,
                "note": "UI-code wijzigen mag; externe connectoracties niet automatisch uitvoeren.",
            },
        },
        {
            "id": "criticus_connector_policy_tests",
            "agent": "Criticus",
            "role": "Reviewer",
            "status": "ready",
            "priority": 4,
            "target": "safety",
            "command_hint": "/roo or /codex",
            "title": "Verhard connector-policy en regressietests.",
            "prompt": (
                "Review de connector-cockpit op guardrails. Voeg tests toe die bewijzen dat disabled connectors executie blokkeren, "
                "status-tools leesbaar blijven, private reads Akkoord vereisen, writes niet via catalog toggles worden uitgevoerd, "
                "en outputs geen API keys/OAuth tokens/cookies/sessies bevatten. "
                "Rapporteer risico's met bestand/regel-referenties."
            ),
            "scope": [
                "sandbox_tests/test_connector_catalog.py",
                "sandbox_tests/test_agent_tools.py",
                "sandbox_tests/test_tool_bridge.py",
                "controller/connector_catalog.py",
            ],
            "acceptance": [
                "Tests dekken aan/uit op connectorniveau en toolniveau.",
                "Secrets-redaction assertions aanwezig.",
                "Geen fake success bij disabled of ongeconfigureerde connectors.",
                "Bestaande regressies blijven groen.",
            ],
            "approval": {
                "required_for_execution": True,
                "phrase": APPROVAL_PHRASE,
                "note": "Review en tests mogen muteren; live connectoracties blijven buiten scope.",
            },
        },
    ]


def get_connector(connector_id: str, *, include_status: bool = True) -> dict[str, Any]:
    clean_id = _clean_id(connector_id)
    spec = _spec_by_id(clean_id)
    if spec is None:
        return {"status": "not_found", "connector_id": clean_id, "reason": f"Unknown connector: {connector_id}", "fake_success": False}
    return {
        "status": "online",
        "connector": _connector_payload(spec, _read_settings(), include_status=include_status),
        "secrets_returned": False,
        "fake_success": False,
    }


def set_connector_enabled(
    connector_id: str,
    *,
    enabled: bool,
    approval: str = "",
    notes: str = "",
    updated_by: str = "cockpit",
) -> dict[str, Any]:
    clean_id = _clean_id(connector_id)
    spec = _spec_by_id(clean_id)
    if spec is None:
        return {"status": "not_found", "connector_id": clean_id, "reason": f"Unknown connector: {connector_id}", "fake_success": False}
    if str(approval or "").strip() != APPROVAL_PHRASE:
        return _approval_blocked("toggle_connector", connector_id=clean_id)

    settings = _read_settings()
    entry = dict((settings.get("connectors") or {}).get(clean_id) or {})
    entry.update(
        {
            "enabled": bool(enabled),
            "updated_at": _now(),
            "updated_by": _clean_text(updated_by, 80),
        }
    )
    if enabled:
        # Treat the connector-level On switch as a master reset. Otherwise a
        # connector can look enabled while stale per-tool false overrides keep
        # every useful action blocked.
        entry.pop("tool_overrides", None)
    if notes:
        entry["notes"] = _clean_text(notes, 500)
    settings.setdefault("connectors", {})[clean_id] = entry
    settings["updated_at"] = _now()
    _write_settings(settings)
    return {
        "status": "updated",
        "connector": _connector_payload(spec, settings, include_status=True),
        "secrets_returned": False,
        "fake_success": False,
    }


def set_tool_enabled(
    tool_name: str,
    *,
    enabled: bool,
    approval: str = "",
    updated_by: str = "cockpit",
) -> dict[str, Any]:
    clean_tool = str(tool_name or "").strip()
    spec = _spec_for_tool(clean_tool)
    if spec is None:
        return {"status": "not_found", "tool_name": clean_tool, "reason": f"Unknown connector tool: {tool_name}", "fake_success": False}
    if clean_tool in STATUS_TOOLS:
        if enabled:
            return {
                "status": "already_on",
                "tool_name": clean_tool,
                "connector_id": spec["id"],
                "tool": is_tool_enabled(clean_tool),
                "reason": "Status tools are always readable for connector diagnostics.",
                "secrets_returned": False,
                "fake_success": False,
            }
        return {
            "status": "not_mutable",
            "tool_name": clean_tool,
            "connector_id": spec["id"],
            "reason": "Connector status tools stay readable so the cockpit can diagnose disabled connectors.",
            "fake_success": False,
        }
    if str(approval or "").strip() != APPROVAL_PHRASE:
        return _approval_blocked("toggle_tool", connector_id=spec["id"], tool_name=clean_tool)

    settings = _read_settings()
    entry = dict((settings.get("connectors") or {}).get(spec["id"]) or {})
    tool_overrides = dict(entry.get("tool_overrides") or {})
    tool_overrides[clean_tool] = bool(enabled)
    entry.update({"tool_overrides": tool_overrides, "updated_at": _now(), "updated_by": _clean_text(updated_by, 80)})
    settings.setdefault("connectors", {})[spec["id"]] = entry
    settings["updated_at"] = _now()
    _write_settings(settings)
    connector = _connector_payload(spec, settings, include_status=True)
    return {
        "status": "updated",
        "tool_name": clean_tool,
        "connector_id": spec["id"],
        "connector": connector,
        "tool": next((tool for tool in connector.get("tools", []) if tool.get("name") == clean_tool), {}),
        "secrets_returned": False,
        "fake_success": False,
    }


def is_tool_enabled(tool_name: str) -> dict[str, Any]:
    clean_tool = str(tool_name or "").strip()
    spec = _spec_for_tool(clean_tool)
    if spec is None:
        return {"enabled": True, "tool_name": clean_tool, "connector_id": "", "reason": "No connector gate for this tool.", "fake_success": False}
    if clean_tool in STATUS_TOOLS:
        return {
            "enabled": True,
            "tool_name": clean_tool,
            "connector_id": spec["id"],
            "connector_name": spec["name"],
            "reason": "Status tools remain readable.",
            "status_tool": True,
            "fake_success": False,
        }
    settings = _read_settings()
    entry = dict((settings.get("connectors") or {}).get(spec["id"]) or {})
    connector_enabled = bool(entry.get("enabled", spec.get("default_enabled", True)))
    override = (entry.get("tool_overrides") or {}).get(clean_tool)
    enabled = bool(connector_enabled if override is None else override)
    if enabled:
        reason = "enabled"
    elif not connector_enabled:
        reason = f"Connector disabled in cockpit: {spec['name']}"
    else:
        reason = f"Tool disabled in cockpit: {clean_tool}"
    return {
        "enabled": enabled,
        "tool_name": clean_tool,
        "connector_id": spec["id"],
        "connector_name": spec["name"],
        "connector_enabled": connector_enabled,
        "tool_override": override,
        "reason": reason,
        "fake_success": False,
    }


def _connector_payload(spec: Mapping[str, Any], settings: Mapping[str, Any], *, include_status: bool) -> dict[str, Any]:
    connector_settings = dict((settings.get("connectors") or {}).get(spec["id"]) or {})
    enabled = bool(connector_settings.get("enabled", spec.get("default_enabled", True)))
    status_payload = _connector_status_payload(spec) if include_status else {"status": "not_checked", "fake_success": False}
    status_detail = _sanitize_status(status_payload)
    if isinstance(status_detail, dict):
        status_detail["cockpit_enabled"] = enabled
        status_detail["connector_runtime"] = "enabled" if enabled else "disabled"
    status_value = str(status_payload.get("status") or "unknown")
    configured = _configured_from_status(status_payload)
    available = _available_from_status(status_payload)
    readiness = "disabled" if not enabled else ("ready" if configured or available else "not_configured")
    tool_overrides = dict(connector_settings.get("tool_overrides") or {})
    tools = []
    for tool in spec.get("tools", []):
        name = str(tool.get("name") or "")
        override = tool_overrides.get(name)
        tool_enabled = True if name in STATUS_TOOLS else bool(enabled if override is None else override)
        tools.append(
            {
                **tool,
                "enabled": tool_enabled,
                "connector_enabled": enabled,
                "status_tool": name in STATUS_TOOLS,
                "approval_phrase": APPROVAL_PHRASE if tool.get("requires_approval") else "",
                "fake_success": False,
            }
        )
    return {
        "id": spec["id"],
        "name": spec["name"],
        "provider": spec.get("provider", ""),
        "category": spec.get("category", ""),
        "description": spec.get("description", ""),
        "enabled": enabled,
        "readiness": readiness,
        "configured": configured,
        "available": available,
        "status": status_value,
        "status_detail": status_detail,
        "tools": tools,
        "routes": list(spec.get("routes", [])),
        "setup": spec.get("setup", {}),
        "approval": {
            "toggle_requires_approval": True,
            "private_read_requires_approval": bool(spec.get("private_read_requires_approval", False)),
            "write_requires_approval": bool(spec.get("write_requires_approval", False)),
            "approval_phrase": APPROVAL_PHRASE,
        },
        "settings": {
            "has_override": spec["id"] in (settings.get("connectors") or {}),
            "updated_at": connector_settings.get("updated_at", ""),
            "updated_by": connector_settings.get("updated_by", ""),
            "notes": connector_settings.get("notes", ""),
            "tool_overrides": tool_overrides,
        },
        "secrets_returned": False,
        "fake_success": False,
    }


def _tool_index(connectors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for connector in connectors:
        for tool in connector.get("tools", []):
            name = str(tool.get("name") or "")
            if not name:
                continue
            index[name] = {
                "tool_name": name,
                "connector_id": connector.get("id"),
                "connector_name": connector.get("name"),
                "enabled": bool(tool.get("enabled")),
                "status_tool": bool(tool.get("status_tool")),
                "requires_approval": bool(tool.get("requires_approval")),
                "kind": tool.get("kind", ""),
            }
    return index


def _connector_status_payload(spec: Mapping[str, Any]) -> dict[str, Any]:
    status_fn = spec.get("status_fn")
    if callable(status_fn):
        try:
            value = status_fn()
            return value if isinstance(value, dict) else {"status": "error", "reason": "Status function returned non-object.", "fake_success": False}
        except Exception as exc:
            return {"status": "error", "reason": _clean_text(str(exc), 1000), "fake_success": False}
    return {"status": str(spec.get("static_status") or "ready"), "fake_success": False}


def _configured_from_status(status: Mapping[str, Any]) -> bool:
    value = str(status.get("status") or "").lower()
    if value in {"connected", "configured", "ready", "success", "online", "available"}:
        token = status.get("token") if isinstance(status.get("token"), Mapping) else {}
        if "has_refresh_token" in token:
            return bool(token.get("has_refresh_token"))
        return True
    if bool(status.get("configured")):
        return True
    token = status.get("token") if isinstance(status.get("token"), Mapping) else {}
    if "has_refresh_token" in token:
        return bool(token.get("has_refresh_token"))
    if bool(token.get("exists")) or bool(token.get("configured")):
        return True
    if bool(status.get("binary_exists")) and bool(status.get("drive_remotes")):
        return True
    return False


def _available_from_status(status: Mapping[str, Any]) -> bool:
    value = str(status.get("status") or "").lower()
    token = status.get("token") if isinstance(status.get("token"), Mapping) else {}
    if "has_refresh_token" in token and not bool(token.get("has_refresh_token")):
        return False
    return value not in {"error", "unavailable", "missing_api_key", "token_missing", "not_found", "offline"}


def _sanitize_status(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if lower in {"has_refresh_token", "client_id_configured", "client_secret_configured"} and isinstance(item, bool):
                clean[str(key)] = item
            elif any(marker in lower for marker in ("access_token", "refresh_token", "client_secret", "authorization", "bearer", "password", "cookie", "session")):
                clean[str(key)] = "[REDACTED]"
            elif lower == "token" and isinstance(item, Mapping):
                clean[str(key)] = _sanitize_status(item)
            else:
                clean[str(key)] = _sanitize_status(item)
        clean.setdefault("secrets_returned", False)
        return clean
    if isinstance(value, list):
        return [_sanitize_status(item) for item in value[:50]]
    return value


def _read_settings() -> dict[str, Any]:
    path = connector_settings_path()
    if not path.exists():
        return {"version": CATALOG_VERSION, "connectors": {}, "created_at": "", "updated_at": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": CATALOG_VERSION, "connectors": {}, "created_at": "", "updated_at": "", "status": "settings_unreadable"}
    if not isinstance(data, dict):
        return {"version": CATALOG_VERSION, "connectors": {}, "created_at": "", "updated_at": ""}
    data.setdefault("version", CATALOG_VERSION)
    data.setdefault("connectors", {})
    return data


def _write_settings(settings: Mapping[str, Any]) -> None:
    path = connector_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(settings)
    payload.setdefault("version", CATALOG_VERSION)
    payload.setdefault("created_at", _now())
    payload["updated_at"] = _now()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _approval_blocked(operation: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "blocked",
        "operation": operation,
        "approval_required": True,
        "approval_phrase": APPROVAL_PHRASE,
        "reason": "Connector toggles require exact Akkoord.",
        **extra,
        "secrets_returned": False,
        "fake_success": False,
    }


def _spec_by_id(connector_id: str) -> Mapping[str, Any] | None:
    return next((spec for spec in CONNECTOR_SPECS if spec["id"] == connector_id), None)


def _spec_for_tool(tool_name: str) -> Mapping[str, Any] | None:
    clean_tool = str(tool_name or "").strip()
    return next((spec for spec in CONNECTOR_SPECS if any(tool.get("name") == clean_tool for tool in spec.get("tools", []))), None)


def _tool(name: str, *, kind: str = "read", requires_approval: bool = False, description: str = "") -> dict[str, Any]:
    return {"name": name, "kind": kind, "requires_approval": requires_approval, "description": description}


def _clean_id(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_import_status(module_name: str, function_name: str) -> Callable[[], dict[str, Any]]:
    def _runner() -> dict[str, Any]:
        module = __import__(module_name, fromlist=[function_name])
        fn = getattr(module, function_name)
        result = fn()
        return result if isinstance(result, dict) else {"status": "error", "reason": "Status function returned non-object.", "fake_success": False}

    return _runner


def _google_drive_status() -> dict[str, Any]:
    adapters: dict[str, Any] = {}
    statuses: list[str] = []
    for key, module_name, function_name in (
        ("google_workspace", "controller.google_workspace_adapter", "get_google_workspace_status"),
        ("rclone_drive", "controller.rclone_drive_adapter", "get_rclone_drive_status"),
    ):
        try:
            payload = _safe_import_status(module_name, function_name)()
        except Exception as exc:
            payload = {"status": "error", "reason": _clean_text(str(exc), 1000), "fake_success": False}
        adapters[key] = payload
        statuses.append(str(payload.get("status") or "unknown"))
    return {
        "status": "ready" if any(item in {"connected", "ready", "success", "online"} for item in statuses) else "unavailable",
        "adapters": adapters,
        "fake_success": False,
        "secrets_returned": False,
    }


CONNECTOR_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "gmail",
        "name": "Gmail",
        "provider": "Google Workspace",
        "category": "Mail",
        "description": "Mailboxstatus, private Gmail search en later preview-first mailacties via Google Workspace.",
        "default_enabled": True,
        "private_read_requires_approval": True,
        "write_requires_approval": True,
        "status_fn": _safe_import_status("controller.google_workspace_adapter", "get_google_workspace_status"),
        "tools": [
            _tool("gmail_status", kind="status", description="Sanitized Gmail/Workspace status."),
            _tool("gmail_search", kind="private_read", requires_approval=True, description="Private mailbox search."),
            _tool("gmail_manage", kind="write", requires_approval=True, description="Labels/archive/read state."),
            _tool("mail_read_recent", kind="private_read", requires_approval=True),
            _tool("mail_send_preview", kind="preview"),
            _tool("mail_send", kind="write", requires_approval=True),
        ],
        "routes": [
            {"method": "GET", "path": "/api/cockpit/connectors/google/oauth/status", "tool_name": "google_oauth_status"},
            {"method": "POST", "path": "/api/cockpit/connectors/google/oauth/start", "tool_name": "google_oauth_start"},
            {"method": "POST", "path": "/api/cockpit/connectors/google/oauth/exchange", "tool_name": "google_oauth_exchange"},
            {"method": "POST", "path": "/agent/tool", "tool_name": "gmail_search"},
        ],
        "setup": {
            "credential": "Google OAuth client + refresh token",
            "env": "WINTRIP_GOOGLE_TOKEN_PATH / WINTRIP_GOOGLE_OAUTH_CLIENT_PATH",
            "oauth_status_route": "/api/cockpit/connectors/google/oauth/status",
        },
    },
    {
        "id": "google_drive",
        "name": "Google Drive",
        "provider": "Google Workspace / rclone",
        "category": "Files",
        "description": "Drive status en private read-only bestandslijsten via Google Workspace of rclone.",
        "default_enabled": True,
        "private_read_requires_approval": True,
        "write_requires_approval": True,
        "status_fn": _google_drive_status,
        "tools": [
            _tool("google_drive_status", kind="status"),
            _tool("google_drive_list", kind="private_read", requires_approval=True),
            _tool("drive_upload_file", kind="write", requires_approval=True),
            _tool("drive_upload_text", kind="write", requires_approval=True),
        ],
        "routes": [
            {"method": "GET", "path": "/api/cockpit/connectors/google/oauth/status", "tool_name": "google_oauth_status"},
            {"method": "POST", "path": "/api/cockpit/connectors/google/oauth/start", "tool_name": "google_oauth_start"},
            {"method": "POST", "path": "/api/cockpit/connectors/google/oauth/exchange", "tool_name": "google_oauth_exchange"},
            {"method": "POST", "path": "/agent/tool", "tool_name": "google_drive_list"},
        ],
        "setup": {
            "credential": "Google OAuth refresh token or rclone remote",
            "env": "WINTRIP_GOOGLE_TOKEN_PATH / WINTRIP_GOOGLE_OAUTH_CLIENT_PATH / RCLONE_CONFIG",
            "oauth_status_route": "/api/cockpit/connectors/google/oauth/status",
        },
    },
    {
        "id": "microsoft_graph",
        "name": "Microsoft 365",
        "provider": "Microsoft Graph",
        "category": "Office",
        "description": "Outlook, Teams, OneDrive en Calendar foundation via Microsoft Graph.",
        "default_enabled": True,
        "private_read_requires_approval": True,
        "write_requires_approval": True,
        "status_fn": _safe_import_status("controller.microsoft_graph_adapter", "get_microsoft_graph_status"),
        "tools": [
            _tool("microsoft_graph_status", kind="status"),
            _tool("outlook_read", kind="private_read", requires_approval=True),
            _tool("teams_list", kind="private_read", requires_approval=True),
            _tool("onedrive_list", kind="private_read", requires_approval=True),
            _tool("microsoft_calendar", kind="private_read", requires_approval=True),
            _tool("power_automate_flow", kind="write", requires_approval=True),
        ],
        "routes": [{"method": "GET", "path": "/trainer/microsoft/status"}],
        "setup": {"credential": "Microsoft Graph token", "env": "WINTRIP_MICROSOFT_GRAPH_TOKEN_PATH"},
    },
    {
        "id": "sharepoint",
        "name": "SharePoint",
        "provider": "Microsoft 365",
        "category": "Office",
        "description": "SharePoint sites, libraries, permission analysis and workflow previews.",
        "default_enabled": True,
        "private_read_requires_approval": True,
        "write_requires_approval": True,
        "status_fn": _safe_import_status("controller.sharepoint_pnp_adapter", "get_sharepoint_status"),
        "tools": [
            _tool("sharepoint_status", kind="status"),
            _tool("sharepoint_sites", kind="private_read", requires_approval=True),
            _tool("sharepoint_libraries", kind="private_read", requires_approval=True),
            _tool("sharepoint_permission_analysis", kind="private_read", requires_approval=True),
            _tool("sharepoint_workflow_preview", kind="preview"),
            _tool("sharepoint_workflow_execute", kind="write", requires_approval=True),
        ],
        "routes": [{"method": "GET", "path": "/trainer/sharepoint/status"}],
        "setup": {"credential": "Microsoft Graph token", "env": "WINTRIP_MICROSOFT_GRAPH_TOKEN_PATH"},
    },
    {
        "id": "github",
        "name": "GitHub",
        "provider": "GitHub",
        "category": "Code",
        "description": "Read-only GitHub metadata/search; write actions stay separate and approval-gated.",
        "default_enabled": True,
        "private_read_requires_approval": True,
        "write_requires_approval": True,
        "status_fn": _safe_import_status("controller.github_adapter", "get_github_status"),
        "tools": [
            _tool("github_status", kind="status"),
            _tool("github_repo", kind="public_read"),
            _tool("github_search_repositories", kind="public_read"),
            _tool("github_write_preview", kind="preview"),
            _tool("github_write", kind="write", requires_approval=True),
        ],
        "routes": [{"method": "POST", "path": "/agent/tool", "tool_name": "github_repo"}],
        "setup": {"credential": "Optional GitHub token", "env": "GITHUB_TOKEN / GH_TOKEN"},
    },
    {
        "id": "brave_search",
        "name": "Brave Search",
        "provider": "Brave",
        "category": "Web",
        "description": "Current web search through Brave API; read-only untrusted web context.",
        "default_enabled": True,
        "private_read_requires_approval": False,
        "write_requires_approval": False,
        "status_fn": _safe_import_status("controller.brave_search", "brave_search_status"),
        "tools": [_tool("brave_search", kind="public_read")],
        "routes": [{"method": "POST", "path": "/api/ouroboros/search/brave"}],
        "setup": {"credential": "Brave API key", "env": "BRAVE_SEARCH_API_KEY or cockpit API-key store"},
    },
    {
        "id": "browser_research",
        "name": "Browser Research",
        "provider": "Local/host browser",
        "category": "Web",
        "description": "Approval-gated browser research, visible page reads and browser/app opening.",
        "default_enabled": True,
        "private_read_requires_approval": True,
        "write_requires_approval": True,
        "static_status": "ready",
        "tools": [
            _tool("browser_research", kind="external_read", requires_approval=True),
            _tool("browser_open_url", kind="browser_control", requires_approval=True),
            _tool("host_open_url", kind="browser_control", requires_approval=True),
            _tool("chatgpt_browser_ask", kind="browser_control", requires_approval=True),
            _tool("world_grok_ask", kind="browser_control", requires_approval=True),
        ],
        "routes": [{"method": "POST", "path": "/api/ouroboros/research/browser"}],
        "setup": {"credential": "Human browser session outside token storage", "env": "host bridge optional"},
    },
    {
        "id": "vps",
        "name": "VPS Deploy",
        "provider": "SSH/rsync",
        "category": "Infrastructure",
        "description": "VPS login status, dry-run sync and explicitly approved deploy actions.",
        "default_enabled": True,
        "private_read_requires_approval": False,
        "write_requires_approval": True,
        "status_fn": _safe_import_status("controller.vps_deploy_adapter", "get_vps_deploy_status"),
        "tools": [
            _tool("vps_status", kind="status"),
            _tool("vps_login_check", kind="read"),
            _tool("vps_sync_preview", kind="preview"),
            _tool("vps_sync_execute", kind="write", requires_approval=True),
            _tool("vps_ui_sync_preview", kind="preview"),
            _tool("vps_ui_sync_execute", kind="write", requires_approval=True),
            _tool("chroma_sync_preview", kind="preview"),
            _tool("chroma_sync_execute", kind="write", requires_approval=True),
        ],
        "routes": [{"method": "POST", "path": "/agent/tool", "tool_name": "vps_sync_preview"}],
        "setup": {"credential": "SSH config/agent outside API payloads", "env": "WINTRIP_VPS_*"},
    },
    {
        "id": "local_computer",
        "name": "Local Computer Tools",
        "provider": "ToolBridge/Roo",
        "category": "Computer",
        "description": "Workspace reads, safe shell, tests and patch operations through local guarded tools.",
        "default_enabled": True,
        "private_read_requires_approval": False,
        "write_requires_approval": True,
        "static_status": "ready",
        "tools": [
            _tool("read_file", kind="read"),
            _tool("list_files", kind="read"),
            _tool("search_files", kind="read"),
            _tool("safe_shell", kind="shell", requires_approval=True),
            _tool("run_tests", kind="shell", requires_approval=True),
            _tool("write_file", kind="write", requires_approval=True),
            _tool("apply_patch", kind="write", requires_approval=True),
            _tool("roo_apply_patch", kind="write", requires_approval=True),
            _tool("roo_execute_command", kind="shell", requires_approval=True),
        ],
        "routes": [{"method": "POST", "path": "/api/agent-runtime/tools/run"}],
        "setup": {"credential": "Local workspace only", "env": "WINTRIP_WORKSPACE"},
    },
    {
        "id": "agent_runtime",
        "name": "Agent Runtime",
        "provider": "Codex/Roo/Slash Agents",
        "category": "Agents",
        "description": "Background jobs for Codex, Roo and function-building flows.",
        "default_enabled": True,
        "private_read_requires_approval": False,
        "write_requires_approval": True,
        "static_status": "ready",
        "tools": [
            _tool("codex_job_start", kind="agent_job", requires_approval=True),
            _tool("resolve_or_build_function", kind="agent_job", requires_approval=True),
            _tool("roo_apply_patch_preview", kind="preview"),
            _tool("roo_attempt_completion", kind="agent_job"),
        ],
        "routes": [{"method": "POST", "path": "/api/agent-runtime/jobs"}],
        "setup": {"credential": "Local agent CLIs", "env": "WINTRIP_*_PATH"},
    },
    {
        "id": "training_memory",
        "name": "Training Memory",
        "provider": "Ouroboros 11D Memory",
        "category": "Memory",
        "description": "Approved learning ingestion and Hippocampus inspection.",
        "default_enabled": True,
        "private_read_requires_approval": False,
        "write_requires_approval": True,
        "static_status": "ready",
        "tools": [
            _tool("training_ingest", kind="memory_write", requires_approval=True),
            _tool("scrub_browser_content", kind="preview"),
            _tool("inspect_hippocampus", kind="read"),
            _tool("self_training_plan", kind="preview"),
            _tool("self_training_step", kind="agent_job", requires_approval=True),
        ],
        "routes": [{"method": "POST", "path": "/api/ouroboros/training/ingest"}],
        "setup": {"credential": "Local Chroma/Ouroboros memory", "env": "WINTRIP_DB_PATH"},
    },
)
