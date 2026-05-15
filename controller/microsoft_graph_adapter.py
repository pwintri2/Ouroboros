"""Local-first Microsoft Graph and Microsoft 365 adapter.

Purpose:
    Provide a safe Microsoft 365/Graph surface for Entra ID, Teams, OneDrive,
    calendar and SharePoint site discovery.
Inputs:
    Local token metadata, optional offline fixtures and exact Akkoord for live
    Graph reads or any write/automation action.
Outputs:
    Sanitized token status, fixture/live read results, write action previews and
    11D Microsoft object records.
Safety notes:
    Live HTTP calls are disabled unless both Akkoord is supplied and
    WINTRIP_ALLOW_LIVE_MICROSOFT_GRAPH=1 is set. Tokens are never returned.
Akkoord requirements:
    Required for live Graph calls and Power Automate execution.

Why this change:
    The buildplan asks for Microsoft 365 mastery without leaking credentials or
    faking tenant access. This adapter gives tests and UI a truthful foundation.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def microsoft_graph_state_path() -> Path:
    return (workspace_root() / ".secrets" / "microsoft_graph_adapter.json").resolve()


def default_graph_token_path() -> Path:
    configured = os.getenv("WINTRIP_MICROSOFT_GRAPH_TOKEN_PATH")
    return Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "microsoft_graph_token.json").resolve()


def get_microsoft_graph_status() -> dict[str, Any]:
    return MicrosoftGraphAdapter().status()


class MicrosoftGraphAdapter:
    def __init__(self, token_path: str | Path | None = None, fixtures: dict[str, Any] | None = None) -> None:
        self.token_path = Path(token_path).expanduser().resolve() if token_path else default_graph_token_path()
        self.fixtures = fixtures or {}

    def status(self) -> dict[str, Any]:
        token = self._token_metadata()
        return {
            "status": "connected" if token["exists"] else "token_missing",
            "adapter": "microsoft_graph",
            "token": token,
            "live_api_enabled": _live_api_enabled(),
            "read_requires_approval_for_live_api": True,
            "write_requires_approval": True,
            "supported_methods": [
                "get_me",
                "list_teams",
                "get_sharepoint_sites",
                "list_onedrive_files",
                "read_outlook_messages",
                "get_calendar",
                "run_power_automate_flow",
            ],
            "state_path": str(microsoft_graph_state_path()),
            "fake_success": False,
        }

    def get_me(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("me")
        if fixture is not None:
            return self._fixture_result("me", [fixture])
        return self._live_get(approval=approval, path="/me", result_key=None, operation="get_me")

    def list_teams(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("teams")
        if fixture is not None:
            return self._fixture_result("teams", list(fixture))
        return self._live_get(approval=approval, path="/me/joinedTeams", result_key="value", operation="list_teams")

    def get_sharepoint_sites(self, approval: str = "", search: str = "*") -> dict[str, Any]:
        fixture = self.fixtures.get("sharepoint_sites")
        if fixture is not None:
            return self._fixture_result("sharepoint_sites", list(fixture))
        encoded = urllib.parse.quote(search)
        return self._live_get(approval=approval, path=f"/sites?search={encoded}", result_key="value", operation="get_sharepoint_sites")

    def list_onedrive_files(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("onedrive_files")
        if fixture is not None:
            return self._fixture_result("onedrive_files", list(fixture))
        return self._live_get(approval=approval, path="/me/drive/root/children", result_key="value", operation="list_onedrive_files")

    def read_outlook_messages(self, approval: str = "", folder: str = "inbox", max_results: int = 10) -> dict[str, Any]:
        fixture = self.fixtures.get("outlook_messages")
        limit = max(1, min(int(max_results or 10), 25))
        if fixture is not None:
            return self._fixture_result("outlook_messages", list(fixture)[:limit])
        clean_folder = str(folder or "inbox").strip() or "inbox"
        encoded_folder = urllib.parse.quote(clean_folder, safe="")
        select = urllib.parse.quote("id,subject,from,receivedDateTime,bodyPreview,webLink", safe=",")
        path = f"/me/mailFolders/{encoded_folder}/messages?$top={limit}&$select={select}"
        return self._live_get(approval=approval, path=path, result_key="value", operation="read_outlook_messages")

    def get_calendar(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("calendar_events")
        if fixture is not None:
            return self._fixture_result("calendar_events", list(fixture))
        return self._live_get(approval=approval, path="/me/events?$top=25", result_key="value", operation="get_calendar")

    def run_power_automate_flow(self, flow_id: str, payload: dict[str, Any] | None = None, approval: str = "") -> dict[str, Any]:
        plan = {
            "operation": "run_power_automate_flow",
            "flow_id": flow_id,
            "payload_preview": redact_sensitive_text(json.dumps(payload or {}, sort_keys=True), max_chars=1000),
            "rollback_plan": "Disable or undo the downstream flow result manually; flow executions are not generally reversible.",
            "approval_required": True,
        }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        if not _live_api_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Microsoft Graph API disabled by policy.", "plan": plan, "fake_success": False}
        return {"status": "disabled", "executed": False, "reason": "Power Automate execution endpoint is tenant-specific and not configured.", "plan": plan, "fake_success": False}

    def map_object_to_11d(self, item: dict[str, Any], record_type: str = "microsoft_object") -> dict[str, Any]:
        return _microsoft_object_record(record_type, item)

    def _fixture_result(self, operation: str, items: list[Any]) -> dict[str, Any]:
        records = [_microsoft_object_record(operation, item if isinstance(item, dict) else {"value": item}) for item in items]
        _save_state({"last_operation": operation, "last_status": "success", "last_source": "fixture", "updated_at": datetime.utcnow().isoformat()})
        return {
            "status": "success",
            "source": "fixture",
            "operation": operation,
            "count": len(items),
            "items": items,
            "records_11d": records,
            "fake_success": False,
        }

    def _live_get(self, approval: str, path: str, result_key: str | None, operation: str) -> dict[str, Any]:
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord' for live Graph reads.", "operation": operation, "fake_success": False}
        if not _live_api_enabled():
            return {"status": "disabled", "reason": "Live Microsoft Graph API disabled by policy.", "operation": operation, "fake_success": False}
        token = self._raw_access_token()
        if not token:
            return {"status": "error", "reason": "No local Microsoft Graph access token available.", "operation": operation, "fake_success": False}
        try:
            request = urllib.request.Request(
                GRAPH_BASE + path,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            items: list[Any]
            if result_key is None:
                items = [payload]
            else:
                items = payload.get(result_key, []) if isinstance(payload, dict) else []
            records = [_microsoft_object_record(operation, item) for item in items if isinstance(item, dict)]
            _save_state({"last_operation": operation, "last_status": "success", "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
            return {"status": "success", "source": "live_api", "operation": operation, "count": len(items), "items": items, "records_11d": records, "fake_success": False}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "error", "reason": redact_sensitive_text(str(exc)), "operation": operation, "fake_success": False}

    def _token_metadata(self) -> dict[str, Any]:
        if not self.token_path.exists():
            return {"exists": False, "path": str(self.token_path), "scopes": [], "tenant_id": "", "secrets_returned": False}
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            scopes = data.get("scopes") or data.get("scope") or []
            if isinstance(scopes, str):
                scopes = scopes.split()
            roles = data.get("roles") or data.get("app_roles") or []
            return {
                "exists": True,
                "path": str(self.token_path),
                "tenant_id": data.get("tenant_id") or data.get("tid") or "",
                "scopes": list(scopes)[:50],
                "roles": list(roles)[:50] if isinstance(roles, list) else [],
                "expires_at": data.get("expires_at") or data.get("expires_on") or "",
                "secrets_returned": False,
            }
        except Exception as exc:
            return {"exists": True, "path": str(self.token_path), "status": "error", "reason": str(exc), "secrets_returned": False}

    def _raw_access_token(self) -> str:
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            return str(data.get("access_token") or "")
        except Exception:
            return ""


def _microsoft_object_record(record_type: str, item: dict[str, Any]) -> dict[str, Any]:
    permission_hint = item.get("roles") or item.get("permissions") or item.get("webUrl") or ""
    modified = str(item.get("lastModifiedDateTime") or item.get("createdDateTime") or "")
    return build_11d_record(
        source="microsoft_graph_adapter",
        record_type=record_type,
        title=str(item.get("displayName") or item.get("name") or item.get("subject") or item.get("id") or item.get("value") or record_type),
        summary=json.dumps({key: item.get(key) for key in ("id", "displayName", "name", "webUrl", "lastModifiedDateTime")}, sort_keys=True),
        signals={
            "driver_or_api_health": 0.8,
            "network_pressure": 0.4,
            "identity_or_auth_state": 0.65,
            "permission_complexity": 0.75 if permission_hint else 0.45,
            "freshness": 0.9 if modified else 0.5,
            "importance": 0.8 if item.get("webUrl") else 0.6,
            "safety_risk": 0.35,
        },
        metadata={"id": item.get("id", ""), "modified": modified, "has_web_url": bool(item.get("webUrl"))},
    )


def _live_api_enabled() -> bool:
    return os.getenv("WINTRIP_ALLOW_LIVE_MICROSOFT_GRAPH", "").strip() == "1"


def _save_state(state: dict[str, Any]) -> None:
    path = microsoft_graph_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
