"""Tests for the approval-gated Ouroboros Docker runner."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import Mock, patch

from controller.docker_runner import (
    APPROVAL_PHRASE,
    _check_docker_available,
    docker_runner_status,
    resolve_or_build_function_docker,
    run_docker_job,
)


class DockerRunnerTests(unittest.TestCase):
    def test_docker_unavailable_when_version_fails(self) -> None:
        failed = Mock(returncode=1, stdout="", stderr="Cannot connect to Docker daemon")
        with patch("controller.docker_runner.subprocess.run", return_value=failed):
            result = _check_docker_available()
        self.assertFalse(result["available"])
        self.assertIn("docker version returned 1", result["reason"])

    def test_docker_unavailable_when_version_times_out(self) -> None:
        with patch(
            "controller.docker_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["docker"], timeout=3),
        ):
            result = _check_docker_available()
        self.assertFalse(result["available"])
        self.assertIn("timed out", result["reason"])

    def test_docker_available_when_version_succeeds(self) -> None:
        ok = Mock(returncode=0, stdout="24.0.1\n", stderr="")
        with patch("controller.docker_runner.subprocess.run", return_value=ok):
            result = _check_docker_available()
        self.assertTrue(result["available"])
        self.assertEqual(result["docker_version"], "24.0.1")

    def test_run_docker_job_requires_exact_approval(self) -> None:
        result = run_docker_job(task="test capability", approval="")
        self.assertEqual(result["status"], "approval_required")
        self.assertTrue(result["approval_required"])

        result = run_docker_job(task="test capability", approval="akkoord")
        self.assertEqual(result["status"], "approval_required")

    def test_run_docker_job_fails_closed_when_docker_unavailable(self) -> None:
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": False, "reason": "daemon not running"},
        ):
            result = run_docker_job(task="test", approval=APPROVAL_PHRASE)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Docker unavailable", result["reason"])
        self.assertFalse(result["fake_success"])

    def test_run_docker_job_prepares_when_approved(self) -> None:
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch(
            "controller.docker_runner._dispatch_docker_job",
            return_value={"status": "prepared", "job_id": "job_001", "reason": "ok"},
        ):
            result = run_docker_job(task="test capability", approval=APPROVAL_PHRASE)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["approval_status"], "approved")
        self.assertEqual(result["job_id"], "job_001")

    def test_resolve_or_build_prepares_without_execution_approval(self) -> None:
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch(
            "controller.docker_runner._dispatch_docker_job",
            return_value={"status": "prepared", "job_id": "job_002", "reason": "ok"},
        ):
            result = resolve_or_build_function_docker(
                requested_capability="custom_search_adapter",
                arguments={},
                execute_after_build=False,
            )
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["build_status"], "queued")
        self.assertEqual(result["test_status"], "skipped")

    def test_resolve_or_build_execution_requires_approval(self) -> None:
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch(
            "controller.docker_runner._dispatch_docker_job",
            return_value={"status": "prepared", "job_id": "job_003", "reason": "ok"},
        ):
            result = resolve_or_build_function_docker(
                requested_capability="custom_search_adapter",
                arguments={},
                execute_after_build=True,
                approval="",
            )
        self.assertEqual(result["status"], "approval_required")
        self.assertTrue(result["approval_required"])

    def test_resolve_or_build_redacts_secret_arguments(self) -> None:
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch(
            "controller.docker_runner._dispatch_docker_job",
            return_value={"status": "prepared", "job_id": "job_004", "reason": "ok"},
        ):
            result = resolve_or_build_function_docker(
                requested_capability="search_adapter",
                arguments={"api_key": "secret", "query": "public query"},
                execute_after_build=False,
            )
        self.assertEqual(result["arguments"]["api_key"], "[REDACTED]")
        self.assertEqual(result["arguments"]["query"], "public query")

    def test_status_includes_host_root_equivalent_warning(self) -> None:
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ):
            result = docker_runner_status()
        self.assertEqual(result["status"], "online")
        self.assertTrue(result["metadata"]["host_root_equivalent"])
        self.assertTrue(result["metadata"]["approval_required"])


if __name__ == "__main__":
    unittest.main()
