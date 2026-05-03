"""Bounded learning acceleration for Ouroboros.

The accelerator combines the existing safe learning paths into one explicit
tick: acquire local knowledge, then immediately rebuild continuous trainer
datasets/jobs from the approved 11D records. Actual LitGPT/Unsloth execution
remains opt-in and approval gated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from controller.knowledge_acquisition import DEFAULT_GEMMA_MODEL, index_knowledge_list, run_knowledge_tick
from controller.trainer_continuous import (
    APPROVAL_PHRASE,
    SUPPORTED_CONTINUOUS_METHODS,
    run_continuous_tick,
)

try:
    from controller.training_dataset_builder import count_approved_records
except Exception:

    def count_approved_records() -> int:
        return 0


KNOWLEDGE_MODES = {"off", "gemma", "browser", "both"}


def accelerate_learning(
    approval: str = "",
    knowledge_mode: str = "gemma",
    knowledge_topics: int = 3,
    start_index: int | None = None,
    model: str = DEFAULT_GEMMA_MODEL,
    continuous_methods: list[str] | None = None,
    execute_training: bool = False,
    max_records: int = 1000,
) -> dict[str, Any]:
    """Run one bounded accelerated-learning pass.

    Default behavior is intentionally fast and local: Gemma distillation plus a
    forced continuous dataset/job tick. Set execute_training=True only when the
    caller explicitly wants real LitGPT/Unsloth training to start.
    """
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}

    clean_mode = str(knowledge_mode or "gemma").strip().lower()
    if clean_mode not in KNOWLEDGE_MODES:
        return {
            "status": "error",
            "reason": f"knowledge_mode must be one of: {', '.join(sorted(KNOWLEDGE_MODES))}",
            "fake_success": False,
        }

    methods = _normalize_methods(continuous_methods)
    bounded_topics = max(0, min(int(knowledge_topics or 0), 10))
    bounded_records = max(1, min(int(max_records or 1000), 10_000))
    started_at = _now_iso()
    approved_before = _safe_count_approved()
    steps: list[dict[str, Any]] = []
    knowledge_result: dict[str, Any] | None = None

    if clean_mode != "off" and bounded_topics > 0:
        index_result = index_knowledge_list(approval=approval)
        steps.append(_step("knowledge_index", index_result))
        knowledge_result = run_knowledge_tick(
            approval=approval,
            mode=clean_mode,
            max_topics=bounded_topics,
            start_index=start_index,
            model=model,
        )
        steps.append(_step("knowledge_tick", knowledge_result))
    else:
        steps.append(
            {
                "name": "knowledge_tick",
                "status": "skipped",
                "reason": "knowledge_mode=off or knowledge_topics=0",
            }
        )

    approved_after_knowledge = _safe_count_approved()
    continuous_result = None
    if methods:
        continuous_result = run_continuous_tick(
            approval=approval if execute_training else "",
            force=True,
            execute_training=execute_training,
            methods=methods,
            max_records=bounded_records,
        )
        steps.append(_step("continuous_tick", continuous_result))
    else:
        steps.append({"name": "continuous_tick", "status": "skipped", "reason": "No continuous methods selected."})

    approved_after = _safe_count_approved()
    return {
        "status": _overall_status(steps),
        "started_at": started_at,
        "completed_at": _now_iso(),
        "knowledge_mode": clean_mode,
        "knowledge_topics": bounded_topics,
        "continuous_methods": methods,
        "execute_training": bool(execute_training),
        "approved_records_before": approved_before,
        "approved_records_after_knowledge": approved_after_knowledge,
        "approved_records_after": approved_after,
        "added_approved_records": max(0, approved_after - approved_before),
        "steps": steps,
        "knowledge": knowledge_result,
        "continuous": continuous_result,
        "fake_success": False,
    }


def _normalize_methods(methods: list[str] | None) -> list[str]:
    values = list(methods or SUPPORTED_CONTINUOUS_METHODS)
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text in SUPPORTED_CONTINUOUS_METHODS and text not in normalized:
            normalized.append(text)
    return normalized


def _step(name: str, result: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(result or {})
    return {
        "name": name,
        "status": str(payload.get("status") or "unknown"),
        "created_count": int(payload.get("created_count") or 0),
        "error_count": int(payload.get("error_count") or 0),
        "reason": payload.get("reason") or payload.get("last_error") or "",
    }


def _overall_status(steps: list[dict[str, Any]]) -> str:
    statuses = [str(step.get("status") or "") for step in steps if step.get("status") != "skipped"]
    if not statuses:
        return "noop"
    if any(status in {"success", "dataset_ready"} for status in statuses):
        return "partial" if any(status in {"error", "blocked", "partial"} for status in statuses) else "success"
    if any(status == "partial" for status in statuses):
        return "partial"
    if any(status == "blocked" for status in statuses):
        return "blocked"
    return "error" if any(status == "error" for status in statuses) else "noop"


def _safe_count_approved() -> int:
    try:
        return int(count_approved_records())
    except Exception:
        return 0


def _now_iso() -> str:
    return datetime.utcnow().isoformat()
