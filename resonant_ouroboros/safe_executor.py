"""Approval-gated safe action executor for Resonant Ouroboros Fase 4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import threading
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .self_model import compact_text


ACTION_SCHEMA_VERSION = "ouroboros_safe_actions_proto_1_1_fase_4"
TERMINAL_STATUSES = {"approved", "blocked", "executed", "failed", "rejected"}
SAFE_EXEC_COMMANDS = (
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "sed",
    "grep",
    "rg",
    "find",
    "wc",
    "du",
    "sort",
    "uniq",
    "stat",
    "date",
    "python",
    "python3",
    "pytest",
    "open",
)
SAFE_MACOS_APPS = ("Safari", "TextEdit", "Preview", "Notes")
DANGEROUS_TOKENS = {
    "rm",
    "sudo",
    "su",
    "chmod",
    "chown",
    "mv",
    "cp",
    "ssh",
    "scp",
    "docker",
    "bash",
    "sh",
    "zsh",
    "fish",
    "dd",
    "mkfs",
    "mount",
    "kill",
    "pkill",
    "curl",
    "wget",
    "nc",
    "netcat",
    "osascript",
}
SHELL_METACHARS = {";", "|", "&", ">", "<", "`", "$", "(", ")", "{", "}"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip_output(value: Any, limit: int = 4000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def default_actions_path() -> Path:
    if Path("/workspace").exists():
        return Path("/workspace/data/awake_keeper_actions.json")
    return Path("data/awake_keeper_actions.json")


@dataclass(frozen=True)
class ActionPolicy:
    classification: str
    risk: str
    status: str
    reasons: list[str]
    argv: list[str] | None = None


class SafeActionExecutor:
    """Persist, classify, approve, and execute bounded sandbox-contained actions."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        container_name: str | None = None,
        docker_bin: str | None = None,
        timeout_seconds: float = 45.0,
        enable_docker_exec: bool | None = None,
        enable_sandbox_exec: bool | None = None,
        sandbox_cwd: str | Path | None = None,
    ):
        self.path = Path(path) if path is not None else default_actions_path()
        self.container_name = container_name or os.getenv("OUROBOROS_EXEC_CONTAINER", "ouroboros-fase2-ouroboros-1")
        self.docker_bin = docker_bin or os.getenv("OUROBOROS_DOCKER_BIN", "docker")
        self.timeout_seconds = float(os.getenv("OUROBOROS_EXEC_TIMEOUT", str(timeout_seconds)))
        if enable_docker_exec is None:
            enable_docker_exec = os.getenv("OUROBOROS_ENABLE_DOCKER_EXEC", "false").strip().lower() in {
                "1",
                "true",
                "yes",
                "ja",
                "on",
            }
        if enable_sandbox_exec is None:
            sandbox_default = "true" if Path("/workspace").exists() else "false"
            enable_sandbox_exec = os.getenv("OUROBOROS_ENABLE_SANDBOX_EXEC", sandbox_default).strip().lower() in {
                "1",
                "true",
                "yes",
                "ja",
                "on",
            }
        self.enable_docker_exec = bool(enable_docker_exec)
        self.enable_sandbox_exec = bool(enable_sandbox_exec)
        self.sandbox_cwd = Path(sandbox_cwd or os.getenv("OUROBOROS_SANDBOX_CWD", "/workspace"))
        self._lock = threading.RLock()
        self._store = self._load()

    @classmethod
    def from_env(cls) -> "SafeActionExecutor":
        return cls(path=os.getenv("AWAKE_KEEPER_ACTIONS_PATH") or None)

    @property
    def whitelist(self) -> tuple[str, ...]:
        return SAFE_EXEC_COMMANDS

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": ACTION_SCHEMA_VERSION, "actions": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": ACTION_SCHEMA_VERSION, "actions": []}
        if not isinstance(data, dict):
            return {"schema_version": ACTION_SCHEMA_VERSION, "actions": []}
        data.setdefault("schema_version", ACTION_SCHEMA_VERSION)
        data.setdefault("actions", [])
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp.write_text(json.dumps(self._store, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            actions = list(self._store.get("actions") or [])
            last_action = self._public_action(actions[-1]) if actions else None
            last_result = (last_action or {}).get("result") or {}
            return {
                "pending_count": sum(1 for action in actions if action.get("status") == "pending"),
                "pending_evolution_proposals": sum(
                    1
                    for action in actions
                    if action.get("status") == "pending"
                    and action.get("kind") in {"evolution_proposal", "safe_evolution_proposal"}
                ),
                "blocked_count": sum(1 for action in actions if action.get("status") == "blocked"),
                "approved_count": sum(1 for action in actions if action.get("status") == "approved"),
                "executed_count": sum(1 for action in actions if action.get("status") == "executed"),
                "failed_count": sum(1 for action in actions if action.get("status") == "failed"),
                "rejected_count": sum(1 for action in actions if action.get("status") == "rejected"),
                "review_only_count": sum(
                    1
                    for action in actions
                    if action.get("kind") in {"evolution_proposal", "safe_evolution_proposal", "apply_code_review"}
                ),
                "whitelist": list(SAFE_EXEC_COMMANDS),
                "docker_exec_enabled": self.enable_docker_exec,
                "sandbox_exec_enabled": self.enable_sandbox_exec,
                "sandbox_cwd": str(self.sandbox_cwd),
                "status_label": self._status_label(),
                "last_action": last_action,
                "last_command_feedback": last_result.get("feedback") if isinstance(last_result, dict) else None,
                "last_command_line": (
                    last_result.get("command_line") or shlex.join(last_result.get("argv") or [])
                    if isinstance(last_result, dict)
                    else None
                ),
                "last_exit_code": last_result.get("exit_code") if isinstance(last_result, dict) else None,
                "last_stdout_preview": last_result.get("stdout_preview") if isinstance(last_result, dict) else None,
                "last_stderr_preview": last_result.get("stderr_preview") if isinstance(last_result, dict) else None,
            }

    def list_actions(self, *, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(reversed(self._store.get("actions") or []))
            if status:
                rows = [row for row in rows if row.get("status") == status]
            return [self._public_action(row) for row in rows[: max(1, min(int(limit or 20), 100))]]

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        with self._lock:
            action = self._find(action_id)
            return self._public_action(action) if action else None

    def propose(
        self,
        *,
        kind: str,
        label: str | None = None,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        auto_execute: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            payload = payload or {}
            policy = self.classify(kind=kind, payload=payload)
            now = utc_now()
            human_message = self._human_message(kind=kind, policy=policy, payload=payload)
            action = {
                "id": f"act_{now.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}",
                "kind": compact_text(kind, 80),
                "label": compact_text(label or kind.replace("_", " ").title(), 120),
                "summary": compact_text(summary or payload.get("summary") or "", 700),
                "status": policy.status,
                "classification": policy.classification,
                "risk": policy.risk,
                "payload": payload,
                "source": source or {},
                "safety_reasons": policy.reasons,
                "human_message": human_message,
                "created_at": now,
                "updated_at": now,
                "approved_at": None,
                "approved_by": None,
                "result": None,
            }
            if policy.classification == "blocked":
                action["result"] = {
                    "mode": "blocked",
                    "message": human_message,
                    "feedback": human_message,
                    "stdout": "",
                    "stderr": "",
                    "stdout_preview": "",
                    "stderr_preview": "",
                    "policy_reasons": list(policy.reasons),
                }
            approval_token = None
            if policy.classification == "approval_required" and policy.status == "pending":
                approval_token = f"apr_{uuid4().hex}"
                action["_approval_token_hash"] = self._hash_token(approval_token)
            self._store.setdefault("actions", []).append(action)
            self._save()
            if policy.classification == "auto_safe" and auto_execute and policy.status == "pending":
                action = self._execute(action, policy.argv)
            return {
                "ok": action.get("status") not in {"blocked", "failed"},
                "proposal": self._public_action(action),
                "approval_token": approval_token,
            }

    def approve(
        self,
        action_id: str,
        *,
        approval_token: str,
        approved_by: str = "local_user",
        note: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            action = self._find(action_id)
            if not action:
                raise KeyError(action_id)
            if action.get("status") in TERMINAL_STATUSES:
                return {"ok": False, "proposal": self._public_action(action), "message": "Action is already terminal."}
            if action.get("classification") == "approval_required":
                expected = action.get("_approval_token_hash")
                if not expected or self._hash_token(approval_token) != expected:
                    return {"ok": False, "proposal": self._public_action(action), "message": "Approval token rejected."}
            policy = self.classify(kind=str(action.get("kind") or ""), payload=action.get("payload") or {})
            if policy.classification == "blocked":
                action["status"] = "blocked"
                action["updated_at"] = utc_now()
                action["safety_reasons"] = policy.reasons
                self._save()
                return {"ok": False, "proposal": self._public_action(action), "message": "Action blocked by policy."}
            action["approved_at"] = utc_now()
            action["approved_by"] = compact_text(approved_by, 120)
            if note:
                action["approval_note"] = compact_text(note, 500)
            return {"ok": True, "proposal": self._public_action(self._execute(action, policy.argv))}

    def approve_many(
        self,
        approvals: list[dict[str, Any]],
        *,
        approved_by: str = "local_user",
        note: str | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for item in approvals[:20]:
            action_id = str(item.get("action_id") or item.get("id") or "")
            if not action_id:
                continue
            try:
                results.append(
                    self.approve(
                        action_id,
                        approval_token=str(item.get("approval_token") or ""),
                        approved_by=approved_by,
                        note=note,
                    )
                )
            except Exception as exc:
                results.append({"ok": False, "action_id": action_id, "message": str(exc)})
        return {
            "ok": bool(results) and all(result.get("ok") for result in results),
            "results": results,
            "summary": self.summary(),
        }

    def reject_many(self, action_ids: list[str], *, reason: str | None = None) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for action_id in [str(item) for item in action_ids[:20] if str(item).strip()]:
            try:
                results.append(self.reject(action_id, reason=reason))
            except Exception as exc:
                results.append({"ok": False, "action_id": action_id, "message": str(exc)})
        return {
            "ok": bool(results) and all(result.get("ok") for result in results),
            "results": results,
            "summary": self.summary(),
        }

    def reject(self, action_id: str, *, reason: str | None = None) -> dict[str, Any]:
        with self._lock:
            action = self._find(action_id)
            if not action:
                raise KeyError(action_id)
            if action.get("status") in TERMINAL_STATUSES:
                return {"ok": False, "proposal": self._public_action(action), "message": "Action is already terminal."}
            action["status"] = "rejected"
            action["rejected_at"] = utc_now()
            action["rejection_reason"] = compact_text(reason or "Rejected by local user.", 500)
            action["updated_at"] = action["rejected_at"]
            self._save()
            return {"ok": True, "proposal": self._public_action(action)}

    def classify(self, *, kind: str, payload: dict[str, Any]) -> ActionPolicy:
        normalized = (kind or "").strip().lower()
        if normalized in {"control", "manual_paeu_step", "creative_spike", "clear_queue", "start", "stop"}:
            return ActionPolicy("auto_safe", "low", "pending", ["Bounded Awake Keeper control command."])
        if normalized == "safe_command":
            return self._classify_safe_command(payload)
        if normalized in {"evolution_proposal", "safe_evolution_proposal"}:
            return ActionPolicy(
                "approval_required",
                "medium",
                "pending",
                [
                    "Evolution proposals are review-only and cannot modify files from the running app.",
                    "Human approval records intent before any future manual implementation.",
                ],
            )
        if normalized == "open_url":
            url = str(payload.get("url") or "").strip()
            if self._safe_url(url):
                return ActionPolicy(
                    "approval_required",
                    "medium",
                    "pending",
                    ["HTTP(S) URL is syntactically safe; human approval required before sandbox executor."],
                    self._open_url_argv(url),
                )
            return ActionPolicy("blocked", "high", "blocked", ["Only explicit http(s) URLs are allowed."])
        if normalized == "open_app":
            app = str(payload.get("app") or "").strip()
            url = str(payload.get("url") or "").strip()
            if app in SAFE_MACOS_APPS and (not url or self._safe_url(url)):
                return ActionPolicy(
                    "approval_required",
                    "medium",
                    "pending",
                    ["Safe app whitelist matched; approval required before sandboxed open attempt."],
                    self._open_app_argv(app, url),
                )
            return ActionPolicy("blocked", "high", "blocked", ["App is not on the safe app whitelist."])
        if normalized in {"apply_code_review", "memory_note"}:
            return ActionPolicy(
                "approval_required",
                "medium",
                "pending",
                ["Approval required; handler is review/logging only and does not write host files."],
            )
        return ActionPolicy("blocked", "high", "blocked", [f"Unsupported action kind: {compact_text(kind, 80)}"])

    def _classify_safe_command(self, payload: dict[str, Any]) -> ActionPolicy:
        argv = self._argv_from_payload(payload)
        if not argv:
            return ActionPolicy("blocked", "high", "blocked", ["Command payload is empty."])
        executable = Path(argv[0]).name
        if executable not in SAFE_EXEC_COMMANDS:
            return ActionPolicy("blocked", "high", "blocked", [f"Command '{executable}' is not whitelisted."])
        for token in argv:
            lowered = token.lower()
            if lowered in DANGEROUS_TOKENS:
                return ActionPolicy("blocked", "high", "blocked", [f"Dangerous token blocked: {token}"])
            if any(char in token for char in SHELL_METACHARS):
                return ActionPolicy("blocked", "high", "blocked", ["Shell metacharacters are not allowed."])
        if executable in {"python", "python3"} and not self._safe_python_args(argv[1:]):
            return ActionPolicy("blocked", "high", "blocked", ["Python is restricted to --version/-V or scripts under /workspace."])
        if executable == "pytest" and not self._safe_pytest_args(argv[1:]):
            return ActionPolicy("blocked", "high", "blocked", ["pytest is restricted to /workspace tests and safe read-only options."])
        if executable == "open" and not self._safe_open_args(argv[1:]):
            return ActionPolicy("blocked", "high", "blocked", ["open is restricted to http(s) URLs and safe app names."])
        for token in argv[1:]:
            if self._looks_like_path(token) and not self._safe_path(token):
                return ActionPolicy("blocked", "high", "blocked", [f"Path is outside the safe workspace: {token}"])
        return ActionPolicy(
            "approval_required",
            "medium",
            "pending",
            ["Command is whitelisted and path-bounded; human approval required before sandbox execution."],
            argv,
        )

    def _execute(self, action: dict[str, Any], argv: list[str] | None) -> dict[str, Any]:
        kind = str(action.get("kind") or "")
        now = utc_now()
        action["updated_at"] = now
        try:
            if kind == "apply_code_review":
                result = {
                    "mode": "review_only",
                    "message": "Code was approved for review only. No files were changed.",
                    "code_preview": compact_text((action.get("payload") or {}).get("code"), 1200),
                }
                action["status"] = "executed"
                action["result"] = result
            elif kind in {"evolution_proposal", "safe_evolution_proposal"}:
                payload = action.get("payload") or {}
                result = {
                    "mode": "evolution_review_only",
                    "message": (
                        "Evolution proposal acknowledged for review only. "
                        "No prompts, code, files, commands, or model settings were changed."
                    ),
                    "proposal_preview": compact_text(payload.get("proposal") or action.get("summary"), 1400),
                    "target_files": [compact_text(item, 180) for item in (payload.get("target_files") or [])[:8]],
                    "tests_to_run": [compact_text(item, 180) for item in (payload.get("tests_to_run") or [])[:8]],
                    "risk": compact_text(payload.get("risk"), 160),
                    "feedback": "Proposal is now part of the audit trail; implementation still requires a separate human-approved coding session.",
                }
                action["status"] = "executed"
                action["result"] = result
            elif kind == "memory_note":
                action["status"] = "executed"
                action["result"] = {"mode": "logged", "message": "Memory note accepted for audit logging."}
            elif kind in {"control", "manual_paeu_step", "creative_spike", "clear_queue", "start", "stop"}:
                action["status"] = "executed"
                action["result"] = {"mode": "control_ack", "message": "Control action approved by safe executor."}
            else:
                if not argv:
                    policy = self.classify(kind=kind, payload=action.get("payload") or {})
                    argv = policy.argv
                if not argv:
                    raise RuntimeError("No executable argv for action.")
                if self.enable_sandbox_exec:
                    action["result"] = self._run_sandbox_exec(argv)
                    action["status"] = "executed" if action["result"].get("exit_code") == 0 else "failed"
                elif not self.enable_docker_exec:
                    action["status"] = "approved"
                    action["result"] = {
                        "mode": "sandbox_exec_disabled",
                        "message": (
                            "Action was approved and logged, but sandbox execution is disabled. "
                            "Set OUROBOROS_ENABLE_SANDBOX_EXEC=true to execute inside the app sandbox, "
                            "or OUROBOROS_ENABLE_DOCKER_EXEC=true to execute through Docker."
                        ),
                        "prepared_argv": argv,
                        "prepared_command": self._docker_exec_command(argv),
                        "feedback": "No command output exists because execution is disabled.",
                    }
                else:
                    action["result"] = self._run_docker_exec(argv)
                    action["status"] = "executed" if action["result"].get("exit_code") == 0 else "failed"
        except Exception as exc:
            action["status"] = "failed"
            action["result"] = {
                "mode": "executor_error",
                "error": str(exc),
                "message": f"Safe executor failed before command output was available: {exc}",
                "stdout": "",
                "stderr": str(exc),
                "feedback": f"Execution failed before launch: {exc}",
            }
        finally:
            action["updated_at"] = utc_now()
            self._save()
        return action

    def _run_sandbox_exec(self, argv: list[str]) -> dict[str, Any]:
        cwd = self.sandbox_cwd
        if not cwd.exists():
            return {
                "mode": "sandbox_exec",
                "argv": argv,
                "command_line": shlex.join(argv),
                "cwd": str(cwd),
                "exit_code": 126,
                "stdout": "",
                "stderr": f"Sandbox cwd does not exist: {cwd}",
                "stdout_preview": "",
                "stderr_preview": f"Sandbox cwd does not exist: {cwd}",
                "feedback": "Command was not launched because the configured sandbox directory is unavailable.",
            }
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                env=self._sandbox_env(),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
            return {
                "mode": "sandbox_exec",
                "argv": argv,
                "command_line": shlex.join(argv),
                "cwd": str(cwd),
                "exit_code": 124,
                "stdout": _clip_output(stdout, 4000),
                "stderr": _clip_output(stderr or f"Command timed out after {self.timeout_seconds:.1f}s", 4000),
                "stdout_preview": _clip_output(stdout, 700),
                "stderr_preview": _clip_output(stderr or "Command timed out.", 700),
                "feedback": "Command timed out; partial stdout/stderr are shown when available.",
            }
        return {
            "mode": "sandbox_exec",
            "argv": argv,
            "command_line": shlex.join(argv),
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "stdout": _clip_output(completed.stdout, 4000),
            "stderr": _clip_output(completed.stderr, 4000),
            "stdout_preview": _clip_output(completed.stdout, 700),
            "stderr_preview": _clip_output(completed.stderr, 700),
            "feedback": self._result_feedback(completed.returncode, completed.stdout, completed.stderr),
        }

    def _run_docker_exec(self, argv: list[str]) -> dict[str, Any]:
        docker_command = self._docker_exec_command(argv)
        try:
            completed = subprocess.run(
                docker_command,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
            return {
                "mode": "docker_exec",
                "command": docker_command,
                "command_line": shlex.join(docker_command),
                "exit_code": 124,
                "stdout": _clip_output(stdout, 4000),
                "stderr": _clip_output(stderr or f"Command timed out after {self.timeout_seconds:.1f}s", 4000),
                "stdout_preview": _clip_output(stdout, 700),
                "stderr_preview": _clip_output(stderr or "Command timed out.", 700),
                "feedback": "Docker exec command timed out; partial stdout/stderr are shown when available.",
            }
        return {
            "mode": "docker_exec",
            "command": docker_command,
            "command_line": shlex.join(docker_command),
            "exit_code": completed.returncode,
            "stdout": _clip_output(completed.stdout, 4000),
            "stderr": _clip_output(completed.stderr, 4000),
            "stdout_preview": _clip_output(completed.stdout, 700),
            "stderr_preview": _clip_output(completed.stderr, 700),
            "feedback": self._result_feedback(completed.returncode, completed.stdout, completed.stderr),
        }

    def _docker_exec_command(self, argv: list[str]) -> list[str]:
        return [self.docker_bin, "exec", self.container_name, *argv]

    def _argv_from_payload(self, payload: dict[str, Any]) -> list[str]:
        raw = payload.get("argv")
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]
        command = payload.get("command")
        if isinstance(command, str):
            try:
                return shlex.split(command)
            except ValueError:
                return []
        return []

    def _safe_python_args(self, args: list[str]) -> bool:
        if not args:
            return False
        if args in [["--version"]] or args in [["-V"]]:
            return True
        if args[0] in {"-c", "-m"}:
            return False
        script = args[0]
        return script.endswith(".py") and script.startswith("/workspace/") and self._safe_path(script)

    def _safe_pytest_args(self, args: list[str]) -> bool:
        blocked_prefixes = ("--basetemp", "--rootdir", "--override-ini", "-c", "-p")
        for arg in args:
            if arg.startswith(blocked_prefixes):
                return False
            if arg in {"--collect-only", "-q", "-x", "-s", "-vv", "-v"}:
                continue
            if arg.startswith("-k") or arg.startswith("--maxfail=") or arg.startswith("--tb="):
                continue
            if arg == "tests" or arg.startswith("tests/") or self._looks_like_path(arg):
                normalized = arg if arg.startswith("/") else f"/workspace/{arg.lstrip('./')}"
                if not self._safe_path(normalized):
                    return False
                continue
            return False
        return True

    def _safe_open_args(self, args: list[str]) -> bool:
        if not args:
            return False
        if len(args) == 1:
            return self._safe_url(args[0])
        if len(args) == 2 and args[0] == "-a" and args[1] in SAFE_MACOS_APPS:
            return True
        if len(args) == 3 and args[0] == "-a" and args[1] in SAFE_MACOS_APPS:
            return self._safe_url(args[2])
        return False

    def _open_url_argv(self, url: str) -> list[str]:
        return ["open", url]

    def _open_app_argv(self, app: str, url: str = "") -> list[str]:
        if url:
            return ["open", "-a", app, url]
        return ["open", "-a", app]

    def _safe_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            return False
        return True

    def _looks_like_path(self, value: str) -> bool:
        if value.startswith("-"):
            return False
        return "/" in value or value.startswith(".") or "." in Path(value).name

    def _safe_path(self, value: str) -> bool:
        lowered = value.lower()
        if ".." in Path(value).parts:
            return False
        if any(marker in lowered for marker in ("secret", "credential", "token", "password", ".env", "id_rsa", "ssh")):
            return False
        if Path(value).name.startswith("."):
            return False
        if value.startswith("/"):
            return value.startswith("/workspace/") or value == "/workspace" or value.startswith("/tmp/wintripai/")
        return True

    def _find(self, action_id: str) -> dict[str, Any] | None:
        for action in self._store.get("actions") or []:
            if action.get("id") == action_id:
                return action
        return None

    def _public_action(self, action: dict[str, Any]) -> dict[str, Any]:
        public = {key: value for key, value in action.items() if not key.startswith("_")}
        return json.loads(json.dumps(public))

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _sandbox_env(self) -> dict[str, str]:
        return {
            "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "PYTHONPATH": os.getenv("PYTHONPATH", "/workspace"),
            "PYTHONUNBUFFERED": "1",
            "HOME": os.getenv("HOME", "/tmp/wintripai"),
        }

    def _status_label(self) -> str:
        if self.enable_sandbox_exec:
            return f"Sandbox exec enabled in {self.sandbox_cwd}"
        if self.enable_docker_exec:
            return f"Docker exec enabled for {self.container_name}"
        return "Execution disabled; actions are approved and logged with prepared command feedback."

    def _human_message(
        self,
        *,
        kind: str,
        policy: ActionPolicy,
        payload: dict[str, Any],
    ) -> str:
        """Translate a policy outcome into one short, plain-language sentence.

        The UI surfaces this verbatim under blocked or pending shell actions so
        the user understands *why* something was blocked or what approval will
        do, without having to read raw policy reason codes.
        """

        normalized = (kind or "").strip().lower()
        argv = self._argv_from_payload(payload) if normalized in {"safe_command"} else []
        command_text = " ".join(argv[:6]) if argv else ""
        if policy.classification == "blocked":
            reason = policy.reasons[0] if policy.reasons else "policy blocked this action"
            if "not whitelisted" in reason:
                return (
                    f"Blocked: '{command_text or kind}' uses a command outside the safe whitelist "
                    f"({', '.join(SAFE_EXEC_COMMANDS[:6])} ...). "
                    "Only read-only inspection commands are allowed."
                )
            if "Dangerous token" in reason or "Shell metacharacters" in reason:
                return (
                    "Blocked: this command would let shell punctuation or a destructive verb "
                    "(rm, sudo, mv, cp, curl, etc.) reach the sandbox. The executor refuses on principle."
                )
            if "Path is outside the safe workspace" in reason:
                return (
                    "Blocked: a file path in this command points outside /workspace or at a hidden / "
                    "credential-looking file. Only paths under /workspace (or /tmp/wintripai/) are allowed."
                )
            if "Python is restricted" in reason:
                return (
                    "Blocked: python/python3 may only run --version, -V, or a script that lives under "
                    "/workspace. Inline -c / -m execution is refused."
                )
            if "open is restricted" in reason or "Only explicit http(s) URLs" in reason:
                return (
                    "Blocked: 'open' may only target an http(s) URL or a whitelisted Mac app "
                    f"({', '.join(SAFE_MACOS_APPS)}). Anything else is refused."
                )
            if "Command payload is empty" in reason:
                return "Blocked: the proposal had no command to run."
            if "App is not on the safe app whitelist" in reason:
                return (
                    "Blocked: that app is not on the safe whitelist. "
                    f"Allowed apps: {', '.join(SAFE_MACOS_APPS)}."
                )
            if "Unsupported action kind" in reason:
                return (
                    f"Blocked: action kind '{compact_text(kind, 40)}' is not recognised by the safe executor. "
                    "Only the documented kinds (safe_command, evolution_proposal, control, ...) can be approved."
                )
            return f"Blocked: {reason}"
        if policy.classification == "approval_required":
            if normalized == "safe_command":
                return (
                    f"Pending approval: '{command_text}' is whitelisted and path-bounded but will only run "
                    "after you approve it. It will execute inside the /workspace sandbox."
                )
            if normalized in {"evolution_proposal", "safe_evolution_proposal"}:
                return (
                    "Pending approval: this is a review-only evolution proposal. Approving it just records "
                    "the intent in the co-evolution journal - no files change."
                )
            if normalized == "apply_code_review":
                return (
                    "Pending approval: approving will store the answer's code under audit; nothing is written "
                    "to your filesystem."
                )
            if normalized == "open_url":
                return (
                    f"Pending approval: 'open {compact_text(payload.get('url'), 80) or '...'}' will be handed to "
                    "the sandbox executor only after you approve it."
                )
            if normalized == "open_app":
                return (
                    f"Pending approval: 'open -a {compact_text(payload.get('app'), 40) or '...'}' will be handed "
                    "to the sandbox executor only after you approve it."
                )
            return "Pending approval: action is whitelisted but waits for your one-time approval."
        if policy.classification == "auto_safe":
            return "Auto-safe: a bounded Awake Keeper control command - no shell, no files, no outbound traffic."
        return "Action recorded by the safe executor."

    def _result_feedback(self, exit_code: int, stdout: str, stderr: str) -> str:
        if exit_code == 0:
            if stdout.strip():
                return "Command completed successfully; stdout is available."
            if stderr.strip():
                return "Command completed successfully; stderr contains diagnostic output."
            return "Command completed successfully with no output."
        if stderr.strip():
            return "Command failed; stderr explains the failure."
        if stdout.strip():
            return "Command failed; stdout contains the available command output."
        return "Command failed with no stdout or stderr."
