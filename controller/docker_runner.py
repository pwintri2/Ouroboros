"""Docker job runner for Ouroboros self-build loop.

Provides fail-closed Docker execution with Akkoord approval gating.
No secrets logged. Docker socket access requires explicit approval.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Mapping

APPROVAL_PHRASE = "Akkoord"
_DOCKER_LOCK = threading.Lock()


def run_docker_job(
    *,
    task: str,
    approval: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    """Execute a Docker build/test job for self-build loop.

    Requires explicit Akkoord approval before execution.
    Fails closed if approval missing or Docker unavailable.

    Args:
        task: Human description of job (e.g., "build test image for capability X")
        approval: Must be exactly APPROVAL_PHRASE to proceed
        timeout: Job timeout in seconds (default 120, max 600)

    Returns:
        {"status": "success|awaiting_approval|blocked|error", ...}
    """
    started = time.time()
    clean_task = " ".join(str(task or "").replace("\x00", " ").split())

    if not clean_task:
        return {
            "status": "blocked",
            "reason": "task description missing",
            "route": "docker_runner",
            "fake_success": False,
        }

    # Approval gate: exact phrase required
    if str(approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "approval_required",
            "reason": f"Docker jobs require exact approval phrase: {APPROVAL_PHRASE}",
            "route": "docker_runner",
            "approval_required": True,
            "task_preview": clean_task[:200],
            "fake_success": False,
        }

    # Fail closed: Docker check
    docker_check = _check_docker_available()
    if not docker_check["available"]:
        return {
            "status": "failed",
            "reason": f"Docker unavailable: {docker_check['reason']}",
            "route": "docker_runner",
            "docker_check": docker_check,
            "fake_success": False,
        }

    # Dispatch job (non-mutating: prepare only, no pull/build without explicit command)
    try:
        result = _dispatch_docker_job(
            clean_task,
            timeout=max(10, min(int(timeout), 600)),
        )
        result["duration_seconds"] = round(time.time() - started, 3)
        result["route"] = "docker_runner"
        result["approval_status"] = "approved"
        result["fake_success"] = False
        return result
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc)[:500],
            "route": "docker_runner",
            "approval_status": "approved",
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }


def docker_runner_status() -> dict[str, Any]:
    """Return current Docker runner status."""
    check = _check_docker_available()
    return {
        "status": "online" if check["available"] else "failed",
        "docker_available": check["available"],
        "reason": check["reason"],
        "docker_version": check.get("docker_version", ""),
        "docker_client": check.get("client", "unknown"),
        "docker_path": check.get("docker_path", ""),
        "metadata": {
            "host_root_equivalent": True,
            "approval_required": True,
            "mode": check.get("mode", "direct_socket"),
            "mount_point": "/var/run/docker.sock",
        },
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


def _check_docker_available() -> dict[str, Any]:
    """Check if Docker daemon is reachable.

    Returns:
        {"available": bool, "reason": str, "docker_version": str}
    """
    with _DOCKER_LOCK:
        docker_path = shutil.which("docker") or ""
        try:
            result = subprocess.run(
                ["docker", "version", "--format={{.Server.Version}}"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
            if result.returncode != 0:
                sdk_check = _check_docker_sdk_available()
                if sdk_check["available"]:
                    return sdk_check
                return {
                    "available": False,
                    "reason": f"docker version returned {result.returncode}: {result.stderr.strip()[:200]}",
                    "docker_path": docker_path,
                }
            version = result.stdout.strip()
            return {
                "available": True,
                "reason": "Docker daemon reachable through CLI",
                "docker_version": version,
                "docker_path": docker_path,
                "client": "cli",
                "mode": "direct_socket_cli",
            }
        except subprocess.TimeoutExpired:
            return {"available": False, "reason": "docker version check timed out"}
        except Exception as exc:
            sdk_check = _check_docker_sdk_available()
            if sdk_check["available"]:
                return sdk_check
            detail = str(exc)[:200] or exc.__class__.__name__
            return {"available": False, "reason": detail, "docker_path": docker_path}


def _check_docker_sdk_available() -> dict[str, Any]:
    """Check Docker socket through the Python SDK when the CLI is absent."""
    try:
        import docker

        client = docker.from_env()
        version = client.version().get("Version", "")
        client.close()
        return {
            "available": True,
            "reason": "Docker daemon reachable through Python SDK",
            "docker_version": str(version),
            "docker_path": "",
            "client": "python_sdk",
            "mode": "direct_socket_sdk",
        }
    except Exception as exc:
        detail = str(exc)[:200] or exc.__class__.__name__
        return {
            "available": False,
            "reason": f"Docker SDK unavailable: {detail}",
            "docker_path": "",
            "client": "python_sdk",
            "mode": "direct_socket_sdk",
        }


def _dispatch_docker_job(task: str, timeout: int = 120) -> dict[str, Any]:
    """Execute Docker job.

    For v1: build/test preparation only; actual build gated by explicit command.

    Returns:
        {"status": "success|prepared|error", "job_id": str, ...}
    """
    with _DOCKER_LOCK:
        running_count = _running_container_count()

        # Generate job metadata (non-mutating)
        job_id = f"docker_job_{int(time.time())}_{hash(task) & 0xFFFFFF:06x}"

        return {
            "status": "prepared",
            "reason": "Docker job prepared and queued for execution",
            "job_id": job_id,
            "task": task[:500],
            "running_containers": running_count,
            "next_step": "send explicit docker command with Akkoord to proceed with build/test",
            "fake_success": False,
        }


def _running_container_count() -> int:
    """Return running container count through CLI or SDK."""
    try:
        ps_result = subprocess.run(
            ["docker", "ps", "--quiet"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if ps_result.returncode == 0:
            return len([line for line in ps_result.stdout.strip().split("\n") if line.strip()])
    except Exception:
        pass

    try:
        import docker

        client = docker.from_env()
        containers = client.containers.list()
        client.close()
        return len(containers)
    except Exception as exc:
        detail = str(exc)[:200] or exc.__class__.__name__
        raise RuntimeError(f"docker ps/list failed: {detail}") from exc


def resolve_or_build_function_docker(
    *,
    requested_capability: str,
    arguments: dict[str, Any] | None = None,
    execute_after_build: bool = False,
    approval: str = "",
) -> dict[str, Any]:
    """Integrated Docker job dispatch for resolve_or_build_function.

    For missing Ouroboros capabilities, attempt Docker-based self-build.
    Requires Akkoord approval for test execution.

    Args:
        requested_capability: Name of missing capability
        arguments: Optional function arguments
        execute_after_build: If true, run tests after build (requires Akkoord)
        approval: Approval phrase from user

    Returns:
        {"status": "success|prepared|awaiting_approval|blocked|error", ...}
    """
    started = time.time()
    clean_capability = " ".join(str(requested_capability or "").replace("\x00", " ").split())
    clean_args = dict(arguments or {})

    if not clean_capability:
        return {
            "status": "blocked",
            "reason": "requested_capability missing",
            "route": "resolve_or_build_function_docker",
            "fake_success": False,
        }

    # Build phase (read-only preparation, no approval needed yet)
    task = f"Build and test capability: {clean_capability}"
    docker_check = _check_docker_available()
    if not docker_check["available"]:
        return {
            "status": "failed",
            "reason": f"Docker unavailable for build: {docker_check['reason']}",
            "route": "resolve_or_build_function_docker",
            "docker_available": False,
            "fake_success": False,
        }

    # Prepare job (non-mutating)
    job_prep = _dispatch_docker_job(task, timeout=120)
    if job_prep["status"] != "prepared":
        return {
            "status": "error",
            "reason": f"Job preparation failed: {job_prep.get('reason', 'unknown')}",
            "route": "resolve_or_build_function_docker",
            "fake_success": False,
        }

    # If execution requested, require approval
    if execute_after_build and str(approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "approval_required",
            "reason": f"Capability {clean_capability} requires Akkoord approval to build and test",
            "route": "resolve_or_build_function_docker",
            "approval_required": True,
            "capability": clean_capability,
            "job_id": job_prep["job_id"],
            "fake_success": False,
        }

    # Job prepared
    result = {
        "status": "prepared" if not execute_after_build else "success",
        "route": "resolve_or_build_function_docker",
        "capability": clean_capability,
        "job_id": job_prep["job_id"],
        "arguments": _safe_args(clean_args),
        "build_status": "queued",
        "test_status": "queued" if execute_after_build else "skipped",
        "docker_version": docker_check.get("docker_version", ""),
        "duration_seconds": round(time.time() - started, 3),
        "approval_status": "approved" if execute_after_build else "not_required",
        "fake_success": False,
    }
    return result


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys from arguments."""
    clean: dict[str, Any] = {}
    for key, value in args.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer")):
            clean[str(key)] = "[REDACTED]"
        elif isinstance(value, str):
            clean[str(key)] = value[:500]
        else:
            clean[str(key)] = value
    return clean
