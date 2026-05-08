#!/usr/bin/env python3
"""Smoke test for the Ouroboros Docker runner wiring."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def smoke_test_docker_runner() -> dict[str, Any]:
    tests_passed = 0
    tests_failed = 0
    details: list[str] = []

    try:
        from controller.runtime_doctor import runtime_doctor_payload

        doctor = runtime_doctor_payload(include_http_backend_check=False)
        docker_check = doctor.get("checks", {}).get("docker_runner", {})
        docker_status = docker_check.get("status")
        if docker_status in {"online", "failed"}:
            tests_passed += 1
            details.append(f"Docker runtime doctor returned {docker_status}")
        else:
            tests_failed += 1
            details.append(f"Docker runtime doctor returned unexpected status {docker_status}")

        metadata = docker_check.get("metadata", {})
        if metadata.get("host_root_equivalent") and metadata.get("approval_required"):
            tests_passed += 1
            details.append("Docker runner metadata includes host-root-equivalent approval warning")
        else:
            tests_failed += 1
            details.append("Docker runner metadata is missing safety flags")
    except Exception as exc:
        tests_failed += 1
        details.append(f"Docker runtime doctor error: {exc}")

    try:
        from controller.docker_runner import APPROVAL_PHRASE, run_docker_job

        result = run_docker_job(task="test", approval="")
        if result.get("status") == "approval_required":
            tests_passed += 1
            details.append("Docker runner blocks jobs without Akkoord")
        else:
            tests_failed += 1
            details.append(f"Docker runner did not block missing approval: {result.get('status')}")

        result = run_docker_job(task="test", approval="Sorry")
        if result.get("status") == "approval_required":
            tests_passed += 1
            details.append("Docker runner blocks jobs with the wrong phrase")
        else:
            tests_failed += 1
            details.append(f"Docker runner did not block wrong approval: {result.get('status')}")

        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": False, "reason": "daemon not running"},
        ):
            result = run_docker_job(task="test", approval=APPROVAL_PHRASE)
        if result.get("status") == "failed" and "unavailable" in result.get("reason", "").lower():
            tests_passed += 1
            details.append("Docker runner fails closed when Docker is unavailable")
        else:
            tests_failed += 1
            details.append(f"Docker runner fail-closed check returned {result.get('status')}")
    except Exception as exc:
        tests_failed += 1
        details.append(f"Docker runner approval/fail-closed error: {exc}")

    try:
        from controller.docker_runner import resolve_or_build_function_docker

        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "test"},
        ), patch(
            "controller.docker_runner._dispatch_docker_job",
            return_value={"status": "prepared", "job_id": "test_001", "reason": "ok"},
        ):
            result = resolve_or_build_function_docker(
                requested_capability="test",
                arguments={"api_key": "secret_xyz", "query": "public"},
                execute_after_build=False,
            )
        args = result.get("arguments", {})
        if args.get("api_key") == "[REDACTED]" and args.get("query") == "public":
            tests_passed += 1
            details.append("Docker runner redacts secret-looking arguments")
        else:
            tests_failed += 1
            details.append("Docker runner argument redaction failed")
    except Exception as exc:
        tests_failed += 1
        details.append(f"Docker runner redaction error: {exc}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", "controller/docker_runner.py"],
            cwd=ROOT,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            tests_passed += 1
            details.append("controller/docker_runner.py compiles")
        else:
            tests_failed += 1
            details.append(result.stderr.decode("utf-8", errors="replace")[:200])
    except Exception as exc:
        tests_failed += 1
        details.append(f"Docker runner compile check error: {exc}")

    return {
        "status": "success" if tests_failed == 0 else "partial_failure",
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "details": details,
        "fake_success": False,
    }


if __name__ == "__main__":
    output = smoke_test_docker_runner()
    print(json.dumps(output, indent=2, sort_keys=True))
    raise SystemExit(0 if output["tests_failed"] == 0 else 1)
