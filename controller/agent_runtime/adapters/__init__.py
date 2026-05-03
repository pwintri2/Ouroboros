"""Agent adapters for the agent runtime.

An adapter is any callable matching the `AdapterFn` signature in
`controller.agent_runtime.orchestrator`. Phase 1 ships only the Codex
adapter; Claude / Roo / Ruflo land in later phases.
"""

from controller.agent_runtime.adapters.codex_cli import CodexCliAdapter, run_codex_job

__all__ = ["CodexCliAdapter", "run_codex_job"]
