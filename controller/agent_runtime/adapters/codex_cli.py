"""Codex CLI adapter for the agent runtime.

Runs `codex exec` as a background process. Streams stdout/stderr to log files,
emits structured events for the cockpit, and exposes a `cancel()` hook so the
orchestrator can stop a job.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
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
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._popen = popen_factory
        self._command_builder = command_builder or default_codex_command
        self._env_factory = env_factory or default_codex_env
        self._sleep = sleep
        self._clock = clock

    def run(self, job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        cwd = job.workspace_root or os.getcwd()
        command = self._command_builder(job)
        log.append("command", {"command": [redact(part) for part in command], "cwd": cwd})

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
            log.append("error", {"reason": f"codex not found: {exc}"})
            return {"status": "failed", "exit_code": None, "reason": str(exc)}
        except Exception as exc:
            log.append("error", {"reason": str(exc)})
            return {"status": "failed", "exit_code": None, "reason": str(exc)}

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

        if cancelled:
            status = "cancelled"
        elif timed_out:
            status = "failed"
        elif return_code == 0:
            status = "completed"
        else:
            status = "failed"

        log.append(
            "finished",
            {
                "status": status,
                "exit_code": return_code,
                "timed_out": timed_out,
                "cancelled": cancelled,
            },
        )

        response_preview = (output_text or stdout_text or "").strip()[-2000:]
        return {
            "status": status,
            "exit_code": return_code,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "output": output_text,
            "response_preview": response_preview,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "pid": pid,
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
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".nvm" / "versions" / "node" / "v22.22.2" / "bin"),
        *codex_bins,
    ]
    env["PATH"] = os.pathsep.join([*extras, env.get("PATH", "")])
    return env


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
