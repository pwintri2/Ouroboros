"""Dedicated VPS deploy adapter for the Ouroboros web target.

Purpose:
    Provide a narrow, auditable VPS surface for status, SSH login checks,
    rsync dry-run previews and approval-gated rsync execution.
Inputs:
    Non-secret profile metadata from environment variables or
    `.secrets/vps.env`, plus the host SSH agent/config/keychain. No passwords,
    private keys or tokens are read.
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
UI_DIST_RELATIVE_PATH = "ouroboros_cockpit/dist"
UI_PACKAGE_RELATIVE_PATH = "ouroboros_cockpit"
UI_ENTRYPOINT_ALIASES: tuple[str, ...] = ("Cockpit.html",)
DEFAULT_VPS_UI_PUBLIC_BASE = "/Ouroboros/"
DEFAULT_VPS_UI_BACKEND_URL = "/Ouroboros"
VPS_ENV_KEYS: tuple[str, ...] = (
    "WINTRIP_VPS_PROFILE_ID",
    "WINTRIP_VPS_SSH_ALIAS",
    "WINTRIP_VPS_HOST",
    "WINTRIP_VPS_USER",
    "WINTRIP_VPS_PORT",
    "WINTRIP_SSH_BIN",
    "WINTRIP_RSYNC_BIN",
    "WINTRIP_SCP_BIN",
    "WINTRIP_NPM_BIN",
    "WINTRIP_VPS_REMOTE_WORKSPACE",
    "WINTRIP_VPS_REMOTE_CHROMA_PATH",
    "WINTRIP_VPS_REMOTE_CHROMA_HTTP_URL",
    "WINTRIP_CHROMA_SYNC_COLLECTIONS",
    "WINTRIP_VPS_UI_PUBLIC_BASE",
    "WINTRIP_VPS_UI_BACKEND_URL",
)

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
    ".roo/",
    ".roo/**",
    "out/",
    "out/**",
    "logs/",
    "logs/**",
    "*.log",
    "**/*.log",
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

UI_RSYNC_EXCLUDES: tuple[str, ...] = (
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
    "**/*.map",
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
    _load_vps_env_file()
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
        scp_binary: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.profile = profile or profile_from_env()
        self.workspace = Path(workspace).expanduser().resolve() if workspace else workspace_root().resolve()
        self.rsync_binary = rsync_binary or os.getenv("WINTRIP_RSYNC_BIN", "rsync").strip() or "rsync"
        self.ssh_binary = ssh_binary or os.getenv("WINTRIP_SSH_BIN", "ssh").strip() or "ssh"
        self.scp_binary = scp_binary or os.getenv("WINTRIP_SCP_BIN", "scp").strip() or "scp"
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

    def ui_sync_preview(
        self,
        *,
        remote_path: str = "",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        prefer_bridge: bool = True,
    ) -> dict[str, Any]:
        return self._ui_sync(
            dry_run=True,
            approval="",
            remote_path=remote_path,
            timeout_seconds=timeout_seconds,
            prefer_bridge=prefer_bridge,
            build_first=False,
        )

    def ui_sync_execute(
        self,
        *,
        approval: str = "",
        remote_path: str = "",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        prefer_bridge: bool = True,
        build_first: bool = True,
    ) -> dict[str, Any]:
        return self._ui_sync(
            dry_run=False,
            approval=approval,
            remote_path=remote_path,
            timeout_seconds=timeout_seconds,
            prefer_bridge=prefer_bridge,
            build_first=build_first,
        )

    def _ui_sync(
        self,
        *,
        dry_run: bool,
        approval: str,
        remote_path: str,
        timeout_seconds: int,
        prefer_bridge: bool,
        build_first: bool,
    ) -> dict[str, Any]:
        operation = "ui_sync_preview" if dry_run else "ui_sync_execute"
        if not dry_run and str(approval or "").strip() != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "operation": operation,
                "reason": "VPS UI sync execution requires exact Akkoord.",
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

        if prefer_bridge:
            bridge = _bridge_request(
                "POST",
                "/vps/ui-sync-preview" if dry_run else "/vps/ui-sync-execute",
                {
                    "approval": approval,
                    "remote_path": remote_path,
                    "timeout_seconds": timeout_seconds,
                    "build_first": build_first,
                },
            )
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)

        dist_status = self._ui_dist_status()
        build_result: dict[str, Any] | None = None
        if not dry_run and build_first:
            build_result = self._build_ui(timeout_seconds=timeout_seconds)
            dist_status = self._ui_dist_status()
            if build_result.get("status") != "success":
                return {
                    "status": "error",
                    "operation": operation,
                    "reason": "UI build failed before VPS sync.",
                    "build": build_result,
                    "ui_dist": dist_status,
                    "executed": False,
                    "mutated": False,
                    "remote_target": REMOTE_ROOT,
                    "tokens_returned": False,
                    "secrets_returned": False,
                    "fake_success": False,
                }

        if not dist_status.get("ready"):
            return {
                "status": "blocked",
                "operation": operation,
                "reason": str(dist_status.get("reason") or "UI dist is not ready."),
                "ui_dist": dist_status,
                "executed": False,
                "mutated": False,
                "remote_target": REMOTE_ROOT,
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }
        if not dry_run and not dist_status.get("vps_ready"):
            return {
                "status": "blocked",
                "operation": operation,
                "reason": str(dist_status.get("vps_ready_reason") or "UI dist is not ready for the VPS public route."),
                "ui_dist": dist_status,
                "build": build_result,
                "executed": False,
                "mutated": False,
                "remote_target": REMOTE_ROOT,
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }

        if _binary_exists(self.rsync_binary):
            result = self._sync(
                dry_run=dry_run,
                approval=approval,
                remote_path=remote_path,
                source_path=UI_DIST_RELATIVE_PATH,
                timeout_seconds=timeout_seconds,
                prefer_bridge=False,
                operation=operation,
                rsync_excludes=UI_RSYNC_EXCLUDES,
            )
        else:
            result = self._ui_scp_sync(
                dry_run=dry_run,
                operation=operation,
                remote_path=remote_path,
                timeout_seconds=timeout_seconds,
            )
        if (
            prefer_bridge
            and result.get("status") == "blocked"
            and "ssh binary is not available" in str(result.get("reason") or "").lower()
            and os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").strip()
        ):
            result["bridge_unavailable"] = True
            result["reason"] = (
                "Host bridge did not handle /vps/ui-sync-preview, and the backend runtime has no ssh binary. "
                "Restart the Ouroboros preview so the new host bridge endpoints are active."
            )
            result["setup_hint"] = "Run: cd /home/pwintri2/WintripAI && WINTRIP_FORCE_BACKEND_REFRESH=1 ./scripts/start_ouroboros_preview.sh"
        result["ui_dist"] = dist_status
        result["ui_artifact_source"] = UI_DIST_RELATIVE_PATH
        result["build_first"] = bool(build_first and not dry_run)
        if build_result:
            result["build"] = build_result
        return result

    def _sync(
        self,
        *,
        dry_run: bool,
        approval: str,
        remote_path: str,
        source_path: str,
        timeout_seconds: int,
        prefer_bridge: bool,
        operation: str | None = None,
        rsync_excludes: tuple[str, ...] = DEFAULT_RSYNC_EXCLUDES,
    ) -> dict[str, Any]:
        operation = operation or ("sync_preview" if dry_run else "sync_execute")
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
            excludes=rsync_excludes,
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
            "excluded_patterns": list(rsync_excludes),
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def _status_payload(self) -> dict[str, Any]:
        profile_error = self._profile_validation_error()
        rsync_exists = _binary_exists(self.rsync_binary)
        ssh_exists = _binary_exists(self.ssh_binary)
        scp_exists = _binary_exists(self.scp_binary)
        if profile_error:
            status = "unconfigured"
            reason = profile_error
        elif ssh_exists and not rsync_exists and scp_exists:
            status = "degraded"
            reason = "rsync is unavailable, so broad workspace sync is blocked; UI artifact sync can use the scp fallback."
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
            "scp_binary": self.scp_binary,
            "scp_available": scp_exists,
            "configured": profile_error == "",
            "reason": reason,
            "env_file": _vps_env_file_status(),
            "configuration_keys": list(VPS_ENV_KEYS),
            "setup_hint": "Copy config/vps.env.example to .secrets/vps.env and keep SSH keys in ~/.ssh/config or ssh-agent.",
            "login_check_mutates": False,
            "preview_mutates": False,
            "execute_requires_approval": True,
            "default_excludes": list(DEFAULT_RSYNC_EXCLUDES),
            "ui_sync": {
                "artifact_source": UI_DIST_RELATIVE_PATH,
                "entrypoint_aliases": list(UI_ENTRYPOINT_ALIASES),
                "package_path": UI_PACKAGE_RELATIVE_PATH,
                "public_base": _vps_ui_public_base(),
                "backend_url": _vps_ui_backend_url(),
                "scp_fallback_available": scp_exists,
                "dist": self._ui_dist_status(),
                "excluded_patterns": list(UI_RSYNC_EXCLUDES),
                "execute_builds_first": True,
            },
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

    def _rsync_args(
        self,
        *,
        source: Path,
        remote_target: str,
        dry_run: bool,
        timeout_seconds: int,
        excludes: tuple[str, ...] = DEFAULT_RSYNC_EXCLUDES,
    ) -> list[str]:
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
        for pattern in excludes:
            args.extend(["--exclude", pattern])
        args.extend([source_arg, remote_arg])
        return args

    def _build_ui(self, *, timeout_seconds: int) -> dict[str, Any]:
        cockpit_dir = (self.workspace / UI_PACKAGE_RELATIVE_PATH).resolve()
        if not cockpit_dir.exists():
            return {
                "status": "error",
                "operation": "ui_build",
                "reason": f"{UI_PACKAGE_RELATIVE_PATH} does not exist inside the workspace.",
                "mutated": False,
                "fake_success": False,
            }
        npm_binary = os.getenv("WINTRIP_NPM_BIN", "npm").strip() or "npm"
        if not _binary_exists(npm_binary):
            return {
                "status": "error",
                "operation": "ui_build",
                "reason": "npm binary is not available on the host bridge/runtime.",
                "npm_binary": npm_binary,
                "mutated": False,
                "fake_success": False,
            }
        cmd = [npm_binary, "--prefix", str(cockpit_dir), "run", "build"]
        env = os.environ.copy()
        env["VITE_PUBLIC_BASE"] = _vps_ui_public_base()
        env["VITE_BACKEND_URL"] = _vps_ui_backend_url()
        env["TAURI_BACKEND_URL"] = _vps_ui_backend_url()
        try:
            proc = self.runner(
                cmd,
                text=True,
                capture_output=True,
                env=env,
                timeout=max(30, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 900)),
                check=False,
            )
        except Exception as exc:
            return self._command_error("ui_build", cmd, str(exc), remote_target="", dry_run=False)
        stdout = redact_sensitive_text(str(proc.stdout or ""))[-12000:]
        stderr = redact_sensitive_text(str(proc.stderr or ""))[-12000:]
        ok = int(proc.returncode or 0) == 0
        alias_result: dict[str, Any] | None = None
        if ok:
            alias_result = self._refresh_ui_entrypoint_aliases()
            ok = bool(alias_result.get("status") == "success")
        return {
            "status": "success" if ok else "error",
            "operation": "ui_build",
            "reason": "" if ok else str((alias_result or {}).get("reason") or "UI build failed."),
            "command_preview": redact_command(cmd),
            "build_env": {
                "VITE_PUBLIC_BASE": env["VITE_PUBLIC_BASE"],
                "VITE_BACKEND_URL": env["VITE_BACKEND_URL"],
                "TAURI_BACKEND_URL": env["TAURI_BACKEND_URL"],
            },
            "entrypoint_aliases": alias_result or {"status": "skipped", "aliases": list(UI_ENTRYPOINT_ALIASES)},
            "exit_code": int(proc.returncode or 0),
            "stdout": stdout,
            "stderr": stderr,
            "mutated": ok,
            "fake_success": False,
        }

    def _refresh_ui_entrypoint_aliases(self) -> dict[str, Any]:
        dist = (self.workspace / UI_DIST_RELATIVE_PATH).resolve()
        index = dist / "index.html"
        try:
            dist.relative_to(self.workspace)
        except ValueError:
            return {
                "status": "error",
                "reason": "UI dist path must stay inside the workspace.",
                "aliases": list(UI_ENTRYPOINT_ALIASES),
            }
        if not index.exists():
            return {
                "status": "error",
                "reason": "UI dist is missing index.html; cannot refresh Cockpit aliases.",
                "aliases": list(UI_ENTRYPOINT_ALIASES),
            }
        written: list[str] = []
        for alias in UI_ENTRYPOINT_ALIASES:
            alias_path = dist / alias
            try:
                alias_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(index, alias_path)
                written.append(alias)
            except OSError as exc:
                return {
                    "status": "error",
                    "reason": f"Failed to refresh UI entrypoint alias {alias}: {exc}",
                    "aliases": list(UI_ENTRYPOINT_ALIASES),
                    "written": written,
                }
        return {
            "status": "success",
            "aliases": list(UI_ENTRYPOINT_ALIASES),
            "written": written,
        }

    def _ui_scp_sync(
        self,
        *,
        dry_run: bool,
        operation: str,
        remote_path: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        target_result = _safe_target_or_error(remote_path)
        if "error" in target_result:
            return self._blocked_path(operation, target_result["error"])
        remote_target = str(target_result["target"])

        source_result = self._safe_source_or_error(UI_DIST_RELATIVE_PATH)
        if "error" in source_result:
            return self._blocked_path(operation, source_result["error"])
        source = source_result["path"]

        readiness = self._ui_scp_readiness()
        files = _ui_upload_files(source)
        manifest = _ui_upload_manifest(source, files)
        if not readiness["ready"]:
            return self._blocked_no_configuration(operation, readiness["reason"], remote_target=remote_target) | {
                "dry_run": dry_run,
                "transfer_method": "scp",
                "files_considered": manifest,
            }
        if not files:
            return self._blocked_path(operation, "UI dist contains no uploadable files.")

        if dry_run:
            return {
                "status": "preview",
                "operation": operation,
                "profile": self.profile.sanitized(),
                "source_path": str(source),
                "remote_target": remote_target,
                "remote_target_fixed_root": REMOTE_ROOT,
                "dry_run": True,
                "executed": False,
                "mutated": False,
                "approval_required": False,
                "approval_present": False,
                "transfer_method": "scp_manifest",
                "rsync_available": False,
                "files_would_send": manifest,
                "excluded_patterns": list(UI_RSYNC_EXCLUDES),
                "note": "rsync is not available; preview lists the files the scp fallback would upload.",
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }

        mkdir_cmd = self._ssh_mkdir_args(remote_target=remote_target, files=files, timeout_seconds=timeout_seconds)
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        command_previews = [redact_command(mkdir_cmd)]
        try:
            mkdir_proc = self.runner(
                mkdir_cmd,
                text=True,
                capture_output=True,
                timeout=max(10, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 300)),
                check=False,
            )
        except Exception as exc:
            return self._command_error(operation, mkdir_cmd, str(exc), remote_target=remote_target, dry_run=False)
        stdout_parts.append(str(mkdir_proc.stdout or ""))
        stderr_parts.append(str(mkdir_proc.stderr or ""))
        if int(mkdir_proc.returncode or 0) != 0:
            return {
                "status": "error",
                "operation": operation,
                "reason": "Failed to create remote UI directories before scp upload.",
                "remote_target": remote_target,
                "dry_run": False,
                "executed": False,
                "mutated": False,
                "transfer_method": "scp",
                "exit_code": int(mkdir_proc.returncode or 0),
                "command_preview": command_previews[0],
                "stdout": redact_sensitive_text("\n".join(stdout_parts))[-12000:],
                "stderr": redact_sensitive_text("\n".join(stderr_parts))[-12000:],
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }

        uploaded: list[dict[str, Any]] = []
        for file_path in files:
            rel = file_path.relative_to(source).as_posix()
            cmd = self._scp_file_args(
                local_file=file_path,
                remote_file=posixpath.join(remote_target.rstrip("/"), rel),
                timeout_seconds=timeout_seconds,
            )
            command_previews.append(redact_command(cmd))
            try:
                proc = self.runner(
                    cmd,
                    text=True,
                    capture_output=True,
                    timeout=max(10, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 300)),
                    check=False,
                )
            except Exception as exc:
                return self._command_error(operation, cmd, str(exc), remote_target=remote_target, dry_run=False)
            stdout_parts.append(str(proc.stdout or ""))
            stderr_parts.append(str(proc.stderr or ""))
            if int(proc.returncode or 0) != 0:
                return {
                    "status": "error",
                    "operation": operation,
                    "reason": f"scp upload failed for {rel}.",
                    "remote_target": remote_target,
                    "dry_run": False,
                    "executed": False,
                    "mutated": bool(uploaded),
                    "transfer_method": "scp",
                    "exit_code": int(proc.returncode or 0),
                    "uploaded": uploaded,
                    "failed_file": rel,
                    "command_preview": redact_command(cmd),
                    "stdout": redact_sensitive_text("\n".join(stdout_parts))[-12000:],
                    "stderr": redact_sensitive_text("\n".join(stderr_parts))[-12000:],
                    "tokens_returned": False,
                    "secrets_returned": False,
                    "fake_success": False,
                }
            uploaded.append(_file_manifest_entry(source, file_path))

        return {
            "status": "success",
            "operation": operation,
            "profile": self.profile.sanitized(),
            "source_path": str(source),
            "remote_target": remote_target,
            "remote_target_fixed_root": REMOTE_ROOT,
            "dry_run": False,
            "executed": True,
            "mutated": True,
            "approval_required": True,
            "approval_present": True,
            "transfer_method": "scp",
            "rsync_available": False,
            "uploaded": uploaded,
            "files_uploaded": len(uploaded),
            "command_preview": "\n".join(command_previews[:3])[:4000],
            "stdout": redact_sensitive_text("\n".join(stdout_parts))[-12000:],
            "stderr": redact_sensitive_text("\n".join(stderr_parts))[-12000:],
            "excluded_patterns": list(UI_RSYNC_EXCLUDES),
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    def _ui_scp_readiness(self) -> dict[str, Any]:
        profile_error = self._profile_validation_error()
        if profile_error:
            return {"ready": False, "reason": profile_error}
        if not _binary_exists(self.ssh_binary):
            return {"ready": False, "reason": "ssh binary is not available."}
        if not _binary_exists(self.scp_binary):
            return {"ready": False, "reason": "scp binary is not available and rsync is not available."}
        return {"ready": True, "reason": "ready"}

    def _ssh_mkdir_args(self, *, remote_target: str, files: list[Path], timeout_seconds: int) -> list[str]:
        connect_timeout = max(3, min(int(timeout_seconds or DEFAULT_CONNECT_TIMEOUT_SECONDS), 30))
        source = (self.workspace / UI_DIST_RELATIVE_PATH).resolve()
        dirs = {remote_target.rstrip("/")}
        for file_path in files:
            rel_dir = file_path.relative_to(source).parent.as_posix()
            if rel_dir and rel_dir != ".":
                dirs.add(posixpath.join(remote_target.rstrip("/"), rel_dir))
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
        args.extend([self.profile.remote_login(), "mkdir", "-p", "--", *sorted(dirs)])
        return args

    def _scp_file_args(self, *, local_file: Path, remote_file: str, timeout_seconds: int) -> list[str]:
        connect_timeout = max(3, min(int(timeout_seconds or DEFAULT_CONNECT_TIMEOUT_SECONDS), 30))
        args = [
            self.scp_binary,
            "-p",
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            f"ConnectTimeout={connect_timeout}",
        ]
        if self.profile.port:
            args.extend(["-P", str(int(self.profile.port))])
        args.extend([str(local_file), f"{self.profile.remote_login()}:{remote_file}"])
        return args

    def _ui_dist_status(self) -> dict[str, Any]:
        dist = (self.workspace / UI_DIST_RELATIVE_PATH).resolve()
        package = (self.workspace / UI_PACKAGE_RELATIVE_PATH).resolve()
        index = dist / "index.html"
        try:
            dist.relative_to(self.workspace)
            package.relative_to(self.workspace)
        except ValueError:
            return {"ready": False, "path": str(dist), "reason": "UI paths must stay inside the workspace."}
        if not dist.exists():
            return {"ready": False, "path": str(dist), "reason": "UI dist directory does not exist; run the UI build first."}
        if not index.exists():
            return {"ready": False, "path": str(dist), "reason": "UI dist is missing index.html; run the UI build first."}
        source_mtime = _newest_mtime(package, exclude_parts={"dist", "node_modules", "target"})
        dist_mtime = _newest_mtime(dist, exclude_parts=set())
        stale = bool(source_mtime and dist_mtime and source_mtime > dist_mtime)
        expected_public_base = _vps_ui_public_base()
        index_text = ""
        try:
            index_text = index.read_text(encoding="utf-8", errors="replace")
        except OSError:
            index_text = ""
        index_has_expected_public_base = bool(expected_public_base in index_text)
        aliases: dict[str, dict[str, Any]] = {}
        all_aliases_match = True
        for alias in UI_ENTRYPOINT_ALIASES:
            alias_path = dist / alias
            exists = alias_path.exists()
            matches_index = False
            if exists:
                try:
                    matches_index = alias_path.read_bytes() == index.read_bytes()
                except OSError:
                    matches_index = False
            all_aliases_match = all_aliases_match and exists and matches_index
            aliases[alias] = {
                "path": str(alias_path),
                "exists": exists,
                "matches_index": matches_index,
            }
        vps_ready = bool(index_has_expected_public_base and all_aliases_match)
        vps_ready_reason = "UI dist is ready for the VPS public route."
        if not index_has_expected_public_base:
            vps_ready_reason = f"UI dist index.html is not built for {expected_public_base}; UI Execute rebuilds it before syncing."
        elif not all_aliases_match:
            vps_ready_reason = "UI dist is missing a fresh Cockpit.html alias; UI Execute refreshes it before syncing."
        return {
            "ready": True,
            "path": str(dist),
            "index_html": str(index),
            "stale": stale,
            "source_newer_than_dist": stale,
            "source_newest_mtime": source_mtime,
            "dist_newest_mtime": dist_mtime,
            "expected_public_base": expected_public_base,
            "expected_backend_url": _vps_ui_backend_url(),
            "index_has_expected_public_base": index_has_expected_public_base,
            "entrypoint_aliases": aliases,
            "vps_ready": vps_ready,
            "vps_ready_reason": vps_ready_reason,
            "reason": "UI dist exists; execute sync rebuilds it first." if stale else "UI dist exists.",
        }

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


def _vps_ui_public_base() -> str:
    value = str(os.getenv("WINTRIP_VPS_UI_PUBLIC_BASE") or DEFAULT_VPS_UI_PUBLIC_BASE).strip() or DEFAULT_VPS_UI_PUBLIC_BASE
    if "\x00" in value or "\\" in value or SHELL_META_RE.search(value):
        return DEFAULT_VPS_UI_PUBLIC_BASE
    if not value.startswith("/"):
        value = "/" + value
    if not value.endswith("/"):
        value += "/"
    return value


def _vps_ui_backend_url() -> str:
    value = str(os.getenv("WINTRIP_VPS_UI_BACKEND_URL") or DEFAULT_VPS_UI_BACKEND_URL).strip() or DEFAULT_VPS_UI_BACKEND_URL
    if "\x00" in value or "\\" in value or SHELL_META_RE.search(value):
        return DEFAULT_VPS_UI_BACKEND_URL
    if not (value.startswith("/") or value.startswith("http://") or value.startswith("https://")):
        value = "/" + value
    return value.rstrip("/") or DEFAULT_VPS_UI_BACKEND_URL


def _ui_upload_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source).as_posix()
        if rel.endswith(".map"):
            continue
        files.append(path)
    return files


def _file_manifest_entry(source: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(source).as_posix()
    try:
        stat = path.stat()
        size = int(stat.st_size)
    except OSError:
        size = 0
    return {"path": rel, "size_bytes": size}


def _ui_upload_manifest(source: Path, files: list[Path]) -> list[dict[str, Any]]:
    return [_file_manifest_entry(source, path) for path in files]


def _newest_mtime(path: Path, *, exclude_parts: set[str]) -> float:
    try:
        if path.is_file():
            return path.stat().st_mtime
        newest = path.stat().st_mtime
    except OSError:
        return 0.0
    for root, dirs, files in os.walk(path):
        if exclude_parts:
            dirs[:] = [name for name in dirs if name not in exclude_parts]
        for name in files:
            try:
                newest = max(newest, (Path(root) / name).stat().st_mtime)
            except OSError:
                continue
    return newest


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


def _default_vps_env_path() -> Path:
    configured = os.getenv("WINTRIP_VPS_ENV_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root_hint = (
        os.getenv("WINTRIP_HOST_WORKSPACE")
        or os.getenv("WINTRIP_PROJECT_ROOT")
        or os.getenv("WINTRIP_WORKSPACE")
        or os.getenv("WORKSPACE_ROOT")
    )
    root = Path(root_hint).expanduser().resolve() if root_hint else Path(__file__).resolve().parents[1]
    return (root / ".secrets" / "vps.env").resolve()


def _load_vps_env_file() -> dict[str, Any]:
    path = _default_vps_env_path()
    loaded_keys: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"loaded": False, "path": str(path), "loaded_keys": []}
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        if key not in VPS_ENV_KEYS:
            continue
        value = value.strip().strip('"').strip("'")
        if value and not os.getenv(key):
            os.environ[key] = value
            loaded_keys.append(key)
    return {"loaded": True, "path": str(path), "loaded_keys": loaded_keys}


def _vps_env_file_status() -> dict[str, Any]:
    path = _default_vps_env_path()
    return {
        "path": str(path),
        "exists": path.exists(),
        "format": "KEY=value; non-secret SSH profile metadata only",
        "secrets_returned": False,
    }
