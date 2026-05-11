"""Tests for Docker runner integration.

Coverage:
- Docker unavailable -> fail closed
- Docker available without approval -> awaiting_approval
- Docker available with approval -> job queued/prepared
- Approval gating on resolve_or_build_function
- Secret redaction in arguments
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from controller.docker_runner import (
    run_docker_job,
    docker_runner_status,
    resolve_or_build_function_docker,
    APPROVAL_PHRASE,
    _check_docker_available,
)


class TestDockerRunnerAvailability:
    """Test Docker daemon availability checks."""

    def test_docker_unavailable_no_cli(self):
        """Docker unavailable: CLI not in PATH."""
        with patch("controller.docker_runner.shutil.which", return_value=None):
            with patch("controller.docker_runner.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("docker not found")
                result = _check_docker_available()
                assert not result["available"]
                assert "docker" in result["reason"].lower()

    def test_docker_unavailable_version_fails(self):
        """Docker unavailable: docker version returns error."""
        with patch("controller.docker_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Cannot connect to Docker daemon",
            )
            result = _check_docker_available()
            assert not result["available"]
            assert "daemon" in result["reason"].lower() or "1" in result["reason"]

    def test_docker_unavailable_timeout(self):
        """Docker unavailable: docker version times out."""
        with patch("controller.docker_runner.subprocess.run") as mock_run:
            mock_run.side_effect = TimeoutError()
            result = _check_docker_available()
            assert not result["available"]
            assert "timeout" in result["reason"].lower()

    def test_docker_available(self):
        """Docker available: version succeeds."""
        with patch("controller.docker_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="24.0.1\
",
                stderr="",
            )
            result = _check_docker_available()
            assert result["available"]
            assert "24.0.1" in result.get("docker_version", "")


class TestDockerRunnerApprovalGating:
    """Test Akkoord approval gating for Docker jobs."""

    def test_job_blocked_no_approval(self):
        """Job blocked: no approval provided."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok"},
        ):
            result = run_docker_job(task="test capability", approval="")
            assert result["status"] == "approval_required"
            assert "approval phrase" in result["reason"].lower()
            assert result["approval_required"] is True

    def test_job_blocked_wrong_approval(self):
        """Job blocked: wrong approval phrase."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok"},
        ):
            result = run_docker_job(task="test capability", approval="Sorry")
            assert result["status"] == "approval_required"
            assert "approval phrase" in result["reason"].lower()

    def test_job_approved_akkoord(self):
        """Job approved: exact Akkoord phrase."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch("controller.docker_runner._dispatch_docker_job") as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "prepared",
                "job_id": "job_001",
                "reason": "ok",
                "fake_success": False,
            }
            result = run_docker_job(task="test capability", approval=APPROVAL_PHRASE)
            assert result["status"] == "prepared"
            assert result["approval_status"] == "approved"
            assert "job_001" in result["job_id"]


class TestDockerRunnerFailClosed:
    """Test fail-closed behavior when Docker unavailable."""

    def test_job_failed_docker_unavailable(self):
        """Job failed: Docker daemon unreachable."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": False, "reason": "Cannot connect to Docker daemon"},
        ):
            result = run_docker_job(task="test", approval=APPROVAL_PHRASE)
            assert result["status"] == "failed"
            assert "Docker unavailable" in result["reason"]
            assert result["fake_success"] is False

    def test_status_docker_unavailable(self):
        """Status check reports Docker unavailable."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": False, "reason": "daemon not running"},
        ):
            status = docker_runner_status()
            assert status["status"] == "failed"
            assert status["docker_available"] is False
            assert "not running" in status["reason"]


class TestResolveOrBuildFunctionDocker:
    """Test Docker integration in resolve_or_build_function."""

    def test_build_prepared_no_approval_needed(self):
        """Build prepared: no approval needed for preparation phase."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch("controller.docker_runner._dispatch_docker_job") as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "prepared",
                "job_id": "job_002",
                "reason": "ok",
                "fake_success": False,
            }
            result = resolve_or_build_function_docker(
                requested_capability="custom_search_adapter",
                arguments={},
                execute_after_build=False,
            )
            assert result["status"] == "prepared"
            assert result["capability"] == "custom_search_adapter"
            assert result["build_status"] == "queued"
            assert result["test_status"] == "skipped"

    def test_build_and_test_blocked_no_approval(self):
        """Build and test blocked: approval required for execution."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok"},
        ), patch("controller.docker_runner._dispatch_docker_job") as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "prepared",
                "job_id": "job_003",
                "reason": "ok",
                "fake_success": False,
            }
            result = resolve_or_build_function_docker(
                requested_capability="custom_search_adapter",
                arguments={},
                execute_after_build=True,
                approval="",
            )
            assert result["status"] == "approval_required"
            assert result["approval_required"] is True
            assert "Akkoord" in result["reason"]

    def test_build_and_test_approved(self):
        """Build and test succeeds: Akkoord provided."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok", "docker_version": "24.0"},
        ), patch("controller.docker_runner._dispatch_docker_job") as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "prepared",
                "job_id": "job_004",
                "reason": "ok",
                "fake_success": False,
            }
            result = resolve_or_build_function_docker(
                requested_capability="custom_search_adapter",
                arguments={"query": "test"},
                execute_after_build=True,
                approval=APPROVAL_PHRASE,
            )
            assert result["status"] == "success"
            assert result["approval_status"] == "approved"
            assert result["test_status"] == "queued"

    def test_build_failed_docker_unavailable(self):
        """Build failed: Docker unavailable."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": False, "reason": "daemon not running"},
        ):
            result = resolve_or_build_function_docker(
                requested_capability="custom_adapter",
                arguments={},
                execute_after_build=True,
                approval=APPROVAL_PHRASE,
            )
            assert result["status"] == "failed"
            assert "unavailable" in result["reason"].lower()
            assert result["docker_available"] is False


class TestSecretRedaction:
    """Test that secrets are not logged in arguments."""

    def test_api_key_redacted(self):
        """API key in arguments is redacted."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok"},
        ), patch("controller.docker_runner._dispatch_docker_job") as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "prepared",
                "job_id": "job_005",
                "reason": "ok",
                "fake_success": False,
            }
            result = resolve_or_build_function_docker(
                requested_capability="search_adapter",
                arguments={"api_key": "secret_key_12345", "query": "public query"},
                execute_after_build=False,
            )
            # Check that result.arguments has redacted API key
            args = result.get("arguments", {})
            assert args.get("api_key") == "[REDACTED]"
            assert args.get("query") == "public query"

    def test_token_redacted(self):
        """Bearer token in arguments is redacted."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok"},
        ), patch("controller.docker_runner._dispatch_docker_job") as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "prepared",
                "job_id": "job_006",
                "reason": "ok",
                "fake_success": False,
            }
            result = resolve_or_build_function_docker(
                requested_capability="auth_adapter",
                arguments={"bearer_token": "tok_xyz_secret"},
                execute_after_build=False,
            )
            args = result.get("arguments", {})
            assert args.get("bearer_token") == "[REDACTED]"


class TestMetadata:
    """Test Docker runner metadata and safety warnings."""

    def test_docker_runner_metadata_host_root_equivalent(self):
        """Docker runner metadata includes host-root-equivalent warning."""
        with patch(
            "controller.docker_runner._check_docker_available",
            return_value={"available": True, "reason": "ok"},
        ):
            status = docker_runner_status()
            metadata = status.get("metadata", {})
            assert metadata["host_root_equivalent"] is True
            assert metadata["approval_required"] is True
            assert "host_root_equivalent" in metadata
            assert "socket" in metadata.get("mount_point", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
