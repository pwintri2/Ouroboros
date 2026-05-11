"""Dedicated VPS deploy adapter for the Ouroboros web target.

Purpose:
    Provide a narrow, auditable VPS surface for status, SSH login checks,
    rsync dry-run previews and approval-gated rsync execution.
Inputs:
    Non-secret profile metadata from environment variables plus the host SSH
    agent/config/keychain. No passwords, private keys or tokens are read.
Outputs:
    Sanitized status and command results. Commands are built as argv lists and
    returned only as redacted previews.
Safety notes:
    The remote target is constrained to
    /var/www/philip-wintrip.nl/html/Ouroboros/ or a normalized child beneath it.
    Secrets and local state are excluded from rsync by default.
Akkoord requirements:
    sync_execute requires the exact approval phrase Akkoord. Status, login check
    and sync_preview are non-mutating and do not require approval.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
REMOTE_ROOT = "/var/www/philip-wintrip.nl/html/Ouroboros/"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10

DEFAULT_RSYNC_EXCLUDES: tuple[str, ...] = (
    ".git/",
    ".git/**",
    ".secrets/",
    ".secrets/**",
    ".env",
    ".env.*",
    ".env*",
    "**/.env",
    "**/.env.*",
    "**/.env*",
    "**/*token*",
    "**/*Token*",
    "**/*oauth*",
    "**/*OAuth*",
    "**/credentials.json",
    "**/client_secret*.json",
    "**/rclone.conf",
    ".ssh/",
    ".ssh/**",
    "**/.ssh/",
    "**/.ssh/**",
    ".gnupg/",
    ".gnupg/**",
    "**/.gnupg/",
    "**/.gnupg/**",
    "**/id_rsa*",
    "**/id_ed25519*",
    "**/*.pem",
    "**/*.key",
    "**/*.gpg",
    "**/*.asc",
    "**/Chrome/",
    "**/Chromium/",
    "**/Firefox/",
    "**/browser_profile*/",
    "**/playwright/.auth/",
    "wintrip_brain/",
    "wintrip_brain/**",
    "**/chroma/",
    "**/chroma/**",
    "**/chromadb/",
    "**/chromadb/**",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*.db",
    "__pycache__/",
    "**/__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".cache/",
    "**/.cache/",
    "node_modules/",
    "**/node_modules/",
    ".venv/",
    "venv/",
    "env/",
    "**/.venv/",
    "**/venv/",
    "dist/",
    "build/",
    "target/",
    "**/dist/",
    "**/build/",
    "**/target/",
    "unsloth_compiled_cache/",
    "litgpt/checkpoints/",
    "artifacts/model*/",
    "output/private/",
    "data/uploads/",
    "uploads/",
    "private/",
    "**/private/",
    "**/*.gguf",
    "**/*.safetensors",
    "**/*.pt",
    "**/*.pth",
    "**/*.ckpt",
    "**/*.onnx",
    "**/*.bin",
)

SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9_.-]{1,255}$")
SAFE_USER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SHELL_META_RE = re.compile(r"[;&|<>`\"'\n\r]")
REMOTE_SAFE_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
UNEXPANDED_VAR_RE = re.compile(r"(\$\{?[A-Za-z0-9_]+\}?|%[A-Za-z0-9_]+%|~)")
SENSITIVE_OUTPUT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"(?i)(identityfile\s+)[^\n\r]+"),
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class VPSProfile:
    profile_id: str = "philip-wintrip-ourobouros"
    ssh_host_alias: str = ""
    user: str = ""
    port: int | None = None
    remote_root: str = REMOTE_ROOT

    def remote_login(self) -> str:
        host = self.ssh_host_alias.strip()
        user = self.user.strip()
        return f"{user}@{host}" if user else host

    def sanitized(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "ssh_host_alias": self.ssh_host_alias,
            "user": self.user,
            "port": self.port,
            "remote_root": self.remote_root,
            "credentials_source": "host_ssh_agent_or_config_only",
            "credentials_returned": False,
            "secrets_returned": False,
        }


def get_vps_deploy_status() -> dict[str, Any]:
    return VPSDeployAdapter().status()


def profile_from_env() -> VPSProfile:
    return VPSProfile(
        profile_id=os.getenv("WINTRIP_VPS_PROFILE_ID", "philip-wintrip-ourobouros").strip() or "philip-wintrip-ourobouros",
        ssh_host_alias=(os.getenv("WINTRIP_VPS_SSH_ALIAS") or os.getenv("WINTRIP_VPS_HOST") or "").strip(),
        user=os.getenv("WINTRIP_VPS_USER", "").strip(),
        port=_optional_port(os.getenv("WINTRIP_VPS_PORT", "")),
        remote_root=REMOTE_ROOT,
    )


class VPSDeployAdapter:
    def __init__(
        self,
        *,
        profile: VPSProfile | None = None,
        workspace: str | Path | None = None,
        rsync_binary: str | None = None,
        ssh_binary: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.profile = profile or profile_from_env()
        self.workspace = Path(workspace).expanduser().resolve() if workspace else workspace_root().resolve()
        self.rsync_binary = rsync_binary or os.getenv("WINTRIP_RSYNC_BIN", "rsync").strip() or "rsync"
        self.ssh_binary = ssh_binary or os.getenv("WINTRIP_SSH_BIN", "ssh").strip() or "ssh"
        self.runner: Runner = runner or subprocess.run

    def status(self, *, prefer_bridge: bool = True) -> dict[str, Any]:
        direct = self._status_payload()
        if prefer_bridge and str(direct.get("status")) in {"unconfigured", "unavailable"}:
            bridge = _bridge_request("GET", "/vps/status", {})
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)
        return direct

    def login_check(self, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, prefer_bridge: bool = True) -> dict[str, Any]:
        readiness = self._direct_readiness(require_rsync=False)
        if prefer_bridge and not readiness["ready"]:
            bridge = _bridge_request("POST", "/vps/login-check", {"timeout_seconds": timeout_seconds})
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)
        if not readiness["ready"]:
            return self._blocked_no_configuration("login_check", readiness["reason"])

        cmd = self._ssh_login_check_args(timeout_seconds=timeout_seconds)
        try:
            proc = self.runner(
                cmd,
                text=True,
                capture_output=True,
                timeout=max(5, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 300)),
                check=False,
            )
        except Exception as exc:
            return self._command_error("login_check", cmd, str(exc))
        stdout = redact_sensitive_text(str(proc.stdout or ""))[-12000:]
        stderr = redact_sensitive_text(str(proc.stderr or ""))[-12000:]
        ok = int(proc.returncode or 0) == 0
        return {
            "status": "success" if ok else "error",
            "operation": "login_check",
            "profile": self.profile.sanitized(),
            "command_preview": redact_command(cmd),
            "exit_code": int(proc.returncode or 0),
            "stdout": stdout,
            "stderr": stderr,
            "login_ok": ok,
            "mutated": False,
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def sync_preview(
        self,
        *,
        remote_path: str = "",
        source_path: str = "",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        prefer_bridge: bool = True,
    ) -> dict[str, Any]:
        return self._sync(
            dry_run=True,
            approval="",
            remote_path=remote_path,
            source_path=source_path,
            timeout_seconds=timeout_seconds,
            prefer_bridge=prefer_bridge,
        )

    def sync_execute(
        self,
        *,
        approval: str = "",
        remote_path: str = "",
        source_path: str = "",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        prefer_bridge: bool = True,
    ) -> dict[str, Any]:
        return self._sync(
            dry_run=False,
            approval=approval,
            remote_path=remote_path,
            source_path=source_path,
            timeout_seconds=timeout_seconds,
            prefer_bridge=prefer_bridge,
        )

    def _sync(
        self,
        *,
        dry_run: bool,
        approval: str,
        remote_path: str,
        source_path: str,
        timeout_seconds: int,
        prefer_bridge: bool,
    ) -> dict[str, Any]:
        operation = "sync_preview" if dry_run else "sync_execute"
        if not dry_run and str(approval or "").strip() != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "operation": operation,
                "reason": "VPS sync execution requires exact Akkoord.",
                "approval_required": True,
                "approval_present": False,
                "dry_run": False,
                "executed": False,
                "mutated": False,
                "remote_target": REMOTE_ROOT,
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }

        target_result = _safe_target_or_error(remote_path)
        if "error" in target_result:
            return self._blocked_path(operation, target_result["error"])
        remote_target = str(target_result["target"])

        source_result = self._safe_source_or_error(source_path)
        if "error" in source_result:
            return self._blocked_path(operation, source_result["error"])
        source = source_result["path"]

        readiness = self._direct_readiness(require_rsync=True)
        if prefer_bridge and not readiness["ready"]:
            bridge = _bridge_request(
                "POST",
                "/vps/sync-preview" if dry_run else "/vps/sync-execute",
                {
                    "approval": approval,
                    "remote_path": remote_path,
                    "source_path": source_path,
                    "timeout_seconds": timeout_seconds,
                },
            )
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)
        if not readiness["ready"]:
            return self._blocked_no_configuration(operation, readiness["reason"], remote_target=remote_target)

        cmd = self._rsync_args(
            source=source,
            remote_target=remote_target,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
        )
        try:
            proc = self.runner(
                cmd,
                text=True,
                capture_output=True,
                timeout=max(10, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 900)),
                check=False,
            )
        except Exception as exc:
            return self._command_error(operation, cmd, str(exc), remote_target=remote_target, dry_run=dry_run)

        stdout = redact_sensitive_text(str(proc.stdout or ""))[-20000:]
        stderr = redact_sensitive_text(str(proc.stderr or ""))[-12000:]
        exit_code = int(proc.returncode or 0)
        ok = exit_code == 0
        return {
            "status": ("preview" if dry_run else "success") if ok else "error",
            "operation": operation,
            "profile": self.profile.sanitized(),
            "source_path": str(source),
            "remote_target": remote_target,
            "remote_target_fixed_root": REMOTE_ROOT,
            "dry_run": dry_run,
            "executed": bool(ok and not dry_run),
            "mutated": bool(ok and not dry_run),
            "approval_required": not dry_run,
            "approval_present": bool((not dry_run) and str(approval or "").strip() == APPROVAL_PHRASE),
            "rsync_exit_code": exit_code,
            "command_preview": redact_command(cmd),
            "stdout": stdout,
            "stderr": stderr,
            "excluded_patterns": list(DEFAULT_RSYNC_EXCLUDES),
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def _status_payload(self) -> dict[str, Any]:
        profile_error = self._profile_validation_error()
        rsync_exists = _binary_exists(self.rsync_binary)
        ssh_exists = _binary_exists(self.ssh_binary)
        if profile_error:
            status = "unconfigured"
            reason = profile_error
        elif not (ssh_exists and rsync_exists):
            status = "unavailable"
            reason = "ssh and rsync binaries must be available on the host bridge/runtime."
        else:
            status = "ready"
            reason = "VPS deploy profile metadata is configured; credentials remain in host SSH agent/config."
        return {
            "status": status,
            "adapter": "vps_deploy",
            "profile": self.profile.sanitized(),
            "workspace": str(self.workspace),
            "remote_target": REMOTE_ROOT,
            "remote_target_policy": "exact_root_or_normalized_child_only",
            "rsync_binary": self.rsync_binary,
            "rsync_available": rsync_exists,
            "ssh_binary": self.ssh_binary,
            "ssh_available": ssh_exists,
            "configured": profile_error == "",
            "reason": reason,
            "login_check_mutates": False,
            "preview_mutates": False,
            "execute_requires_approval": True,
            "default_excludes": list(DEFAULT_RSYNC_EXCLUDES),
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def _direct_readiness(self, *, require_rsync: bool) -> dict[str, Any]:
        profile_error = self._profile_validation_error()
        if profile_error:
            return {"ready": False, "reason": profile_error}
        if not _binary_exists(self.ssh_binary):
            return {"ready": False, "reason": "ssh binary is not available."}
        if require_rsync and not _binary_exists(self.rsync_binary):
            return {"ready": False, "reason": "rsync binary is not available."}
        return {"ready": True, "reason": "ready"}

    def _profile_validation_error(self) -> str:
        host = str(self.profile.ssh_host_alias or "").strip()
        user = str(self.profile.user or "").strip()
        if not host:
            return "No VPS SSH host alias configured; set WINTRIP_VPS_SSH_ALIAS or WINTRIP_VPS_HOST on the host."
        if not SAFE_HOST_RE.fullmatch(host) or host.startswith("-") or "@" in host:
            return "Unsafe VPS SSH host alias metadata."
        if user and (not SAFE_USER_RE.fullmatch(user) or user.startswith("-")):
            return "Unsafe VPS SSH user metadata."
        if self.profile.port is not None and not (1 <= int(self.profile.port) <= 65535):
            return "Unsafe VPS SSH port metadata."
        if self.profile.remote_root != REMOTE_ROOT:
            return "Remote root is fixed and cannot be overridden."
        return ""

    def _ssh_login_check_args(self, *, timeout_seconds: int) -> list[str]:
        connect_timeout = max(3, min(int(timeout_seconds or DEFAULT_CONNECT_TIMEOUT_SECONDS), 30))
        args = [
            self.ssh_binary,
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            f"ConnectTimeout={connect_timeout}",
        ]
        if self.profile.port:
            args.extend(["-p", str(int(self.profile.port))])
        args.extend([self.profile.remote_login(), "printf", "ouroboros-vps-ok"])
        return args

    def _rsync_args(self, *, source: Path, remote_target: str, dry_run: bool, timeout_seconds: int) -> list[str]:
        rsync_timeout = max(10, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 900))
        source_arg = str(source) + ("/" if source.is_dir() else "")
        remote_arg = f"{self.profile.remote_login()}:{remote_target}"
        ssh_parts = [
            self.ssh_binary,
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            f"ConnectTimeout={min(rsync_timeout, 30)}",
        ]
        if self.profile.port:
            ssh_parts.extend(["-p", str(int(self.profile.port))])
        args = [
            self.rsync_binary,
            "--archive",
            "--compress",
            "--itemize-changes",
            "--human-readable",
            "--safe-links",
            "--protect-args",
            "--timeout",
            str(rsync_timeout),
            "-e",
            " ".join(shlex.quote(part) for part in ssh_parts),
        ]
        if dry_run:
            args.append("--dry-run")
        for pattern in DEFAULT_RSYNC_EXCLUDES:
            args.extend(["--exclude", pattern])
        args.extend([source_arg, remote_arg])
        return args

    def _safe_source_or_error(self, source_path: str) -> dict[str, Any]:
        text = str(source_path or "").strip()
        if text and ("\x00" in text or SHELL_META_RE.search(text) or UNEXPANDED_VAR_RE.search(text)):
            return {"error": "Unsafe source path metadata."}
        root = self.workspace.resolve()
        candidate = (root / text).resolve() if text and not text.startswith("/") else (Path(text).expanduser().resolve() if text else root)
        try:
            candidate.relative_to(root)
        except ValueError:
            return {"error": "Source path must stay inside the WintripAI workspace."}
        if not candidate.exists():
            return {"error": "Source path does not exist inside the WintripAI workspace."}
        return {"path": candidate}

    def _blocked_no_configuration(self, operation: str, reason: str, *, remote_target: str = REMOTE_ROOT) -> dict[str, Any]:
        return {
            "status": "blocked",
            "operation": operation,
            "reason": reason,
            "configured": False,
            "remote_target": remote_target,
            "executed": False,
            "mutated": False,
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def _blocked_path(self, operation: str, reason: str) -> dict[str, Any]:
        return {
            "status": "blocked",
            "operation": operation,
            "reason": reason,
            "remote_target": REMOTE_ROOT,
            "executed": False,
            "mutated": False,
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def _command_error(
        self,
        operation: str,
        cmd: list[str],
        reason: str,
        *,
        remote_target: str = REMOTE_ROOT,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "operation": operation,
            "reason": redact_sensitive_text(reason),
            "remote_target": remote_target,
            "dry_run": dry_run,
            "executed": False,
            "mutated": False,
            "command_preview": redact_command(cmd),
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }


def normalize_remote_target(path: str = "") -> str:
    raw = str(path or "").strip()
    if not raw:
        return REMOTE_ROOT
    if raw in {".", "./"}:
        raise ValueError("Remote target path is ambiguous; use blank for the fixed root or a child path.")
    if "\x00" in raw or "\\" in raw or SHELL_META_RE.search(raw) or UNEXPANDED_VAR_RE.search(raw):
        raise ValueError("Remote target path contains unsafe shell metacharacters or unexpanded variables.")
    if re.search(r"\s", raw) or not REMOTE_SAFE_RE.fullmatch(raw):
        raise ValueError("Remote target path contains ambiguous or unsafe characters.")
    segments = [segment for segment in raw.split("/") if segment]
    if any(segment in {"..", "."} for segment in segments):
        raise ValueError("Remote target path must not contain parent traversal or dot segments.")

    root = REMOTE_ROOT.rstrip("/")
    if raw.startswith("/"):
        normalized = posixpath.normpath(raw)
    else:
        normalized = posixpath.normpath(posixpath.join(root, raw.lstrip("/")))
    if normalized != root and not normalized.startswith(root + "/"):
        raise ValueError("Remote target must stay under /var/www/philip-wintrip.nl/html/Ouroboros/.")
    return normalized.rstrip("/") + "/"


def redact_sensitive_text(text: str) -> str:
    redacted = str(text or "")
    for pattern in SENSITIVE_OUTPUT_PATTERNS:
        def repl(match: re.Match[str]) -> str:
            if match.groups() and len(match.groups()) >= 1:
                return f"{match.group(1)}[REDACTED]"
            return "[REDACTED]"

        redacted = pattern.sub(repl, redacted)
    return redacted


def redact_command(args: list[str]) -> str:
    safe: list[str] = []
    for arg in args:
        text = redact_sensitive_text(str(arg))
        safe.append(shlex.quote(text))
    return " ".join(safe)[:4000]


def _safe_target_or_error(remote_path: str) -> dict[str, str]:
    try:
        return {"target": normalize_remote_target(remote_path)}
    except ValueError as exc:
        return {"error": str(exc)}


def _optional_port(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        port = int(text)
    except ValueError:
        return None
    return port if 1 <= port <= 65535 else None


def _binary_exists(binary: str) -> bool:
    value = str(binary or "").strip()
    if not value:
        return False
    return shutil.which(value) is not None or Path(value).exists()


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"password", "passwd", "secret", "token", "access_token", "refresh_token", "private_key", "ssh_key", "authorization", "bearer"}:
                output[str(key)] = "[REDACTED]" if item not in (None, "", False) else item
            else:
                output[str(key)] = _sanitize_payload(item)
        return output
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


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
