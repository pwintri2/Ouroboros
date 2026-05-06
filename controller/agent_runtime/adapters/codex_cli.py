"""Codex CLI adapter for the agent runtime.

Runs `codex exec` as a background process. Streams stdout/stderr to log files,
emits structured events for the cockpit, and exposes a `cancel()` hook so the
orchestrator can stop a job.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)
TEST_COMMAND_RE = re.compile(
    r"(?im)(?:^|\b)("
    r"(?:python3?|uv)\s+(?:run\s+)?-m\s+(?:unittest|pytest)[^\n;`]*|"
    r"(?:python3?|uv)\s+(?:run\s+)?pytest[^\n;`]*|"
    r"pytest[^\n;`]*|"
    r"(?:npm|pnpm|yarn)\s+(?:run\s+)?test[^\n;`]*"
    r")"
)


def redact(text: str) -> str:
    redacted = str(text or "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class CodexCliAdapter:
    """Encapsulates the Codex CLI invocation as a long-running job.

    The adapter is intentionally injectable: `popen_factory` and
    `command_builder` exist so tests can stub the subprocess without
    monkeypatching the module.
    """

    def __init__(
        self,
        *,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        command_builder: Callable[[JobRecord], list[str]] | None = None,
        env_factory: Callable[[], dict[str, str]] | None = None,
        workspace_status_reader: Callable[[str], list[dict[str, str]] | None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._popen = popen_factory
        self._command_builder = command_builder or default_codex_command
        self._env_factory = env_factory or default_codex_env
        self._workspace_status_reader = workspace_status_reader or read_workspace_status
        self._sleep = sleep
        self._clock = clock

    def run(self, job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        cwd = job.workspace_root or os.getcwd()
        binary_info = _detect_codex_binary()
        version_info = _detect_codex_version(binary_info)
        log.append(
            "binary",
            {
                "status": binary_info.get("status"),
                "path": binary_info.get("path"),
                "version_status": version_info.get("status"),
                "version": version_info.get("version"),
            },
        )
        if binary_info.get("status") != "found":
            log.append("error", {"reason": "codex binary not found", "category": "binary_missing"})
            return {
                "status": "failed",
                "exit_code": None,
                "reason": "codex binary not found",
                "category": "binary_missing",
                "binary": binary_info,
            }
        command = self._command_builder(job)
        if command and command[0] == "codex":
            command = [str(binary_info["path"]), *command[1:]]
        public_command = [redact(part) for part in command]
        command_text = _format_command(public_command)
        log.append("command", {"command": public_command, "cwd": cwd})

        workspace_before = self._workspace_status_reader(cwd)
        if workspace_before is not None:
            log.append(
                "workspace_before",
                {
                    "dirty_count": len(workspace_before),
                    "paths": [item.get("path", "") for item in workspace_before[:80]],
                },
            )

        stdout_path = Path(job.stdout_file)
        stderr_path = Path(job.stderr_file)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            stdout_handle = stdout_path.open("w", encoding="utf-8")
            stderr_handle = stderr_path.open("w", encoding="utf-8")
            proc = self._popen(
                command,
                cwd=cwd,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                env=self._env_factory(),
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            log.append("error", {"reason": f"codex not found: {exc}", "category": "binary_missing"})
            return {
                "status": "failed",
                "exit_code": None,
                "reason": str(exc),
                "category": "binary_missing",
                "binary": binary_info,
            }
        except Exception as exc:
            log.append("error", {"reason": str(exc), "category": "spawn_failed"})
            return {
                "status": "failed",
                "exit_code": None,
                "reason": str(exc),
                "category": "spawn_failed",
                "binary": binary_info,
            }

        pid = getattr(proc, "pid", None)
        if pid is not None:
            log.append("started", {"pid": pid})
        if on_progress:
            try:
                on_progress({"pid": pid})
            except Exception:
                pass

        deadline = self._clock() + max(1, int(job.timeout_seconds or 240))
        timed_out = False
        cancelled = False
        cancel_check = getattr(job, "_cancel_check", None)
        while True:
            return_code = proc.poll()
            if return_code is not None:
                break
            now = self._clock()
            if cancel_check is not None and cancel_check():
                cancelled = True
                _terminate(proc)
                break
            if now >= deadline:
                timed_out = True
                _terminate(proc)
                break
            self._sleep(0.5)

        try:
            return_code = proc.wait(timeout=5)
        except Exception:
            return_code = proc.poll()

        try:
            stdout_handle.close()
            stderr_handle.close()
        except Exception:
            pass

        stdout_text = redact(_read_tail(stdout_path, 12000))
        stderr_text = redact(_read_tail(stderr_path, 12000))
        output_text = ""
        if job.output_file:
            output_text = redact(_read_tail(Path(job.output_file), 12000))
        workspace_after = self._workspace_status_reader(cwd)
        changed_files = _changed_status_paths(workspace_before, workspace_after)
        dirty_files = [item.get("path", "") for item in (workspace_after or []) if item.get("path")]
        tests_run = _extract_test_commands("\n".join([stdout_text, stderr_text, output_text]))
        artifacts = _existing_artifacts([stdout_path, stderr_path, Path(job.output_file) if job.output_file else None])

        if workspace_after is not None:
            log.append(
                "workspace_after",
                {
                    "dirty_count": len(workspace_after),
                    "changed_files": changed_files[:80],
                    "dirty_files": dirty_files[:120],
                },
            )
        if tests_run:
            log.append("tests_detected", {"tests_run": tests_run})
        log.append("artifacts", {"artifacts": artifacts})

        if cancelled:
            status = "cancelled"
        elif timed_out:
            status = "failed"
        elif return_code == 0:
            status = "completed"
        else:
            status = "failed"

        category = _classify_failure(status, return_code, stdout_text, stderr_text, timed_out)

        log.append(
            "finished",
            {
                "status": status,
                "exit_code": return_code,
                "timed_out": timed_out,
                "cancelled": cancelled,
                "category": category,
            },
        )

        response_preview = (output_text or stdout_text or "").strip()[-2000:]
        return {
            "status": status,
            "exit_code": return_code,
            "command": public_command,
            "commands_run": [command_text],
            "changed_files": changed_files,
            "dirty_files": dirty_files,
            "tests_run": tests_run,
            "artifacts": artifacts,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "output": output_text,
            "response_preview": response_preview,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "pid": pid,
            "category": category,
            "binary": binary_info,
            "version": version_info,
        }


def run_codex_job(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Default adapter entrypoint used by the orchestrator."""

    return CodexCliAdapter().run(job, log, on_progress=on_progress)


def default_codex_command(job: JobRecord) -> list[str]:
    extra_dirs: list[str] = []
    for root in job.allowed_roots or []:
        text = str(root or "").strip()
        if text:
            extra_dirs.extend(["--add-dir", text])
    output_arg: list[str] = []
    if job.output_file:
        output_arg = ["--output-last-message", str(job.output_file)]
    prompt = job.metadata.get("prompt") if isinstance(job.metadata, dict) else None
    if not prompt:
        prompt = job.task
    return [
        "codex",
        "exec",
        "--cd",
        job.workspace_root or os.getcwd(),
        *extra_dirs,
        "--sandbox",
        "workspace-write",
        "--full-auto",
        "--skip-git-repo-check",
        *output_arg,
        prompt,
    ]


def default_codex_env() -> dict[str, str]:
    env = dict(os.environ)
    configured_binary = env.get("WINTRIP_CODEX_BINARY") or env.get("CODEX_BINARY")
    extension_bases = (
        Path.home() / ".windsurf" / "extensions",
        Path.home() / ".vscode" / "extensions",
        Path.home() / ".antigravity" / "extensions",
        Path.home() / ".cursor" / "extensions",
    )
    codex_bins = [
        str(path)
        for base in extension_bases
        for path in sorted(base.glob("openai.chatgpt-*/bin/linux-x86_64"))
        if path.exists()
    ]
    extras = [
        str(Path(configured_binary).expanduser().parent) if configured_binary else "",
        "/codex_native/bin/linux-x86_64",
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".nvm" / "versions" / "node" / "v22.22.2" / "bin"),
        *codex_bins,
    ]
    env["PATH"] = os.pathsep.join([item for item in [*extras, env.get("PATH", "")] if item])
    return env


def read_workspace_status(cwd: str) -> list[dict[str, str]] | None:
    """Return current git porcelain status for `cwd`, or None outside git."""

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return _parse_git_status(proc.stdout)


def _terminate(proc: Any) -> None:
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


def _read_tail(path: Path, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[-limit:]


def _parse_git_status(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in str(text or "").splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or "modified"
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            out.append({"status": redact(status)[:20], "path": redact(path)[:500]})
    return out


def _changed_status_paths(
    before: list[dict[str, str]] | None,
    after: list[dict[str, str]] | None,
) -> list[str]:
    if after is None:
        return []
    before_keys = {_status_key(item) for item in (before or [])}
    changed: list[str] = []
    seen: set[str] = set()
    for item in after:
        path = str(item.get("path") or "")
        if not path or _status_key(item) in before_keys or path in seen:
            continue
        seen.add(path)
        changed.append(path)
    return changed[:200]


def _status_key(item: dict[str, str]) -> str:
    return f"{item.get('status', '')}\0{item.get('path', '')}"


def _extract_test_commands(text: str) -> list[str]:
    commands: list[str] = []
    seen: set[str] = set()
    for match in TEST_COMMAND_RE.finditer(redact(text)):
        command = " ".join(match.group(1).strip().split())
        if not command or command in seen:
            continue
        seen.add(command)
        commands.append(command[:500])
        if len(commands) >= 12:
            break
    return commands


def _existing_artifacts(paths: Iterable[Path | None]) -> list[str]:
    artifacts: list[str] = []
    for path in paths:
        if path is not None and path.exists():
            artifacts.append(str(path))
    return artifacts


def _format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def _detect_codex_binary() -> dict[str, Any]:
    try:
        from controller.codex_status import find_codex_binary

        return find_codex_binary()
    except Exception as exc:
        return {"status": "error", "path": None, "reason": str(exc)[:300]}


def _detect_codex_version(binary_info: dict[str, Any]) -> dict[str, Any]:
    if binary_info.get("status") != "found":
        return {"status": "skipped", "version": None}
    try:
        from controller.codex_status import codex_version

        info = codex_version()
        return {
            "status": info.get("status"),
            "version": info.get("version"),
            "raw": info.get("raw"),
        }
    except Exception as exc:
        return {"status": "error", "version": None, "reason": str(exc)[:300]}


def _classify_failure(
    status: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    timed_out: bool,
) -> str:
    if status == "completed":
        return "ok"
    if timed_out:
        return "timeout"
    blob = f"{stdout}\n{stderr}".lower()
    if "not logged in" in blob or "authentication" in blob or "api key" in blob or "login" in blob:
        return "auth_missing"
    if "sandbox" in blob and ("denied" in blob or "violation" in blob or "blocked" in blob):
        return "sandbox_violation"
    if "command not found" in blob or "no such file" in blob:
        return "binary_missing"
    if exit_code is None:
        return "spawn_failed"
    return "exec_error"
