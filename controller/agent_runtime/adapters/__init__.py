"""Agent adapters for the agent runtime.

An adapter is any callable matching the `AdapterFn` signature in
`controller.agent_runtime.orchestrator`.
"""

from controller.agent_runtime.adapters.codex_cli import CodexCliAdapter, run_codex_job
from controller.agent_runtime.adapters.ecosystem_cli import (
    atlas_status,
    deepseek_status,
    run_atlas_job,
    run_deepseek_job,
)
from controller.agent_runtime.adapters.ruflo_swarm import (
    analyze_ruflo_swarm_signal,
    ruflo_creative_retry_prompt,
    should_apply_sacred_corruption,
)

__all__ = [
    "CodexCliAdapter",
    "analyze_ruflo_swarm_signal",
    "atlas_status",
    "deepseek_status",
    "ruflo_creative_retry_prompt",
    "run_atlas_job",
    "run_codex_job",
    "run_deepseek_job",
    "should_apply_sacred_corruption",
]
