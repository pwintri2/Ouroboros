"""Ruflo swarm Nexus helpers.

Ruflo itself is normally reached through the host bridge or a handoff file.
This adapter-side helper adds the v4.3 "sacred corruption" behavior safely:
when repeated low-coherence signals are observed, it returns a divergent retry
prompt instead of mutating files or spawning extra processes.
"""

from __future__ import annotations

from typing import Any

from ouroboros_esoteric.quantum_corruption_nexus import (
    SACRED_CORRUPTION_COHERENCE_THRESHOLD,
    creative_corruption_prompt,
    get_quantum_corruption_nexus,
)


def analyze_ruflo_swarm_signal(
    task: str,
    *,
    coherence: float,
    agent_id: str = "ruflo",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a Ruflo coherence signal and return the Nexus decision."""

    return get_quantum_corruption_nexus().record_ruflo_coherence(
        task=task,
        coherence=coherence,
        agent_id=agent_id,
        metadata=metadata or {},
    )


def ruflo_creative_retry_prompt(task: str, *, reason: str = "") -> str:
    return creative_corruption_prompt(task, reason=reason or "Ruflo swarm coherence stalled twice.")


def should_apply_sacred_corruption(coherence: float) -> bool:
    return float(coherence) < SACRED_CORRUPTION_COHERENCE_THRESHOLD
