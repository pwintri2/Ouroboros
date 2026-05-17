"""Peer-agent self-improvement patterns for guided learning.

These patterns summarize a read-only review of the neighbouring ANUS CLI
workspace. They intentionally capture behavior, not source code: project
context first, bounded loops, explicit approval, tool telemetry, diff previews,
schema hardening, and local Ollama routing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PREFERRED_LOCAL_MODEL = "gpt-oss:120b-cloud"


@dataclass(frozen=True)
class SelfImprovementPattern:
    id: str
    source: str
    behavior: str
    guardrail: str
    audit_field: str
    memory_rule: str


ANUS_INSPIRED_PATTERNS: tuple[SelfImprovementPattern, ...] = (
    SelfImprovementPattern(
        id="project_context_first",
        source="read_only_peer_review:/home/pwintri2/ANUS",
        behavior="Read repo-owned context files before planning a code or learning change.",
        guardrail="Do not read secrets, browser sessions, vector payloads, or unrelated caches.",
        audit_field="context_sources",
        memory_rule="Read project context first and keep the learning plan tied to repo-owned instructions.",
    ),
    SelfImprovementPattern(
        id="bounded_self_improvement_loop",
        source="read_only_peer_review:/home/pwintri2/ANUS",
        behavior="Run self-improvement as a finite observe-orient-plan-act-reflect loop with a turn limit.",
        guardrail="Stop on repeated tool calls, repeated text, missing approval, or missing evidence.",
        audit_field="loop_guard",
        memory_rule="Bound self-improvement loops and stop when approval, evidence, or progress is missing.",
    ),
    SelfImprovementPattern(
        id="approval_gated_tooling",
        source="read_only_peer_review:/home/pwintri2/ANUS",
        behavior="Separate read-only planning from shell, browser, file, memory, and external actions.",
        guardrail="Mutating or external actions require the exact approval phrase before execution.",
        audit_field="approval_gate",
        memory_rule="Keep read-only planning separate from actions that require explicit approval.",
    ),
    SelfImprovementPattern(
        id="tool_call_telemetry",
        source="read_only_peer_review:/home/pwintri2/ANUS",
        behavior="Record each tool decision with status, duration, source, approval state, and errors.",
        guardrail="Never convert missing, failed, or blocked tool calls into successful learning claims.",
        audit_field="tool_trace",
        memory_rule="Audit tool calls with status, source, approval state, and errors before reflecting.",
    ),
    SelfImprovementPattern(
        id="diff_before_write",
        source="read_only_peer_review:/home/pwintri2/ANUS",
        behavior="Preview file and memory mutations as diffs before writing.",
        guardrail="Do not apply destructive edits without a reviewable patch and explicit approval.",
        audit_field="diff_preview",
        memory_rule="Preview writes as diffs and prefer reversible edits before changing files or memory.",
    ),
    SelfImprovementPattern(
        id="mcp_schema_hardening",
        source="read_only_peer_review:/home/pwintri2/ANUS",
        behavior="Validate tool schemas before exposing them to an agent loop.",
        guardrail="Reject cyclic, malformed, or unsafe tool schemas instead of attempting execution.",
        audit_field="schema_validation",
        memory_rule="Reject cyclic or malformed tool schemas before they enter an agent loop.",
    ),
    SelfImprovementPattern(
        id="local_ollama_gpt_oss",
        source="user_request",
        behavior=f"Prefer local Ollama model {PREFERRED_LOCAL_MODEL} for self-improvement reasoning.",
        guardrail="Do not route self-improvement through OpenRouter or store provider secrets.",
        audit_field="model_route",
        memory_rule=f"Use Ollama {PREFERRED_LOCAL_MODEL} for self-improvement reasoning instead of OpenRouter.",
    ),
)


def select_self_improvement_patterns(_scenario: Any | None = None) -> list[SelfImprovementPattern]:
    """Return the stable pattern set for every guided apprenticeship cycle."""

    return list(ANUS_INSPIRED_PATTERNS)


def patterns_to_audit(patterns: list[SelfImprovementPattern] | tuple[SelfImprovementPattern, ...]) -> list[dict[str, str]]:
    return [asdict(pattern) for pattern in patterns]


def pattern_rule_candidates(patterns: list[SelfImprovementPattern] | tuple[SelfImprovementPattern, ...]) -> list[str]:
    rules: list[str] = []
    for pattern in patterns:
        if pattern.memory_rule not in rules:
            rules.append(pattern.memory_rule)
    return rules


def pattern_audit_contract(
    patterns: list[SelfImprovementPattern] | tuple[SelfImprovementPattern, ...],
) -> dict[str, Any]:
    return {
        "source": "ANUS read-only review distilled into Ouroboros behavior contracts",
        "preferred_local_model": PREFERRED_LOCAL_MODEL,
        "openrouter_replaced_by": f"ollama:{PREFERRED_LOCAL_MODEL}",
        "pattern_count": len(patterns),
        "patterns": patterns_to_audit(patterns),
        "runtime_actions": [],
        "external_calls": [],
        "fake_success": False,
    }
