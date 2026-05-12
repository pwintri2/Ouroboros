"""Approval-gated Google OAuth setup for the connector cockpit.

The connector toggle only decides whether Ouroboros may use Google tools. This
module handles the missing credential bootstrap: generate an authorization URL,
exchange the returned code, and store the resulting token bundle locally without
ever returning tokens or client secrets in API payloads.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import redact_sensitive_text
from controller.google_workspace_adapter import (
    APPROVAL_PHRASE,
    GOOGLE_TOKEN_URL,
    GoogleWorkspaceAdapter,
    default_google_token_path,
)
from controller.safe_shell import workspace_root


GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_GOOGLE_REDIRECT_URI = "http://127.0.0.1:8010/api/cockpit/connectors/google/oauth/callback"
GOOGLE_SCOPE_PRESETS = {
    "gmail_send": [
        "https://www.googleapis.com/auth/gmail.send",
    ],
    "gmail_read_send": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ],
    "google_workspace_full": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/drive.file",
    ],
}
DEFAULT_GOOGLE_SCOPES = GOOGLE_SCOPE_PRESETS["gmail_send"]
GOOGLE_WORKSPACE_FULL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def google_oauth_client_path() -> Path:
    configured = os.getenv("WINTRIP_GOOGLE_OAUTH_CLIENT_PATH")
    return Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "google_oauth_client.json").resolve()


def google_oauth_pending_code_path() -> Path:
    configured = os.getenv("WINTRIP_GOOGLE_OAUTH_PENDING_CODE_PATH")
    return Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "google_oauth_pending_code.json").resolve()


def google_oauth_last_exchange_path() -> Path:
    configured = os.getenv("WINTRIP_GOOGLE_OAUTH_LAST_EXCHANGE_PATH")
    return Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "google_oauth_last_exchange.json").resolve()


def google_oauth_status() -> dict[str, Any]:
    client = _client_metadata()
    token_status = GoogleWorkspaceAdapter().status().get("token", {})
    token_scopes = _normalize_scopes(token_status.get("scopes"))
    missing_scopes = [scope for scope in DEFAULT_GOOGLE_SCOPES if scope not in token_scopes]
    token_exists = bool(token_status.get("exists"))
    has_refresh_token = bool(token_status.get("has_refresh_token"))
    ready = bool(client.get("configured") and token_exists and has_refresh_token and not missing_scopes)
    return {
        "status": "ready" if ready else ("token_incomplete" if token_exists else "not_configured"),
        "provider": "google",
        "client": client,
        "token": token_status,
        "pending_code": _pending_code_metadata(),
        "last_exchange": _last_exchange_metadata(),
        "required_scopes": list(DEFAULT_GOOGLE_SCOPES),
        "available_scope_presets": GOOGLE_SCOPE_PRESETS,
        "missing_scopes": missing_scopes,
        "redirect_uri": client.get("redirect_uri") or DEFAULT_GOOGLE_REDIRECT_URI,
        "token_path": str(default_google_token_path()),
        "setup_ready": ready,
        "can_send_gmail": ready and "https://www.googleapis.com/auth/gmail.send" in token_scopes,
        "approval_required": True,
        "approval_phrase": APPROVAL_PHRASE,
        "secrets_returned": False,
        "fake_success": False,
    }


def start_google_oauth_flow(
    *,
    client_id: str,
    client_secret: str,
    client_json: str = "",
    redirect_uri: str = "",
    scopes: list[str] | None = None,
    approval: str = "",
) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return _blocked("Google OAuth setup stores a local client secret and requires exact Akkoord.")
    saved_client = _load_client_config()
    resolved = _resolve_client_config(
        client_id=client_id,
        client_secret=client_secret,
        client_json=client_json,
        redirect_uri=redirect_uri,
        scopes=scopes,
        saved_client=saved_client,
    )
    if resolved.get("status") != "success":
        return resolved
    clean_client_id = str(resolved["client_id"])
    clean_client_secret = str(resolved["client_secret"])
    clean_redirect_uri = str(resolved["redirect_uri"])
    clean_scopes = list(resolved["scopes"])
    _write_secret_json(
        google_oauth_client_path(),
        {
            "client_id": clean_client_id,
            "client_secret": clean_client_secret,
            "project_id": str(resolved.get("project_id") or ""),
            "client_type": str(resolved.get("client_type") or "manual"),
            "redirect_uri": clean_redirect_uri,
            "scopes": clean_scopes,
            "updated_at": _now(),
        },
    )
    params = {
        "client_id": clean_client_id,
        "redirect_uri": clean_redirect_uri,
        "response_type": "code",
        "scope": " ".join(clean_scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return {
        "status": "authorization_url_ready",
        "authorization_url": GOOGLE_OAUTH_AUTH_URL + "?" + urllib.parse.urlencode(params),
        "redirect_uri": clean_redirect_uri,
        "scopes": clean_scopes,
        "client_configured": True,
        "project_id_configured": bool(resolved.get("project_id")),
        "client_type": str(resolved.get("client_type") or "manual"),
        "warnings": list(resolved.get("warnings") or []),
        "next_step": "Open the authorization URL, sign in, then paste the returned code into the cockpit.",
        "secrets_returned": False,
        "fake_success": False,
    }


def exchange_google_oauth_code(
    *,
    code: str,
    client_id: str = "",
    client_secret: str = "",
    client_json: str = "",
    redirect_uri: str = "",
    use_pending_code: bool = False,
    approval: str = "",
) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        result = _blocked("Google OAuth code exchange stores refresh credentials and requires exact Akkoord.")
        _record_last_exchange(result)
        return result
    clean_code = _pending_authorization_code() if use_pending_code else _extract_authorization_code(code)
    if not clean_code:
        result = {"status": "blocked", "reason": "Google authorization code is required, or no pending callback code is available.", "fake_success": False}
        _record_last_exchange(result)
        return result

    saved_client = _load_client_config()
    resolved = _resolve_client_config(
        client_id=client_id,
        client_secret=client_secret,
        client_json=client_json,
        redirect_uri=redirect_uri,
        scopes=saved_client.get("scopes") or DEFAULT_GOOGLE_SCOPES,
        saved_client=saved_client,
    )
    if resolved.get("status") != "success":
        _record_last_exchange(resolved)
        return resolved
    clean_client_id = str(resolved["client_id"])
    clean_client_secret = str(resolved["client_secret"])
    clean_redirect_uri = str(resolved["redirect_uri"])

    form = urllib.parse.urlencode(
        {
            "code": clean_code,
            "client_id": clean_client_id,
            "client_secret": clean_client_secret,
            "redirect_uri": clean_redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result = {
            "status": "error",
            "reason": _safe_oauth_error(exc),
            "token_saved": False,
            "using_pending_code": bool(use_pending_code),
            "fake_success": False,
        }
        _record_last_exchange(result)
        return result

    if not isinstance(payload, dict) or not payload.get("access_token"):
        result = {"status": "error", "reason": "Google token endpoint did not return an access token.", "token_saved": False, "using_pending_code": bool(use_pending_code), "fake_success": False}
        _record_last_exchange(result)
        return result

    previous = _load_token_config()
    expires_in = int(payload.get("expires_in") or 0)
    token_data = dict(previous)
    token_data.update(payload)
    token_data["client_id"] = clean_client_id
    token_data["client_secret"] = clean_client_secret
    token_data["project_id"] = str(resolved.get("project_id") or "")
    token_data["client_type"] = str(resolved.get("client_type") or "manual")
    token_data["redirect_uri"] = clean_redirect_uri
    token_data["scopes"] = _normalize_scopes(payload.get("scope") or payload.get("scopes") or saved_client.get("scopes") or DEFAULT_GOOGLE_SCOPES)
    token_data["updated_at"] = _now()
    token_data.setdefault("created_at", _now())
    if expires_in:
        token_data["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in))).isoformat()
    if not token_data.get("refresh_token") and previous.get("refresh_token"):
        token_data["refresh_token"] = previous.get("refresh_token")
    _write_secret_json(default_google_token_path(), token_data)
    _clear_pending_authorization_code()

    status = google_oauth_status()
    result = {
        "status": "token_saved",
        "token_saved": True,
        "has_refresh_token": bool(token_data.get("refresh_token")),
        "missing_scopes": status.get("missing_scopes", []),
        "setup_ready": status.get("setup_ready", False),
        "can_send_gmail": status.get("can_send_gmail", False),
        "project_id_configured": bool(token_data.get("project_id")),
        "token": status.get("token", {}),
        "secrets_returned": False,
        "fake_success": False,
    }
    _record_last_exchange(result)
    return result


def store_google_oauth_callback_code(code: str = "", error: str = "") -> dict[str, Any]:
    clean_code = _extract_authorization_code(code)
    clean_error = redact_sensitive_text(str(error or ""), max_chars=500)
    if not clean_code:
        return {"status": "error" if clean_error else "missing_code", "stored": False, "reason": clean_error or "No authorization code in callback.", "fake_success": False, "secrets_returned": False}
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    _write_secret_json(
        google_oauth_pending_code_path(),
        {
            "code": clean_code,
            "received_at": _now(),
            "expires_at": expires_at,
        },
    )
    return {"status": "stored", "stored": True, "expires_at": expires_at, "secrets_returned": False, "fake_success": False}


def google_oauth_callback_page(code_present: bool, error: str = "", stored: bool = False) -> str:
    clean_error = redact_sensitive_text(str(error or ""), max_chars=500)
    title = "Google OAuth ontvangen" if code_present else "Google OAuth niet voltooid"
    if code_present and stored:
        message = "De Google-code is tijdelijk ontvangen. Ga terug naar de cockpit en klik op Save Callback Code."
    elif code_present:
        message = "Ga terug naar de cockpit en plak de callback-URL in het Google OAuth-paneel."
    else:
        message = clean_error or "Er staat geen code in de callback-URL."
    return f"""<!doctype html>
<html lang="nl">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 40px; max-width: 720px; line-height: 1.5; }}
      code {{ background: #eef2f7; padding: 2px 5px; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>{title}</h1>
    <p>{message}</p>
    <p>De omwisseling gebeurt pas in de cockpit na <code>Akkoord</code>. De code wordt niet in API-output getoond.</p>
  </body>
</html>"""


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "approval_required": True,
        "approval_phrase": APPROVAL_PHRASE,
        "secrets_returned": False,
        "fake_success": False,
    }


def _client_metadata() -> dict[str, Any]:
    path = google_oauth_client_path()
    if not path.exists():
        return {"configured": False, "path": str(path), "scopes": [], "secrets_returned": False}
    data = _load_client_config()
    client_id = str(data.get("client_id") or "").strip()
    validation_reason = _validate_google_client_id(client_id) if client_id else ""
    valid_client_id = bool(client_id and not validation_reason)
    return {
        "configured": bool(valid_client_id and data.get("client_secret")),
        "path": str(path),
        "client_id_configured": bool(client_id),
        "valid_client_id": valid_client_id,
        "validation_reason": validation_reason,
        "client_secret_configured": bool(data.get("client_secret")),
        "project_id_configured": bool(data.get("project_id")),
        "client_type": str(data.get("client_type") or ""),
        "redirect_uri": str(data.get("redirect_uri") or DEFAULT_GOOGLE_REDIRECT_URI),
        "scopes": _normalize_scopes(data.get("scopes")),
        "updated_at": str(data.get("updated_at") or ""),
        "secrets_returned": False,
    }


def _pending_code_metadata() -> dict[str, Any]:
    path = google_oauth_pending_code_path()
    data = _load_json(path)
    code = str(data.get("code") or "")
    expires_at = str(data.get("expires_at") or "")
    expired = _iso_timestamp_expired(expires_at)
    available = bool(code and not expired)
    return {
        "available": available,
        "path": str(path),
        "received_at": str(data.get("received_at") or ""),
        "expires_at": expires_at,
        "expired": expired if code else False,
        "secrets_returned": False,
    }


def _last_exchange_metadata() -> dict[str, Any]:
    data = _load_json(google_oauth_last_exchange_path())
    if not data:
        return {"status": "never", "updated_at": "", "token_saved": False, "secrets_returned": False}
    return {
        "status": str(data.get("status") or "unknown"),
        "updated_at": str(data.get("updated_at") or ""),
        "token_saved": bool(data.get("token_saved")),
        "has_refresh_token": bool(data.get("has_refresh_token")),
        "using_pending_code": bool(data.get("using_pending_code")),
        "reason": redact_sensitive_text(str(data.get("reason") or ""), max_chars=1000),
        "secrets_returned": False,
    }


def _record_last_exchange(result: dict[str, Any]) -> None:
    payload = {
        "status": str(result.get("status") or "unknown"),
        "updated_at": _now(),
        "token_saved": bool(result.get("token_saved")),
        "has_refresh_token": bool(result.get("has_refresh_token")),
        "using_pending_code": bool(result.get("using_pending_code")),
        "reason": redact_sensitive_text(str(result.get("reason") or ""), max_chars=1000),
    }
    _write_secret_json(google_oauth_last_exchange_path(), payload)


def _pending_authorization_code() -> str:
    if not _pending_code_metadata().get("available"):
        return ""
    return _extract_authorization_code(_load_json(google_oauth_pending_code_path()).get("code"))


def _clear_pending_authorization_code() -> None:
    try:
        google_oauth_pending_code_path().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        _write_secret_json(google_oauth_pending_code_path(), {"cleared_at": _now()})


def _load_client_config() -> dict[str, Any]:
    return _load_json(google_oauth_client_path())


def _load_token_config() -> dict[str, Any]:
    return _load_json(default_google_token_path())


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_secret_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _resolve_client_config(
    *,
    client_id: str = "",
    client_secret: str = "",
    client_json: str = "",
    redirect_uri: str = "",
    scopes: list[str] | None = None,
    saved_client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    saved = saved_client or {}
    parsed = _parse_google_client_json(client_json) if str(client_json or "").strip() else {}
    if not parsed and str(client_id or "").strip().startswith("{"):
        parsed = _parse_google_client_json(client_id)
        client_id = ""
    if parsed.get("status") == "error":
        return {"status": "blocked", "reason": parsed["reason"], "fake_success": False, "secrets_returned": False}

    clean_client_id = str(client_id or parsed.get("client_id") or saved.get("client_id") or "").strip()
    clean_client_secret = str(client_secret or parsed.get("client_secret") or saved.get("client_secret") or "").strip()
    project_id = str(parsed.get("project_id") or saved.get("project_id") or "").strip()
    client_type = str(parsed.get("client_type") or saved.get("client_type") or ("manual" if clean_client_id else "")).strip()
    clean_redirect_uri = str(redirect_uri or saved.get("redirect_uri") or DEFAULT_GOOGLE_REDIRECT_URI).strip() or DEFAULT_GOOGLE_REDIRECT_URI
    clean_scopes = _clean_requested_scopes(scopes or saved.get("scopes") or DEFAULT_GOOGLE_SCOPES)

    if not clean_client_id or not clean_client_secret:
        return {"status": "blocked", "reason": "Google OAuth client_id and client_secret are required.", "fake_success": False, "secrets_returned": False}
    validation = _validate_google_client_id(clean_client_id)
    if validation:
        return {"status": "blocked", "reason": validation, "fake_success": False, "secrets_returned": False}

    warnings: list[str] = []
    if not project_id:
        warnings.append("No project_id was found. If Google shows invalid_client, paste the downloaded OAuth client JSON instead of typing credentials manually.")
    return {
        "status": "success",
        "client_id": clean_client_id,
        "client_secret": clean_client_secret,
        "project_id": project_id,
        "client_type": client_type or "manual",
        "redirect_uri": clean_redirect_uri,
        "scopes": clean_scopes,
        "warnings": warnings,
        "fake_success": False,
        "secrets_returned": False,
    }


def _parse_google_client_json(raw: Any) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"status": "error", "reason": "Google OAuth client JSON could not be parsed."}
    if not isinstance(data, dict):
        return {"status": "error", "reason": "Google OAuth client JSON must be an object."}
    if isinstance(data.get("installed"), dict):
        client = data["installed"]
        client_type = "installed"
    elif isinstance(data.get("web"), dict):
        client = data["web"]
        client_type = "web"
    else:
        client = data
        client_type = "manual_json"
    return {
        "status": "success",
        "client_id": str(client.get("client_id") or "").strip(),
        "client_secret": str(client.get("client_secret") or "").strip(),
        "project_id": str(client.get("project_id") or "").strip(),
        "client_type": client_type,
    }


def _validate_google_client_id(client_id: str) -> str:
    value = str(client_id or "").strip()
    if any(char in value for char in "{}\"' \n\r\t"):
        return "Google Client ID must be the OAuth Client ID only, ending in .apps.googleusercontent.com. Paste downloaded client JSON into the Client JSON field if needed."
    if not value.endswith(".apps.googleusercontent.com"):
        return "Google Client ID must end with .apps.googleusercontent.com. Do not use a project id, API key, or client secret as the Client ID."
    return ""


def _iso_timestamp_expired(raw: str) -> bool:
    value = str(raw or "").strip()
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= datetime.now(timezone.utc)
    except Exception:
        return False


def _clean_requested_scopes(scopes: list[str] | None) -> list[str]:
    requested = _normalize_scopes(scopes) if scopes else list(DEFAULT_GOOGLE_SCOPES)
    cleaned = [scope for scope in requested if scope.startswith("https://www.googleapis.com/auth/")]
    return cleaned or list(DEFAULT_GOOGLE_SCOPES)


def _normalize_scopes(raw: Any) -> list[str]:
    if isinstance(raw, str):
        candidates = raw.split()
    elif isinstance(raw, list):
        candidates = [str(item) for item in raw]
    else:
        candidates = []
    seen: set[str] = set()
    scopes: list[str] = []
    for item in candidates:
        clean = item.strip()
        if clean and clean not in seen:
            seen.add(clean)
            scopes.append(clean)
    return scopes


def _extract_authorization_code(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query or value.lstrip("?"))
    code_values = query.get("code") or []
    if code_values:
        return str(code_values[0] or "").strip()
    return value


def _safe_oauth_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
        return redact_sensitive_text(raw or str(exc), max_chars=2000)
    return redact_sensitive_text(str(exc), max_chars=2000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
