#!/usr/bin/env python3
"""Interactive OAuth token helper for Ouroboros cloud adapters.

Purpose:
    Turn pasted OAuth app material into real delegated access tokens without
    asking Philip to handcraft .env files.
Inputs:
    Existing `.secrets/google_workspace_token.json` and
    `.secrets/microsoft_graph_token.json` files may contain a client_id and
    client_secret, or the client_id may currently be parked in access_token by
    the forgiving token eater.
Outputs:
    Fresh adapter token JSON files with access_token, scopes and expiry
    metadata, chmod 0600.
Safety notes:
    Secrets and token values are never printed. Browser/device-code login is
    interactive and user initiated.
Akkoord requirements:
    This tool only reads and writes local token files. The later API calls still
    require the adapter approval phrase.

Why this change:
    Pasted client IDs and secrets are not live access tokens. This helper gets
    Ouroboros from "I have app credentials" to "I can read Drive/Graph".
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable


GOOGLE_TARGET = ".secrets/google_workspace_token.json"
MICROSOFT_TARGET = ".secrets/microsoft_graph_token.json"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_LOOPBACK_PORT = 8765
MICROSOFT_DEVICE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

GOOGLE_WORKSPACE_SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
GOOGLE_FULL_SCOPES = [
    *GOOGLE_WORKSPACE_SCOPES,
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/cloud-platform.read-only",
]
GOOGLE_SCOPE_PROFILES = {
    "workspace": GOOGLE_WORKSPACE_SCOPES,
    "full": GOOGLE_FULL_SCOPES,
}
GOOGLE_403_HELP = (
    "Google 403 betekent meestal dat de OAuth app jou nog niet mag toelaten. "
    "Zet in Google Cloud Console bij OAuth consent screen je account als Test user, "
    "controleer dat de app External is als je met een gewone Gmail inlogt, en voeg "
    "bij Authorized redirect URIs http://127.0.0.1:8765/callback toe als Google "
    "daarom vraagt. De knop Google login vraagt alleen Drive + Calendar; Google alles "
    "vraagt ook Gmail en GCP en wordt sneller geblokkeerd."
)
MICROSOFT_SCOPES = [
    "offline_access",
    "User.Read",
    "Files.Read",
    "Sites.Read.All",
    "Calendars.Read",
    "Team.ReadBasic.All",
]


def workspace_root() -> Path:
    return Path(os.getenv("WINTRIP_WORKSPACE") or Path(__file__).resolve().parents[1]).expanduser().resolve()


def google_token_path(workspace: str | Path | None = None) -> Path:
    return (Path(workspace).expanduser().resolve() if workspace else workspace_root()) / GOOGLE_TARGET


def microsoft_token_path(workspace: str | Path | None = None) -> Path:
    return (Path(workspace).expanduser().resolve() if workspace else workspace_root()) / MICROSOFT_TARGET


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def google_client_config(workspace: str | Path | None = None) -> dict[str, str]:
    data = load_json(google_token_path(workspace))
    client_id = str(data.get("client_id") or "").strip()
    client_secret = str(data.get("client_secret") or "").strip()
    parked = str(data.get("access_token") or data.get("token") or "").strip()
    if not client_id and _looks_like_google_client_id(parked):
        client_id = parked
    return {"client_id": client_id, "client_secret": client_secret}


def microsoft_client_config(workspace: str | Path | None = None) -> dict[str, str]:
    data = load_json(microsoft_token_path(workspace))
    client_id = str(data.get("client_id") or "").strip()
    tenant_id = str(data.get("tenant_id") or data.get("tid") or "common").strip() or "common"
    parked = str(data.get("access_token") or data.get("token") or "").strip()
    if not client_id and _looks_like_uuid(parked):
        client_id = parked
    return {"client_id": client_id, "tenant_id": tenant_id}


def run_google_loopback_oauth(
    *,
    workspace: str | Path | None = None,
    scope_profile: str = "workspace",
    timeout_seconds: int = 240,
    open_browser: bool = True,
    status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve() if workspace else workspace_root()
    config = google_client_config(root)
    if not config["client_id"] or not config["client_secret"]:
        return {
            "status": "error",
            "provider": "google",
            "reason": "google_client_id_or_secret_missing",
            "hint": "Plak Google --> client_id en Google secret --> client_secret, druk OK, probeer daarna Google login.",
            "secrets_returned": False,
        }

    port = _loopback_port(preferred=GOOGLE_LOOPBACK_PORT)
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    scopes = GOOGLE_SCOPE_PROFILES.get(scope_profile) or GOOGLE_WORKSPACE_SCOPES
    auth_url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "select_account consent",
            "include_granted_scopes": "true",
        }
    )

    if status:
        scope_label = "Drive + Calendar" if scope_profile != "full" else "Drive + Calendar + Gmail + GCP"
        status(f"Google login geopend ({scope_label}). Rond de toestemming daar af.")
    server = _OAuthCallbackServer(("127.0.0.1", port), _OAuthCallbackHandler)
    if open_browser:
        webbrowser.open(auth_url)

    deadline = time.time() + max(30, timeout_seconds)
    while time.time() < deadline and not server.oauth_result:
        server.handle_request()

    if not server.oauth_result:
        return {"status": "error", "provider": "google", "reason": "oauth_timeout_or_browser_blocked", "hint": GOOGLE_403_HELP, "secrets_returned": False}
    if server.oauth_result.get("error"):
        return {"status": "error", "provider": "google", "reason": server.oauth_result.get("error"), "hint": GOOGLE_403_HELP, "secrets_returned": False}

    code = str(server.oauth_result.get("code") or "")
    token = _post_form_json(
        GOOGLE_TOKEN_URL,
        {
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    normalized = _normalize_oauth_token(token, provider="google", client_id=config["client_id"], client_secret=config["client_secret"])
    _write_token(google_token_path(root), normalized)
    return _safe_success("google", normalized, google_token_path(root))


def run_microsoft_device_oauth(
    *,
    workspace: str | Path | None = None,
    timeout_seconds: int = 600,
    open_browser: bool = True,
    status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve() if workspace else workspace_root()
    config = microsoft_client_config(root)
    if not config["client_id"]:
        return {
            "status": "error",
            "provider": "microsoft",
            "reason": "microsoft_client_id_missing",
            "hint": "Plak Microsoft --> client_id, druk OK, probeer daarna Microsoft login.",
            "secrets_returned": False,
        }

    tenant = config["tenant_id"] or "common"
    device = _post_form_json(
        MICROSOFT_DEVICE_URL.format(tenant=urllib.parse.quote(tenant)),
        {"client_id": config["client_id"], "scope": " ".join(MICROSOFT_SCOPES)},
    )
    verification_uri = str(device.get("verification_uri") or device.get("verification_url") or "https://microsoft.com/devicelogin")
    user_code = str(device.get("user_code") or "")
    message = str(device.get("message") or f"Ga naar {verification_uri} en vul code {user_code} in.")
    if status:
        status(message)
    if open_browser:
        webbrowser.open(verification_uri)

    interval = int(device.get("interval") or 5)
    deadline = time.time() + min(max(60, int(device.get("expires_in") or timeout_seconds)), timeout_seconds)
    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": config["client_id"],
        "device_code": str(device.get("device_code") or ""),
    }
    while time.time() < deadline:
        time.sleep(max(1, interval))
        try:
            token = _post_form_json(MICROSOFT_TOKEN_URL.format(tenant=urllib.parse.quote(tenant)), payload)
        except urllib.error.HTTPError as exc:
            error = _safe_http_error_json(exc)
            code = str(error.get("error") or "")
            if code == "authorization_pending":
                continue
            if code == "slow_down":
                interval += 5
                continue
            return {"status": "error", "provider": "microsoft", "reason": code or "device_login_failed", "message": error.get("error_description", ""), "secrets_returned": False}
        normalized = _normalize_oauth_token(token, provider="microsoft", client_id=config["client_id"], tenant_id=tenant)
        _write_token(microsoft_token_path(root), normalized)
        return _safe_success("microsoft", normalized, microsoft_token_path(root))

    return {"status": "error", "provider": "microsoft", "reason": "device_login_timeout", "secrets_returned": False}


def _post_form_json(url: str, fields: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("oauth_response_not_object")
    return payload


def _safe_http_error_json(exc: urllib.error.HTTPError) -> dict[str, Any]:
    try:
        value = json.loads(exc.read().decode("utf-8"))
    except Exception:
        value = {"error": f"http_{exc.code}"}
    return value if isinstance(value, dict) else {"error": f"http_{exc.code}"}


def _normalize_oauth_token(
    token: dict[str, Any],
    *,
    provider: str,
    client_id: str,
    client_secret: str = "",
    tenant_id: str = "",
) -> dict[str, Any]:
    expires_in = int(token.get("expires_in") or 0)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in))).isoformat() if expires_in else ""
    scopes = token.get("scope") or token.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    normalized = dict(token)
    normalized["provider"] = provider
    normalized["client_id"] = client_id
    if client_secret:
        normalized["client_secret"] = client_secret
    if tenant_id:
        normalized["tenant_id"] = tenant_id
    normalized["scopes"] = list(scopes)
    normalized["expires_at"] = expires_at
    normalized["installed_by"] = "scripts/oauth_token_wizard.py"
    normalized["installed_at"] = datetime.now(timezone.utc).isoformat()
    if provider == "microsoft":
        payload = _jwt_payload(str(normalized.get("access_token") or ""))
        if payload:
            normalized.setdefault("tid", payload.get("tid", ""))
            normalized.setdefault("roles", payload.get("roles", []))
    return normalized


def _safe_success(provider: str, token: dict[str, Any], target: Path) -> dict[str, Any]:
    return {
        "status": "success",
        "provider": provider,
        "target": str(target),
        "scopes": list(token.get("scopes") or [])[:50],
        "expires_at": token.get("expires_at", ""),
        "secrets_returned": False,
    }


def _write_token(path: Path, token: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def _loopback_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    return _free_loopback_port()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _looks_like_google_client_id(value: str) -> bool:
    return value.endswith(".apps.googleusercontent.com")


def _looks_like_uuid(value: str) -> bool:
    return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", value.strip()))


def _jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        value = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


class _OAuthCallbackServer(HTTPServer):
    oauth_result: dict[str, str]

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(server_address, handler)
        self.timeout = 1
        self.oauth_result = {}


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        result = {key: values[0] for key, values in query.items() if values}
        self.server.oauth_result = result  # type: ignore[attr-defined]
        body = b"<html><body><h1>Ouroboros login klaar</h1><p>Je kunt dit venster sluiten.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return
