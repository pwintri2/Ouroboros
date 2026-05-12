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
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, clamp01, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
GOOGLE_API_BASE = "https://www.googleapis.com"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SYSTEM_LABELS = {
    "CHAT",
    "SENT",
    "INBOX",
    "IMPORTANT",
    "TRASH",
    "DRAFT",
    "SPAM",
    "CATEGORY_FORUMS",
    "CATEGORY_UPDATES",
    "CATEGORY_PERSONAL",
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "STARRED",
    "UNREAD",
}


def google_workspace_state_path() -> Path:
    return (workspace_root() / ".secrets" / "google_workspace_adapter.json").resolve()


def default_google_token_path() -> Path:
    configured = os.getenv("WINTRIP_GOOGLE_TOKEN_PATH")
    return Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "google_workspace_token.json").resolve()


def get_google_workspace_status() -> dict[str, Any]:
    return GoogleWorkspaceAdapter().status()


class GoogleWorkspaceAdapter:
    def __init__(
        self,
        token_path: str | Path | None = None,
        fixtures: dict[str, Any] | None = None,
        *,
        live_api_enabled: bool | None = None,
    ) -> None:
        self.token_path = Path(token_path).expanduser().resolve() if token_path else default_google_token_path()
        self.fixtures = fixtures or {}
        self.live_api_enabled = live_api_enabled

    def status(self) -> dict[str, Any]:
        token = self._token_metadata()
        return {
            "status": "connected" if token["exists"] else "token_missing",
            "adapter": "google_workspace",
            "token": token,
            "live_api_enabled": self._live_enabled(),
            "read_requires_approval_for_live_api": True,
            "write_requires_approval": True,
            "supported_methods": [
                "list_drive_files",
                "upload_file",
                "upload_text_file",
                "get_calendar_events",
                "send_gmail",
                "search_gmail",
                "manage_gmail",
                "label_gmail",
                "archive_gmail",
                "move_gmail",
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
        clean_query = str(query or "in:inbox").strip() or "in:inbox"
        ids_result = self._gmail_message_ids(query=clean_query, approval=approval, max_results=max_results)
        if ids_result.get("status") != "success":
            return ids_result
        messages: list[dict[str, Any]] = []
        for message_id in ids_result.get("message_ids", []):
            detail = self._request_json(
                approval=approval,
                method="GET",
                path="/gmail/v1/users/me/messages/"
                + urllib.parse.quote(str(message_id), safe="")
                + "?"
                + urllib.parse.urlencode(
                    [
                        ("format", "metadata"),
                        ("metadataHeaders", "From"),
                        ("metadataHeaders", "To"),
                        ("metadataHeaders", "Subject"),
                        ("metadataHeaders", "Date"),
                    ]
                ),
                operation="get_gmail_message",
            )
            if detail.get("status") == "success":
                messages.append(_compact_gmail_message(detail.get("payload") if isinstance(detail.get("payload"), dict) else {}))
            else:
                messages.append({"id": message_id, "status": "detail_error", "reason": detail.get("reason", "")})
        _save_state({"last_operation": "search_gmail", "last_status": "success", "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
        return {
            "status": "success",
            "source": "live_api",
            "operation": "search_gmail",
            "query": clean_query,
            "count": len(messages),
            "message_ids": ids_result.get("message_ids", []),
            "messages": messages,
            "items": messages,
            "fake_success": False,
        }

    def gcp_list_projects(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("gcp_projects")
        if fixture is not None:
            return self._fixture_result("gcp_projects", list(fixture))
        return self._live_get(approval=approval, path="/cloudresourcemanager/v1/projects", result_key="projects", operation="gcp_list_projects")

    def upload_file(self, local_path: str, drive_folder_id: str = "", approval: str = "") -> dict[str, Any]:
        safe_path = _safe_workspace_file(local_path)
        plan = {
            "operation": "upload_file",
            "local_path": str(local_path),
            "drive_folder_id": drive_folder_id,
            "rollback_plan": "Delete the uploaded Drive file version if the live API execution is enabled and succeeds.",
            "approval_required": True,
        }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        if not self._live_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Google API disabled by policy.", "plan": plan, "fake_success": False}
        if safe_path.get("status") != "success":
            return {"status": "error", "executed": False, "reason": safe_path.get("reason", "Invalid local path."), "plan": plan, "fake_success": False}
        target = Path(safe_path["path"])
        mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return self._upload_drive_bytes(
            name=target.name,
            content=target.read_bytes(),
            mime_type=mime_type,
            drive_folder_id=drive_folder_id,
            approval=approval,
            plan=plan,
        )

    def upload_text_file(self, name: str, content: str, drive_folder_id: str = "", approval: str = "") -> dict[str, Any]:
        plan = {
            "operation": "upload_text_file",
            "name": str(name or "ouroboros-agent-output.txt"),
            "drive_folder_id": drive_folder_id,
            "rollback_plan": "Delete the uploaded Drive file if needed.",
            "approval_required": True,
        }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        if not self._live_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Google API disabled by policy.", "plan": plan, "fake_success": False}
        clean_name = Path(str(name or "ouroboros-agent-output.txt")).name or "ouroboros-agent-output.txt"
        return self._upload_drive_bytes(
            name=clean_name,
            content=str(content or "").encode("utf-8"),
            mime_type="text/plain; charset=utf-8",
            drive_folder_id=drive_folder_id,
            approval=approval,
            plan=plan,
        )

    def send_gmail(self, to: str, subject: str, body: str, approval: str = "", from_addr: str = "") -> dict[str, Any]:
        import base64
        import email.mime.text
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
        if not self._live_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Google API disabled by policy.", "plan": plan, "fake_success": False}
        token = self._raw_access_token()
        if not token:
            return {"status": "error", "executed": False, "reason": "No local Google access token available.", "plan": plan, "fake_success": False}
        msg = email.mime.text.MIMEText(str(body or ""), "plain", "utf-8")
        msg["To"] = str(to or "")
        msg["Subject"] = str(subject or "")
        if from_addr:
            msg["From"] = str(from_addr)
        raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        payload = {"raw": raw_bytes}
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            request = urllib.request.Request(
                GOOGLE_API_BASE + "/gmail/v1/users/me/messages/send",
                data=data,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                resp_payload = json.loads(response.read().decode("utf-8"))
            _save_state({"last_operation": "send_gmail", "last_status": "success", "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
            return {
                "status": "success",
                "executed": True,
                "source": "live_api",
                "operation": "send_gmail",
                "message_id": resp_payload.get("id", ""),
                "thread_id": resp_payload.get("threadId", ""),
                "to": to,
                "subject": subject,
                "plan": plan,
                "fake_success": False,
            }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            details = _google_error_details(exc)
            status = "configuration_required" if details.get("configuration_required") else "error"
            return {
                "status": status,
                "executed": False,
                "reason": details.get("message") or details.get("reason") or "Google API request failed.",
                "google_error": details,
                "activation_url": details.get("activation_url", ""),
                "next_action": details.get("next_action", "Controleer Google API/OAuth configuratie."),
                "plan": plan,
                "fake_success": False,
            }

    def manage_gmail(
        self,
        *,
        query: str = "",
        message_ids: list[str] | None = None,
        add_label: str = "",
        remove_label_ids: list[str] | None = None,
        archive: bool = False,
        mark_read: bool = False,
        approval: str = "",
        max_results: int = 10,
    ) -> dict[str, Any]:
        fixture = self.fixtures.get("gmail_messages")
        if fixture is not None:
            return {
                "status": "success",
                "source": "fixture",
                "operation": "manage_gmail",
                "executed": False,
                "reason": "Fixture mode records the requested Gmail management action without live side effects.",
                "matched_count": min(len(fixture), max(1, min(int(max_results or 10), 50))),
                "fake_success": False,
            }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "operation": "manage_gmail", "fake_success": False}
        if not self._live_enabled():
            return {"status": "approval_recorded", "executed": False, "reason": "Live Google API disabled by policy.", "operation": "manage_gmail", "fake_success": False}

        clean_ids = [str(item).strip() for item in (message_ids or []) if str(item).strip()]
        clean_query = str(query or "in:inbox").strip() or "in:inbox"
        if not clean_ids:
            ids_result = self._gmail_message_ids(query=clean_query, approval=approval, max_results=max_results)
            if ids_result.get("status") != "success":
                return ids_result
            clean_ids = list(ids_result.get("message_ids") or [])
        if not clean_ids:
            return {
                "status": "noop",
                "source": "live_api",
                "operation": "manage_gmail",
                "executed": False,
                "query": clean_query,
                "matched_count": 0,
                "modified_count": 0,
                "fake_success": False,
            }

        add_label_ids: list[str] = []
        label_name = str(add_label or "").strip()
        if label_name:
            label_result = self._ensure_gmail_label(label_name, approval=approval)
            if label_result.get("status") != "success":
                return label_result
            add_label_ids.append(str(label_result.get("label_id") or ""))

        remove_ids = [str(item).strip() for item in (remove_label_ids or []) if str(item).strip()]
        if archive and "INBOX" not in remove_ids:
            remove_ids.append("INBOX")
        if mark_read and "UNREAD" not in remove_ids:
            remove_ids.append("UNREAD")
        add_label_ids = [item for item in add_label_ids if item]
        if not add_label_ids and not remove_ids:
            return {"status": "noop", "operation": "manage_gmail", "reason": "No Gmail label/archive mutation requested.", "message_ids": clean_ids, "fake_success": False}

        modified: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for message_id in clean_ids[: max(1, min(int(max_results or 10), 50))]:
            result = self._request_json(
                approval=approval,
                method="POST",
                path=f"/gmail/v1/users/me/messages/{urllib.parse.quote(message_id, safe='')}/modify",
                operation="manage_gmail",
                payload={"addLabelIds": add_label_ids, "removeLabelIds": remove_ids},
            )
            if result.get("status") == "success":
                modified.append(_compact_gmail_message(result.get("payload") if isinstance(result.get("payload"), dict) else {"id": message_id}))
            else:
                errors.append({"id": message_id, "status": result.get("status"), "reason": result.get("reason", "")})
        status = "success" if modified and not errors else ("partial" if modified else "error")
        _save_state({"last_operation": "manage_gmail", "last_status": status, "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
        return {
            "status": status,
            "source": "live_api",
            "operation": "manage_gmail",
            "executed": bool(modified),
            "query": clean_query,
            "add_label_ids": add_label_ids,
            "remove_label_ids": remove_ids,
            "matched_count": len(clean_ids),
            "modified_count": len(modified),
            "modified": modified,
            "errors": errors,
            "fake_success": False,
        }

    def label_gmail(self, query: str, label: str, approval: str = "", max_results: int = 10) -> dict[str, Any]:
        return self.manage_gmail(query=query, add_label=label, approval=approval, max_results=max_results)

    def archive_gmail(self, query: str, approval: str = "", max_results: int = 10) -> dict[str, Any]:
        return self.manage_gmail(query=query, archive=True, approval=approval, max_results=max_results)

    def move_gmail(self, query: str, label: str, approval: str = "", max_results: int = 10) -> dict[str, Any]:
        return self.manage_gmail(query=query, add_label=label, archive=True, approval=approval, max_results=max_results)

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
        if not self._live_enabled():
            return {"status": "disabled", "reason": "Live Google API disabled by policy.", "operation": operation, "fake_success": False}
        response = self._request_json(approval=approval, method="GET", path=path, operation=operation)
        if response.get("status") != "success":
            return response
        payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
        items = payload.get(result_key, []) if isinstance(payload, dict) else []
        records = [_google_object_record(operation, item) for item in items if isinstance(item, dict)]
        _save_state({"last_operation": operation, "last_status": "success", "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
        return {"status": "success", "source": "live_api", "operation": operation, "count": len(items), "items": items, "records_11d": records, "fake_success": False}

    def _request_json(
        self,
        *,
        approval: str,
        method: str,
        path: str,
        operation: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "operation": operation, "fake_success": False}
        if not self._live_enabled():
            return {"status": "disabled", "reason": "Live Google API disabled by policy.", "operation": operation, "fake_success": False}
        token = self._raw_access_token()
        if not token:
            return {"status": "error", "reason": "No local Google access token available.", "operation": operation, "fake_success": False}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            request = urllib.request.Request(
                GOOGLE_API_BASE + path,
                data=data,
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(request, timeout=max(5, min(int(timeout_seconds or 20), 60))) as response:
                raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw.strip() else {}
            return {"status": "success", "source": "live_api", "operation": operation, "payload": parsed, "fake_success": False}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "error", "reason": _safe_google_error(exc), "operation": operation, "fake_success": False}

    def _gmail_message_ids(self, *, query: str, approval: str, max_results: int) -> dict[str, Any]:
        encoded = urllib.parse.urlencode({"q": str(query or "in:inbox"), "maxResults": max(1, min(int(max_results or 10), 50))})
        result = self._request_json(approval=approval, method="GET", path=f"/gmail/v1/users/me/messages?{encoded}", operation="search_gmail")
        if result.get("status") != "success":
            return result
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        ids = [str(item.get("id") or "").strip() for item in messages if isinstance(item, dict) and str(item.get("id") or "").strip()]
        return {"status": "success", "source": "live_api", "operation": "search_gmail", "message_ids": ids, "count": len(ids), "fake_success": False}

    def _ensure_gmail_label(self, label_name: str, *, approval: str) -> dict[str, Any]:
        clean = str(label_name or "").strip().strip("/")
        if not clean:
            return {"status": "error", "operation": "ensure_gmail_label", "reason": "Gmail label name is empty.", "fake_success": False}
        if clean.upper() in GMAIL_SYSTEM_LABELS:
            return {"status": "success", "operation": "ensure_gmail_label", "label_id": clean.upper(), "label_name": clean.upper(), "created": False, "fake_success": False}
        labels = self._request_json(approval=approval, method="GET", path="/gmail/v1/users/me/labels", operation="list_gmail_labels")
        if labels.get("status") != "success":
            return labels
        payload = labels.get("payload") if isinstance(labels.get("payload"), dict) else {}
        for item in payload.get("labels", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "").casefold() == clean.casefold() or str(item.get("id") or "").casefold() == clean.casefold():
                return {"status": "success", "operation": "ensure_gmail_label", "label_id": str(item.get("id") or ""), "label_name": str(item.get("name") or clean), "created": False, "fake_success": False}
        created = self._request_json(
            approval=approval,
            method="POST",
            path="/gmail/v1/users/me/labels",
            operation="create_gmail_label",
            payload={"name": clean, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        )
        if created.get("status") != "success":
            return created
        label = created.get("payload") if isinstance(created.get("payload"), dict) else {}
        return {"status": "success", "operation": "ensure_gmail_label", "label_id": str(label.get("id") or clean), "label_name": str(label.get("name") or clean), "created": True, "fake_success": False}

    def _upload_drive_bytes(
        self,
        *,
        name: str,
        content: bytes,
        mime_type: str,
        drive_folder_id: str,
        approval: str,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        token = self._raw_access_token()
        if not token:
            return {"status": "error", "executed": False, "reason": "No local Google access token available.", "plan": plan, "fake_success": False}
        boundary = f"ouroboros-{uuid.uuid4().hex}"
        metadata: dict[str, Any] = {"name": Path(str(name or "ouroboros-agent-output.txt")).name}
        if str(drive_folder_id or "").strip():
            metadata["parents"] = [str(drive_folder_id).strip()]
        body = b"".join(
            [
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("utf-8"),
                json.dumps(metadata).encode("utf-8"),
                b"\r\n",
                f"--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        try:
            request = urllib.request.Request(
                GOOGLE_API_BASE + "/upload/drive/v3/files?uploadType=multipart&fields=id,name,mimeType,webViewLink,webContentLink",
                data=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            _save_state({"last_operation": plan.get("operation") or "upload_file", "last_status": "success", "last_source": "live_api", "updated_at": datetime.utcnow().isoformat()})
            return {
                "status": "success",
                "source": "live_api",
                "operation": plan.get("operation") or "upload_file",
                "executed": True,
                "file": payload,
                "plan": plan,
                "fake_success": False,
            }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "error", "executed": False, "reason": _safe_google_error(exc), "plan": plan, "fake_success": False}

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
                "has_refresh_token": bool(data.get("refresh_token")),
                "secrets_returned": False,
            }
        except Exception as exc:
            return {"exists": True, "path": str(self.token_path), "status": "error", "reason": str(exc), "secrets_returned": False}

    def _raw_access_token(self) -> str:
        token = self._load_token()
        if not token:
            return ""
        if _token_expired_or_stale(token):
            refreshed = self._refresh_access_token(token)
            if refreshed:
                token = refreshed
        access = str(token.get("access_token") or "")
        if access:
            return access
        refreshed = self._refresh_access_token(token)
        return str((refreshed or {}).get("access_token") or "")

    def _load_token(self) -> dict[str, Any]:
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _refresh_access_token(self, token: dict[str, Any]) -> dict[str, Any] | None:
        refresh_token = str(token.get("refresh_token") or "")
        client_id = str(token.get("client_id") or "")
        client_secret = str(token.get("client_secret") or "")
        if not (refresh_token and client_id and client_secret):
            return None
        try:
            data = urllib.parse.urlencode(
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }
            ).encode("utf-8")
            request = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict) or not payload.get("access_token"):
                return None
            expires_in = int(payload.get("expires_in") or 0)
            merged = dict(token)
            merged.update(payload)
            merged["refresh_token"] = refresh_token
            merged["client_id"] = client_id
            merged["client_secret"] = client_secret
            if expires_in:
                merged["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in))).isoformat()
            self.token_path.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
            try:
                self.token_path.chmod(0o600)
            except OSError:
                pass
            return merged
        except Exception:
            return None

    def _live_enabled(self) -> bool:
        return _live_api_enabled(self.live_api_enabled)


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


def _compact_gmail_message(item: dict[str, Any]) -> dict[str, Any]:
    headers = {}
    for header in ((item.get("payload") or {}).get("headers") or []) if isinstance(item.get("payload"), dict) else []:
        if isinstance(header, dict):
            headers[str(header.get("name") or "").lower()] = str(header.get("value") or "")
    return {
        "id": str(item.get("id") or ""),
        "thread_id": str(item.get("threadId") or ""),
        "label_ids": list(item.get("labelIds") or [])[:40],
        "snippet": redact_sensitive_text(str(item.get("snippet") or ""), max_chars=500),
        "from": redact_sensitive_text(headers.get("from", ""), max_chars=500),
        "to": redact_sensitive_text(headers.get("to", ""), max_chars=500),
        "subject": redact_sensitive_text(headers.get("subject", ""), max_chars=500),
        "date": headers.get("date", "")[:200],
    }


def _safe_google_error(exc: BaseException) -> str:
    return str(_google_error_details(exc).get("reason") or "")


def _google_error_details(exc: BaseException) -> dict[str, Any]:
    status_code = 0
    raw = ""
    if isinstance(exc, urllib.error.HTTPError):
        status_code = int(getattr(exc, "code", 0) or 0)
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
    else:
        raw = str(exc)

    clean_raw = redact_sensitive_text(raw or str(exc), max_chars=2000)
    parsed: dict[str, Any] = {}
    try:
        parsed_payload = json.loads(raw) if raw.strip() else {}
        parsed = parsed_payload if isinstance(parsed_payload, dict) else {}
    except Exception:
        parsed = {}

    error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
    message = redact_sensitive_text(str(error.get("message") or clean_raw), max_chars=1200)
    google_status = str(error.get("status") or "")
    google_reason = ""
    activation_url = ""
    service_title = ""
    details = error.get("details") if isinstance(error.get("details"), list) else []
    for item in details:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        google_reason = google_reason or str(item.get("reason") or metadata.get("reason") or "")
        activation_url = activation_url or str(metadata.get("activationUrl") or "")
        service_title = service_title or str(metadata.get("serviceTitle") or "")
    errors = error.get("errors") if isinstance(error.get("errors"), list) else []
    for item in errors:
        if isinstance(item, dict):
            google_reason = google_reason or str(item.get("reason") or "")
    configuration_required = bool(
        google_reason in {"accessNotConfigured", "SERVICE_DISABLED", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}
        or "has not been used in project" in message
        or "it is disabled" in message
    )
    next_action = ""
    if activation_url:
        next_action = f"Enable {service_title or 'the required Google API'} in Google Cloud, then retry after propagation."
    elif configuration_required:
        next_action = "Enable the required Google API or OAuth scope in Google Cloud, then retry."
    return {
        "status_code": status_code,
        "status": google_status,
        "google_reason": google_reason,
        "message": message,
        "reason": clean_raw,
        "activation_url": activation_url,
        "service_title": service_title,
        "configuration_required": configuration_required,
        "next_action": next_action,
        "secrets_returned": False,
    }


def _safe_workspace_file(local_path: str) -> dict[str, Any]:
    if not str(local_path or "").strip():
        return {"status": "error", "reason": "Local path is required.", "fake_success": False}
    root = workspace_root().resolve()
    candidate = Path(str(local_path)).expanduser()
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return {"status": "error", "reason": "Local path must stay inside the Wintrip workspace.", "fake_success": False}
    if not target.exists() or not target.is_file():
        return {"status": "error", "reason": f"Local file does not exist: {local_path}", "fake_success": False}
    return {"status": "success", "path": str(target), "fake_success": False}


def _token_expired_or_stale(token: dict[str, Any]) -> bool:
    raw = str(token.get("expires_at") or token.get("expiry") or token.get("expires_on") or "").strip()
    if not raw:
        return False
    try:
        normalized = raw.replace("Z", "+00:00")
        expires = datetime.fromisoformat(normalized)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires <= datetime.now(timezone.utc) + timedelta(seconds=60)
    except Exception:
        return False


def _live_api_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return os.getenv("WINTRIP_ALLOW_LIVE_GOOGLE_API", "").strip() == "1"


def _save_state(state: dict[str, Any]) -> None:
    path = google_workspace_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
