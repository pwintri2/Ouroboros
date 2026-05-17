# controller/self_training.py
# Deterministic self-training loop built on the safe agent tool registry.

from __future__ import annotations

from typing import Any

from ouroboros_learning.self_improvement_patterns import (
    pattern_audit_contract,
    select_self_improvement_patterns,
)


SELF_TRAINING_PHASES: tuple[str, ...] = (
    "observe_prompt",
    "determine_missing_knowledge",
    "memory_search",
    "browser_research_request",
    "plan",
    "approval_gated_action",
    "reflect",
)


def build_self_training_plan(
    philip_opdracht: str,
    understanding: dict[str, Any] | None = None,
    memory_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = str(philip_opdracht or "").strip()
    understanding = understanding or {}
    missing = determine_missing_knowledge(understanding, memory_result)
    needs_browser = bool(missing.get("needs_browser_research"))
    candidate_actions = list(understanding.get("candidate_actions") or [])
    if not candidate_actions and needs_browser:
        candidate_actions.append({"tool": "browser_research", "approval_required": True})
    self_improvement_contract = pattern_audit_contract(select_self_improvement_patterns())

    steps = [
        {
            "phase": "observe_prompt",
            "tool": "prompt_understanding",
            "purpose": "Parse Philip's opdracht into intent, keywords, and approval signals.",
            "approval_required": False,
        },
        {
            "phase": "determine_missing_knowledge",
            "tool": "prompt_understanding",
            "purpose": "Name what knowledge is missing before acting.",
            "approval_required": False,
        },
        {
            "phase": "memory_search",
            "tool": "memory_search",
            "purpose": "Search local Hippocampus before external research.",
            "approval_required": False,
        },
        {
            "phase": "browser_research_request",
            "tool": "browser_research" if needs_browser else None,
            "purpose": "Request external research only when local memory is insufficient.",
            "approval_required": needs_browser,
            "enabled": needs_browser,
        },
        {
            "phase": "plan",
            "tool": "self_training_plan",
            "purpose": "Choose the smallest approved learning action.",
            "approval_required": False,
        },
        {
            "phase": "approval_gated_action",
            "tool": _first_action_tool(candidate_actions),
            "purpose": "Run only an approved action: training_ingest, browser_research, chatgpt_browser_ask, safe_shell, or run_tests.",
            "approval_required": bool(candidate_actions),
        },
        {
            "phase": "reflect",
            "tool": "training_ingest",
            "purpose": "Store successful learning/reflection in 11D ChromaDB when available.",
            "approval_required": True,
        },
    ]
    return {
        "philip_opdracht": prompt,
        "phases": list(SELF_TRAINING_PHASES),
        "steps": steps,
        "missing_knowledge": missing,
        "candidate_actions": candidate_actions,
        "self_improvement_contract": self_improvement_contract,
        "openrouter_used": False,
        "preferred_local_model": self_improvement_contract["preferred_local_model"],
        "approval_required": any(bool(step.get("approval_required")) for step in steps),
        "next_action": (
            "Ask Philip for Akkoord before browser/action/storage."
            if any(bool(step.get("approval_required")) for step in steps)
            else "Proceed with local memory-backed answer."
        ),
    }


def determine_missing_knowledge(
    understanding: dict[str, Any] | None,
    memory_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    understanding = understanding or {}
    memory_payload = (memory_result or {}).get("result", memory_result or {})
    matches = list(memory_payload.get("matches") or []) if isinstance(memory_payload, dict) else []
    needs_browser = bool(understanding.get("needs_browser_research"))
    missing_items = list(understanding.get("missing_knowledge") or [])
    if not matches and understanding.get("research_query"):
        missing_items.append(
            {
                "kind": "local_memory_gap",
                "reason": "No local memory match was found for the research query.",
                "query": understanding.get("research_query"),
                "tool": "memory_search",
                "approval_required": False,
            }
        )

    return {
        "needs_browser_research": needs_browser,
        "has_local_memory_matches": bool(matches),
        "memory_match_count": len(matches),
        "items": missing_items,
        "research_query": understanding.get("research_query") or "",
    }


def self_training_step(
    philip_opdracht: str,
    registry: Any,
    approval: str = "",
    action: str | None = None,
    action_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = str(philip_opdracht or "").strip()
    trace: list[dict[str, Any]] = []

    understanding_result = registry.run_tool("prompt_understanding", {"prompt": prompt})
    trace.append({"phase": "observe_prompt", "tool_result": understanding_result})
    understanding = understanding_result.get("result", {})

    memory_result = registry.run_tool(
        "memory_search",
        {"query": understanding.get("research_query") or prompt, "limit": 5},
    )
    trace.append({"phase": "memory_search", "tool_result": memory_result})

    missing = determine_missing_knowledge(understanding, memory_result)
    trace.append({"phase": "determine_missing_knowledge", "missing_knowledge": missing})

    browser_result = None
    if missing.get("needs_browser_research"):
        browser_result = registry.run_tool(
            "browser_research",
            {"query": missing.get("research_query") or prompt, "approval": approval, "limit": 3},
        )
        trace.append({"phase": "browser_research_request", "tool_result": browser_result})
    else:
        trace.append(
            {
                "phase": "browser_research_request",
                "tool_result": {
                    "status": "skipped",
                    "tool_name": "browser_research",
                    "reason": "Local memory path is sufficient for this step.",
                },
            }
        )

    plan = build_self_training_plan(prompt, understanding=understanding, memory_result=memory_result)
    trace.append({"phase": "plan", "plan": plan})

    # Execute the action. If in autonomous mode (approval="Akkoord"), we can run more tools.
    action_result = _run_approval_gated_action(
        registry=registry,
        prompt=prompt,
        approval=approval,
        action=action,
        action_args=action_args or {},
        browser_result=browser_result,
    )
    trace.append({"phase": "approval_gated_action", "tool_result": action_result})

    # Reflection: store success in 11D Hippocampus
    reflection = _reflect(prompt, trace, action_result)

    if action_result.get("status") == "success" and not action_result.get("stored_to_memory"):
        # Autonoom opslaan van de geleerde les/wijziging
        store_result = registry.run_tool(
            "training_ingest",
            {
                "text": f"Ouroboros Self-Training Success: {prompt}\nTool: {action_result.get('tool_name')}\nOutput: {action_result.get('stdout', '')[:2000]}",
                "approval": approval,
                "title": f"Self-training result: {action_result.get('tool_name')}"
            }
        )
        reflection["stored_to_memory"] = bool(store_result.get("stored_to_memory"))
        trace.append({"phase": "autonomous_storage", "tool_result": store_result})

    trace.append({"phase": "reflect", "reflection": reflection})

    return {
        "status": reflection["status"],
        "philip_opdracht": prompt,
        "missing_knowledge": missing,
        "plan": plan,
        "trace": trace,
        "action_result": action_result,
        "reflection": reflection,
        "next_action": reflection["next_action"],
    }


def self_training_loop(
    philip_opdracht: str,
    registry: Any,
    approval: str = "",
    max_steps: int = 1,
    action: str | None = None,
    action_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    count = max(1, min(int(max_steps or 1), 5))
    for _index in range(count):
        step = self_training_step(
            philip_opdracht=philip_opdracht,
            registry=registry,
            approval=approval,
            action=action,
            action_args=action_args,
        )
        steps.append(step)
        if step["status"] in {"success", "blocked", "error"}:
            break
    return {
        "status": steps[-1]["status"] if steps else "error",
        "philip_opdracht": str(philip_opdracht or "").strip(),
        "steps": steps,
        "next_action": steps[-1]["next_action"] if steps else "No step executed.",
    }


def _run_approval_gated_action(
    registry: Any,
    prompt: str,
    approval: str,
    action: str | None,
    action_args: dict[str, Any],
    browser_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if action:
        args = dict(action_args)
        args.setdefault("approval", approval)
        return registry.run_tool(action, args)

    if browser_result and browser_result.get("status") == "success" and browser_result.get("stored_to_memory"):
        return {
            "status": "success",
            "tool_name": "browser_research",
            "approval_status": browser_result.get("approval_status"),
            "stored_to_memory": browser_result.get("stored_to_memory"),
            "result": {"reason": "Browser research already stored successful learning."},
        }

    return {
        "status": "blocked" if not _approval_present(approval) else "success",
        "tool_name": "approval_gated_action",
        "approval_status": "approved" if _approval_present(approval) else "pending_philip_akkoord",
        "stored_to_memory": False,
        "result": {
            "reason": (
                "No explicit action selected; waiting for approved training_ingest/safe_shell/run_tests."
                if not _approval_present(approval)
                else "No explicit action selected after approval; plan is ready."
            ),
            "prompt": prompt,
        },
    }


def _reflect(prompt: str, trace: list[dict[str, Any]], action_result: dict[str, Any]) -> dict[str, Any]:
    action_status = action_result.get("status")
    tool_name = action_result.get("tool_name")
    stdout = str(action_result.get("stdout") or "")

    stored = bool(action_result.get("stored_to_memory"))
    blocked = action_status == "blocked" or any(
        entry.get("tool_result", {}).get("status") == "blocked" for entry in trace if isinstance(entry.get("tool_result"), dict)
    )
    error = action_status == "error" or any(
        entry.get("tool_result", {}).get("status") == "error" for entry in trace if isinstance(entry.get("tool_result"), dict)
    )

    is_done = tool_name == "roo_attempt_completion" or "task complete" in stdout.lower()

    if error:
        status = "error"
        next_action = "Inspect failing tool stderr before retrying the self-training step."
    elif blocked:
        status = "blocked"
        next_action = "Ask Philip for Akkoord before external research or storage."
    elif is_done:
        status = "success"
        next_action = "done: Task completed successfully."
    else:
        status = "success"
        next_action = "Use the learned context in the answer and run tests when code behavior changed."

    return {
        "status": status,
        "prompt": prompt,
        "stored_to_memory": stored,
        "phase_count": len(trace),
        "next_action": next_action,
    }


def _first_action_tool(candidate_actions: list[dict[str, Any]]) -> str | None:
    if not candidate_actions:
        return None
    tool = str(candidate_actions[0].get("tool") or "").strip()
    return tool or None


def _approval_present(value: str) -> bool:
    return str(value or "").strip().casefold() == "akkoord"
