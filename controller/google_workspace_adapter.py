"""Local-first Google Workspace adapter.

Purpose:
    Represent Google Drive, Gmail, Calendar and GCP operations through a safe
    local adapter that can use simulated fixtures today and live APIs only when
    explicitly enabled.
Inputs:
    Local OAuth token metadata, optional offline fixtures and exact Akkoord for
    any operation that would call Google or mutate user data.
Outputs:
    Token status, read previews, approval-gated write plans and 11D records for
    Google objects.
Safety notes:
    Secrets are never returned. Live HTTP calls are disabled unless both
    Akkoord is supplied and WINTRIP_ALLOW_LIVE_GOOGLE_API=1 is set.
Akkoord requirements:
    Required for live read calls and all write actions.

Why this change:
    Ouroboros needs a Google ecosystem surface that can be tested locally now,
    while preserving strict approval and no-fake-success behavior.
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

from controller.ecosystem_11d import build_11d_record, clamp01, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
GOOGLE_API_BASE = "https://www.googleapis.com"


def google_workspace_state_path() -> Path:
    return (workspace_root() / ".secrets" / "google_workspace_adapter.json").resolve()


def default_google_token_path() -> Path:
    configured = os.getenv("WINTRIP_GOOGLE_TOKEN_PATH")
    return Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "google_workspace_token.json").resolve()


def get_google_workspace_status() -> dict[str, Any]:
    return GoogleWorkspaceAdapter().status()


class GoogleWorkspaceAdapter:
    def __init__(self, token_path: str | Path | None = None, fixtures: dict[str, Any] | None = None) -> None:
        self.token_path = Path(token_path).expanduser().resolve() if token_path else default_google_token_path()
        self.fixtures = fixtures or {}

    def status(self) -> dict[str, Any]:
        token = self._token_metadata()
        return {
            "status": "connected" if token["exists"] else "token_missing",
            "adapter": "google_workspace",
            "token": token,
            "live_api_enabled": _live_api_enabled(),
            "read_requires_approval_for_live_api": True,
            "write_requires_approval": True,
            "supported_methods": [
                "list_drive_files",
                "upload_file",
                "get_calendar_events",
                "send_gmail",
                "search_gmail",
                "gcp_list_projects",
            ],
            "state_path": str(google_workspace_state_path()),
            "fake_success": False,
        }

    def list_drive_files(self, approval: str = "", page_size: int = 25) -> dict[str, Any]:
        fixture = self.fixtures.get("drive_files")
        if fixture is not None:
            files = list(fixture)[: max(1, min(int(page_size), 100))]
            return self._fixture_result("drive_files", files)
        return self._live_get(
            approval=approval,
            path=f"/drive/v3/files?pageSize={max(1, min(int(page_size), 100))}&fields=files(id,name,mimeType,modifiedTime,owners,shared,webViewLink)",
            result_key="files",
            operation="list_drive_files",
        )

    def get_calendar_events(self, approval: str = "", calendar_id: str = "primary", max_results: int = 20) -> dict[str, Any]:
        fixture = self.fixtures.get("calendar_events")
        if fixture is not None:
            return self._fixture_result("calendar_events", list(fixture)[: max(1, min(int(max_results), 100))])
        path = f"/calendar/v3/calendars/{calendar_id}/events?maxResults={max(1, min(int(max_results), 100))}&singleEvents=true&orderBy=startTime"
        return self._live_get(approval=approval, path=path, result_key="items", operation="get_calendar_events")

    def search_gmail(self, query: str, approval: str = "", max_results: int = 10) -> dict[str, Any]:
        fixture = self.fixtures.get("gmail_messages")
        if fixture is not None:
            lowered = query.lower()
            messages = [item for item in fixture if lowered in json.dumps(item, sort_keys=True).lower()]
            return self._fixture_result("gmail_messages", messages[: max(1, min(int(max_results), 50))])
        encoded_query = urllib.parse.quote(query)
        path = f"/gmail/v1/users/me/messages?q={encoded_query}&maxResults={max(1, min(int(max_results), 50))}"
        return self._live_get(approval=approval, path=path, result_key="messages", operation="search_gmail")

    def gcp_list_projects(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("gcp_projects")
        if fixture is not None:
            return self._fixture_result("gcp_projects", list(fixture))
        return self._live_get(approval=approval, path="/cloudresourcemanager/v1/projects", result_key="projects", operation="gcp_list_projects")

    def upload_file(self, local_path: str, drive_folder_id: str = "", approval: str = "") -> dict[str, Any]:
        plan = {
            "operation": "upload_file",
            "local_path": str(local_path),
            "drive_folder_id": drive_folder_id,
            "rollback_plan": "Delete the uploaded Drive file version if the live API execution is enabled and succeeds.",
            "approval_required": True,
        }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        if not _live_api_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Google API disabled by policy.", "plan": plan, "fake_success": False}
        return {"status": "disabled", "executed": False, "reason": "Multipart Drive upload is not enabled in this adapter yet.", "plan": plan, "fake_success": False}

    def send_gmail(self, to: str, subject: str, body: str, approval: str = "") -> dict[str, Any]:
        plan = {
            "operation": "send_gmail",
            "to": to,
            "subject": subject,
            "body_preview": redact_sensitive_text(body, max_chars=500),
            "rollback_plan": "Gmail sends cannot be undone; create a clarifying follow-up if needed.",
            "approval_required": True,
        }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        if not _live_api_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Google API disabled by policy.", "plan": plan, "fake_success": False}
        return {"status": "disabled", "executed": False, "reason": "Live Gmail send is intentionally not implemented in this foundation pass.", "plan": plan, "fake_success": False}

    def map_drive_object_to_11d(self, item: dict[str, Any]) -> dict[str, Any]:
        return _google_object_record("drive_file", item)

    def _fixture_result(self, operation: str, items: list[Any]) -> dict[str, Any]:
        records = [_google_object_record(operation, item if isinstance(item, dict) else {"value": item}) for item in items]
        result = {
            "status": "success",
            "source": "fixture",
            "operation": operation,
            "count": len(items),
            "items": items,
            "records_11d": records,
            "fake_success": False,
        }
        _save_state({"last_operation": operation, "last_status": "success", "last_source": "fixture", "updated_at": datetime.utcnow().isoformat()})
        return result

    def _live_get(self, approval: str, path: str, result_key: str, operation: str) -> dict[str, Any]:
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord' for live Google API reads.", "operation": operation, "fake_success": False}
        if not _live_api_enabled():
            return {"status": "disabled", "reason": "Live Google API disabled by policy.", "operation": operation, "fake_success": False}
        token = self._raw_access_token()
        if not token:
            return {"status": "error", "reason": "No local Google access token available.", "operation": operation, "fake_success": False}
        try:
            request = urllib.request.Request(
                GOOGLE_API_BASE + path,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            items = payload.get(result_key, []) if isinstance(payload, dict) else []
            records = [_google_object_record(operation, item) for item in items if isinstance(item, dict)]
            _save_state({"last_operation": operation, "last_status": "success", "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
            return {"status": "success", "source": "live_api", "operation": operation, "count": len(items), "items": items, "records_11d": records, "fake_success": False}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "error", "reason": redact_sensitive_text(str(exc)), "operation": operation, "fake_success": False}

    def _token_metadata(self) -> dict[str, Any]:
        if not self.token_path.exists():
            return {"exists": False, "path": str(self.token_path), "scopes": [], "expires_at": "", "secrets_returned": False}
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            scopes = data.get("scopes") or data.get("scope") or []
            if isinstance(scopes, str):
                scopes = scopes.split()
            return {
                "exists": True,
                "path": str(self.token_path),
                "scopes": list(scopes)[:50],
                "expires_at": data.get("expiry") or data.get("expires_at") or "",
                "token_type": data.get("token_type", ""),
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


def _google_object_record(record_type: str, item: dict[str, Any]) -> dict[str, Any]:
    modified = str(item.get("modifiedTime") or item.get("updated") or "")
    shared = bool(item.get("shared") or item.get("sharedWithMeTime"))
    owners = item.get("owners") or []
    importance = 0.75 if shared else 0.55
    return build_11d_record(
        source="google_workspace_adapter",
        record_type=record_type,
        title=str(item.get("name") or item.get("summary") or item.get("id") or item.get("value") or record_type),
        summary=json.dumps({key: item.get(key) for key in ("id", "name", "mimeType", "modifiedTime", "summary")}, sort_keys=True),
        signals={
            "driver_or_api_health": 0.8,
            "network_pressure": 0.35,
            "identity_or_auth_state": 0.55,
            "permission_complexity": 0.65 if shared else 0.35,
            "freshness": 0.9 if modified else 0.5,
            "importance": importance,
            "safety_risk": 0.3 if owners else 0.2,
        },
        metadata={"id": item.get("id", ""), "modified": modified, "shared": shared},
    )


def _live_api_enabled() -> bool:
    return os.getenv("WINTRIP_ALLOW_LIVE_GOOGLE_API", "").strip() == "1"


def _save_state(state: dict[str, Any]) -> None:
    path = google_workspace_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
