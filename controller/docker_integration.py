"""Integration of docker_runner into agentic_processor.

Docker-backed job dispatch for resolve_or_build_function with approval gating.
"""

from __future__ import annotations

from typing import Any

from controller.docker_runner import resolve_or_build_function_docker


def integrate_docker_into_resolve_or_build(
    *,
    requested_capability: str,
    arguments: dict[str, Any] | None = None,
    execute_after_build: bool = False,
    approval: str = "",
) -> dict[str, Any]:
    """Dispatch Docker job for missing Ouroboros capability.

    Wrapped by resolve_or_build_function in agentic_processor.
    Fails closed: Docker unavailable or approval missing -> blocked/approval_required.
    """
    result = resolve_or_build_function_docker(
        requested_capability=requested_capability,
        arguments=arguments or {},
        execute_after_build=execute_after_build,
        approval=approval,
    )
    return result
