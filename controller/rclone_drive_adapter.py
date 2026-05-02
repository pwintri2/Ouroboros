"""Read-only rclone bridge for human-authenticated cloud drives.

Purpose:
    Let Ouroboros inspect Google Drive through an existing rclone login instead
    of capturing browser sessions or hand-managing Google OAuth tokens.
Inputs:
    Local rclone binary/config and exact Akkoord for live read calls.
Outputs:
    Sanitized rclone status, root/path listings and 11D records for Drive
    objects.
Safety notes:
    This adapter never reads or returns rclone tokens. It invokes rclone with an
    argument list, performs read-only listing commands and does not scrape
    browser cookies.
Akkoord requirements:
    Required for every live rclone listing.

Why this change:
    Philip asked for the "human login like other apps" route. rclone already
    provides that legitimate browser OAuth flow and token refresh layer.
"""

from __future__ import annotations

import configparser
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
DEFAULT_TIMEOUT_SECONDS = 90


def default_rclone_binary() -> str:
    configured = os.getenv("WINTRIP_RCLONE_BIN", "").strip()
    if configured:
        return configured
    found = shutil.which("rclone")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "rclone"
    return str(local) if local.exists() else "rclone"


def default_rclone_config() -> Path:
    configured = os.getenv("RCLONE_CONFIG", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".config" / "rclone" / "rclone.conf").resolve()


def rclone_drive_state_path() -> Path:
    return (workspace_root() / ".secrets" / "rclone_drive_adapter.json").resolve()


def get_rclone_drive_status() -> dict[str, Any]:
    return RcloneDriveAdapter().status()


class RcloneDriveAdapter:
    def __init__(self, binary: str | None = None, config_path: str | Path | None = None) -> None:
        self.binary = binary or default_rclone_binary()
        self.config_path = Path(config_path).expanduser().resolve() if config_path else default_rclone_config()

    def status(self) -> dict[str, Any]:
        remotes = self._drive_remotes()
        version = self._rclone_version()
        latest = self._load_state()
        binary_exists = shutil.which(self.binary) is not None or Path(self.binary).exists()
        if not (binary_exists and remotes):
            bridge = self._bridge_status()
            if bridge:
                bridge["via_bridge"] = True
                return bridge
        return {
            "status": "ready" if binary_exists and remotes else "unavailable",
            "adapter": "rclone_drive",
            "binary": self.binary,
            "binary_exists": binary_exists,
            "config_exists": self.config_path.exists(),
            "drive_remotes": remotes,
            "version": version,
            "last_listing": latest,
            "read_requires_approval": True,
            "tokens_returned": False,
            "fake_success": False,
        }

    def list_drive_files(
        self,
        *,
        approval: str = "",
        remote: str = "",
        path: str = "",
        max_items: int = 100,
        max_depth: int = 1,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord' for rclone Drive reads.", "fake_success": False}

        remotes = self._drive_remotes()
        binary_exists = shutil.which(self.binary) is not None or Path(self.binary).exists()
        if not (binary_exists and remotes):
            bridge = self._bridge_list(
                approval=approval,
                remote=remote,
                path=path,
                max_items=max_items,
                max_depth=max_depth,
            )
            if bridge:
                bridge["via_bridge"] = True
                return bridge
        if not remotes:
            return {"status": "error", "reason": "No rclone Google Drive remote configured.", "fake_success": False}
        remote_name = _normalize_remote(remote or remotes[0])
        if remote_name not in remotes:
            return {"status": "error", "reason": f"Unknown rclone Drive remote: {remote_name}", "available_remotes": remotes, "fake_success": False}

        target = f"{remote_name}:{_clean_remote_path(path)}"
        cmd = [
            self.binary,
            "lsjson",
            target,
            "--max-depth",
            str(max(1, min(int(max_depth), 5))),
            "--fast-list",
        ]
        try:
            proc = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=max(5, min(int(timeout_seconds), 300)),
                check=False,
            )
        except Exception as exc:
            return {"status": "error", "reason": redact_sensitive_text(str(exc)), "remote": remote_name, "fake_success": False}

        if proc.returncode != 0:
            return {
                "status": "error",
                "reason": redact_sensitive_text((proc.stderr or proc.stdout or "rclone listing failed").strip()),
                "remote": remote_name,
                "fake_success": False,
            }
        try:
            items = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as exc:
            return {"status": "error", "reason": f"Could not parse rclone JSON: {exc}", "remote": remote_name, "fake_success": False}
        if not isinstance(items, list):
            return {"status": "error", "reason": "rclone JSON was not a list.", "remote": remote_name, "fake_success": False}

        limit = max(1, min(int(max_items), 1000))
        clipped = [item for item in items[:limit] if isinstance(item, dict)]
        records = [_rclone_drive_record(remote_name, item) for item in clipped]
        state = {
            "remote": remote_name,
            "path": _clean_remote_path(path),
            "count": len(clipped),
            "total_seen": len(items),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_state(state)
        return {
            "status": "success",
            "source": "rclone",
            "operation": "list_drive_files",
            "remote": remote_name,
            "path": state["path"],
            "count": len(clipped),
            "total_seen": len(items),
            "items": clipped,
            "records_11d": records,
            "fake_success": False,
        }

    def _drive_remotes(self) -> list[str]:
        if not self.config_path.exists():
            return []
        parser = configparser.ConfigParser()
        parser.read(self.config_path)
        remotes: list[str] = []
        for section in parser.sections():
            if parser.get(section, "type", fallback="").strip() == "drive":
                remotes.append(section)
        return sorted(remotes)

    def _rclone_version(self) -> str:
        try:
            proc = subprocess.run(
                [self.binary, "version"],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return ""
        first_line = (proc.stdout or proc.stderr or "").splitlines()
        return first_line[0].strip() if first_line else ""

    def _load_state(self) -> dict[str, Any]:
        path = rclone_drive_state_path()
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def _bridge_status(self) -> dict[str, Any]:
        return _bridge_request("GET", "/status", {})

    def _bridge_list(self, *, approval: str, remote: str, path: str, max_items: int, max_depth: int) -> dict[str, Any]:
        return _bridge_request(
            "POST",
            "/drive/files",
            {
                "approval": approval,
                "remote": remote,
                "path": path,
                "max_items": max_items,
                "max_depth": max_depth,
            },
        )


def _normalize_remote(remote: str) -> str:
    return str(remote or "").strip().rstrip(":")


def _clean_remote_path(path: str) -> str:
    clean = str(path or "").strip().lstrip("/")
    if "\x00" in clean or clean.startswith("..") or "/../" in clean:
        return ""
    return clean


def _rclone_drive_record(remote: str, item: dict[str, Any]) -> dict[str, Any]:
    modified = str(item.get("ModTime") or "")
    is_dir = bool(item.get("IsDir"))
    size = int(item.get("Size") or 0) if not is_dir else 0
    return build_11d_record(
        source="rclone_drive_adapter",
        record_type="drive_folder" if is_dir else "drive_file",
        title=str(item.get("Name") or item.get("Path") or "drive_object"),
        summary=json.dumps(
            {
                "path": item.get("Path", ""),
                "name": item.get("Name", ""),
                "mime_type": item.get("MimeType", ""),
                "is_dir": is_dir,
                "size": size,
            },
            sort_keys=True,
        ),
        signals={
            "driver_or_api_health": 0.85,
            "network_pressure": 0.45,
            "identity_or_auth_state": 0.7,
            "permission_complexity": 0.45,
            "freshness": 0.85 if modified else 0.5,
            "importance": 0.65 if is_dir else 0.55,
            "safety_risk": 0.25,
        },
        metadata={"remote": remote, "path": item.get("Path", ""), "modified": modified, "is_dir": is_dir},
    )


def _save_state(state: dict[str, Any]) -> None:
    path = rclone_drive_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _bridge_request(method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").strip()
    if not base_url:
        return {}
    token = _bridge_token()
    if not token:
        return {}
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if method == "POST" else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ouroboros-Bridge-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _bridge_token() -> str:
    configured = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "rclone_bridge_token").resolve()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
