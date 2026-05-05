"""Truthful subsystem status semantics shared across the cockpit.

Every subsystem (Codex, AgentS, OpenHands, Living, World, Nexus) used to
report its own ad-hoc status string, and the cockpit converted "exists on disk"
into "available". This module is the single place that defines a truthful
status ladder and a small set of helpers so that no subsystem accidentally
promotes weak evidence into strong claims.

The ladder, from weakest to strongest evidence:

    missing       — root/binary not present
    detected      — files found, no execution proof
    configured    — config/auth files present, no health proof
    available     — execution path verified (a launch/health probe succeeded)
    running       — active process or live loop confirmed
    online        — service responds AND core health checks pass
    degraded      — partial function with known failures
    blocked       — approval/auth/gating issue (action waiting on humans)
    error         — execution attempted and failed

Helpers in this module never read secret files (.env, tokens, OAuth caches);
they only inspect path existence and JSON structural shape.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


STATUS_LADDER: tuple[str, ...] = (
    "missing",
    "detected",
    "configured",
    "available",
    "running",
    "online",
    "degraded",
    "blocked",
    "error",
)

_OPERATIONAL_STATUSES: frozenset[str] = frozenset({"available", "running", "online"})


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a small command probe (e.g. `tool --version`)."""

    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout[-2000:],
            "stderr": self.stderr[-2000:],
            "duration_ms": self.duration_ms,
        }


def is_operational(status: str | None) -> bool:
    """True iff the status implies the subsystem can be used right now."""

    return str(status or "").strip().lower() in _OPERATIONAL_STATUSES


def normalize_status(status: str | None, *, default: str = "missing") -> str:
    """Coerce a free-form status into the ladder; unknowns become `default`."""

    text = str(status or "").strip().lower()
    return text if text in STATUS_LADDER else default


def freshness_seconds(timestamp: float | int | None) -> int | None:
    """Seconds elapsed since `timestamp`. Returns None for invalid inputs."""

    if timestamp is None:
        return None
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return max(0, int(time.time() - ts))


def is_fresh(timestamp: float | int | None, *, max_age_seconds: int) -> bool:
    age = freshness_seconds(timestamp)
    return age is not None and age <= max(0, int(max_age_seconds))


def path_exists(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        return Path(path).expanduser().exists()
    except (OSError, ValueError):
        return False


def find_executable(name: str, *, extra_paths: Iterable[str | Path] = ()) -> str | None:
    """Locate an executable in PATH or in additional candidate paths."""

    direct = shutil.which(name)
    if direct:
        return direct
    for candidate in extra_paths:
        try:
            path = Path(candidate).expanduser()
        except (OSError, ValueError):
            continue
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def run_probe(
    command: list[str],
    *,
    cwd: str | Path | None = None,
    timeout_seconds: int = 5,
    env: dict[str, str] | None = None,
) -> ProbeResult:
    """Run a short command probe and report status without leaking secrets."""

    if not command:
        return ProbeResult(status="error", exit_code=None, stdout="", stderr="empty command", duration_ms=0)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_seconds)),
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        return ProbeResult(
            status="missing",
            exit_code=None,
            stdout="",
            stderr=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(
            status="degraded",
            exit_code=None,
            stdout="",
            stderr=f"probe exceeded {timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        return ProbeResult(
            status="error",
            exit_code=None,
            stdout="",
            stderr=str(exc)[:500],
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    status = "available" if proc.returncode == 0 else "error"
    return ProbeResult(
        status=status,
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        duration_ms=duration_ms,
    )


def evidence_status(
    *,
    root_exists: bool,
    config_present: bool = False,
    runtime_reachable: bool = False,
    process_running: bool = False,
    healthy: bool = False,
    blocked: bool = False,
    errored: bool = False,
) -> str:
    """Resolve a status from binary evidence flags.

    The flags must be set strictly: pass True only if you have verified that
    state. Promotion rules are intentionally conservative — nothing better than
    `available` is returned without a runtime probe success.
    """

    if errored:
        return "error"
    if blocked:
        return "blocked"
    if not root_exists:
        return "missing"
    if healthy and runtime_reachable:
        return "online"
    if process_running:
        return "running"
    if runtime_reachable:
        return "available"
    if config_present:
        return "configured"
    return "detected"


def status_with_reason(status: str, reason: str | None = None) -> dict[str, Any]:
    """Helper to build a small status dict with a single human-readable reason."""

    payload: dict[str, Any] = {"status": normalize_status(status), "fake_success": False}
    if reason:
        payload["reason"] = str(reason)[:1000]
    return payload


def degrade_if_stale(
    status: str,
    *,
    last_seen: float | int | None,
    max_age_seconds: int,
    reason: str | None = None,
) -> tuple[str, str | None]:
    """If `last_seen` is older than `max_age_seconds`, knock the status down.

    Returns the new status and an updated reason. Operational statuses
    (`available`, `running`, `online`) all degrade to `degraded` when stale.
    """

    if status in {"available", "running", "online"}:
        if not is_fresh(last_seen, max_age_seconds=max_age_seconds):
            new_reason = reason or f"No fresh evidence within {max_age_seconds}s; subsystem looks stalled."
            return "degraded", new_reason
    return status, reason


__all__ = [
    "ProbeResult",
    "STATUS_LADDER",
    "degrade_if_stale",
    "evidence_status",
    "find_executable",
    "freshness_seconds",
    "is_fresh",
    "is_operational",
    "normalize_status",
    "path_exists",
    "run_probe",
    "status_with_reason",
]
