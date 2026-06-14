"""Grok CLI adapter for the agent runtime."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.adapters.codex_cli import (
    _changed_status_paths,
    _classify_failure,
    _existing_artifacts,
    _extract_test_commands,
    _format_command,
    _read_tail,
    _terminate,
    read_workspace_status,
    redact,
)
from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord


DEFAULT_GROK_BINARY = "/home/pwintri2/.local/bin/grok"
DEFAULT_GROK_MODEL = "grok-composer-2.5-fast"


class GrokCliAdapter:
    """Runs Grok CLI as a background coding job."""

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
        self._command_builder = command_builder or default_grok_command
        self._env_factory = env_factory or default_grok_env
        self._workspace_status_reader = workspace_status_reader or read_workspace_status
        self._sleep = sleep
        self._clock = clock

    def run(self, job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        cwd = job.workspace_root or os.getcwd()
        binary_info = grok_binary_status()
        log.append(
            "binary",
            {
                "status": binary_info.get("status"),
                "path": binary_info.get("path"),
                "version": binary_info.get("version"),
            },
        )
        if binary_info.get("status") != "found":
            log.append("error", {"reason": "grok binary not found", "category": "binary_missing"})
            return {
                "status": "failed",
                "exit_code": None,
                "reason": "grok binary not found",
                "category": "binary_missing",
                "binary": binary_info,
            }

        command = self._command_builder(job)
        if command and command[0] == "grok":
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
            log.append("error", {"reason": f"grok not found: {exc}", "category": "binary_missing"})
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
        workspace_after = self._workspace_status_reader(cwd)
        changed_files = _changed_status_paths(workspace_before, workspace_after)
        dirty_files = [item.get("path", "") for item in (workspace_after or []) if item.get("path")]
        tests_run = _extract_test_commands("\n".join([stdout_text, stderr_text]))
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

        response_preview = (stdout_text or stderr_text or "").strip()[-2000:]
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
            "output": stdout_text,
            "response_preview": response_preview,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "pid": pid,
            "category": category,
            "binary": binary_info,
        }


def run_grok_job(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    return GrokCliAdapter().run(job, log, on_progress=on_progress)


def default_grok_command(job: JobRecord) -> list[str]:
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    prompt = str(metadata.get("prompt") or job.task or "").strip()
    model = str(metadata.get("model") or os.getenv("WINTRIP_GROK_MODEL") or DEFAULT_GROK_MODEL).strip()
    max_turns = str(metadata.get("max_turns") or os.getenv("WINTRIP_GROK_MAX_TURNS") or "20").strip()
    command = [
        "grok",
        "--cwd",
        job.workspace_root or os.getcwd(),
        "--no-memory",
        "--disable-web-search",
        "--permission-mode",
        "acceptEdits",
        "--max-turns",
        max_turns,
        "--output-format",
        "plain",
    ]
    if model:
        command.extend(["--model", model])
    command.extend(["-p", prompt])
    return command


def default_grok_env() -> dict[str, str]:
    env = dict(os.environ)
    configured_binary = env.get("WINTRIP_GROK_BINARY") or env.get("GROK_BIN")
    extras = [
        str(Path(configured_binary).expanduser().parent) if configured_binary else "",
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".cargo" / "bin"),
        str(Path.home() / ".nvm" / "versions" / "node" / "v22.22.2" / "bin"),
    ]
    env["PATH"] = os.pathsep.join([item for item in [*extras, env.get("PATH", "")] if item])
    return env


def grok_binary_status() -> dict[str, Any]:
    binary = _resolve_grok_binary()
    if binary is None:
        return {"status": "missing", "path": "", "version": "", "fake_success": False}
    version = ""
    try:
        proc = subprocess.run(
            [str(binary), "--version"],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
            env=default_grok_env(),
        )
        version = redact((proc.stdout or proc.stderr or "").strip())
    except Exception as exc:
        version = f"version probe failed: {exc}"
    return {"status": "found", "path": str(binary), "version": version, "fake_success": False}


def _resolve_grok_binary() -> Path | None:
    configured = os.getenv("WINTRIP_GROK_BINARY") or os.getenv("GROK_BIN")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path(DEFAULT_GROK_BINARY))
    for path_part in default_grok_env().get("PATH", "").split(os.pathsep):
        if path_part:
            candidates.append(Path(path_part) / "grok")
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        except Exception:
            continue
    return None


__all__ = [
    "DEFAULT_GROK_MODEL",
    "GrokCliAdapter",
    "default_grok_command",
    "grok_binary_status",
    "run_grok_job",
]
