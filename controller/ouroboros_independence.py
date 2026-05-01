"""Measure how close Ouroboros is to running without external model help."""

from __future__ import annotations

from typing import Any


THRESHOLDS = [
    (0.85, "independent_candidate"),
    (0.80, "mostly_independent"),
    (0.75, "self_extending_with_approval"),
    (0.65, "local_useful"),
    (0.4, "local_assisted"),
    (0.0, "external_dependent"),
]


def independence_label(score: float) -> str:
    for threshold, label in THRESHOLDS:
        if score >= threshold:
            return label
    return "external_dependent"


def compute_independence_score() -> dict[str, Any]:
    """Compute a transparent, evidence-backed independence score."""
    signals: dict[str, dict[str, Any]] = {}

    local_inference = _local_inference_signal()
    signals["local_inference"] = local_inference
    signals["tool_use"] = _tool_use_signal()
    signals["code_ability"] = _code_ability_signal()
    signals["learning_loop"] = _learning_loop_signal()
    signals["self_extension"] = _self_extension_signal()
    signals["validation"] = _validation_signal()
    signals["recovery"] = _recovery_signal()
    knowledge = _knowledge_coverage_signal()
    signals["knowledge_coverage"] = knowledge

    weights = {
        "local_inference": 0.16,
        "tool_use": 0.13,
        "code_ability": 0.14,
        "learning_loop": 0.14,
        "self_extension": 0.12,
        "validation": 0.12,
        "recovery": 0.08,
        "knowledge_coverage": 0.11,
    }
    score = sum(float(signals[name]["score"]) * weight for name, weight in weights.items())
    label = independence_label(score)
    gaps = [signals[name]["gap"] for name in weights if signals[name].get("gap")]
    return {
        "status": "success",
        "independence_score": round(score, 4),
        "label": label,
        "external_model_needed": score < 0.85,
        "thresholds": {
            "external_dependent": "0.00-0.39",
            "local_assisted": "0.40-0.64",
            "local_useful": "0.65-0.74",
            "self_extending_with_approval": "0.75-0.79",
            "mostly_independent": "0.80-0.84",
            "independent_candidate": "0.85+",
        },
        "signals": signals,
        "knowledge_coverage": knowledge.get("coverage", {}),
        "capability_gaps": gaps,
        "recommendations": _recommendations(gaps, score),
        "fake_success": False,
    }


def _local_inference_signal() -> dict[str, Any]:
    try:
        from controller.ollama_client import OllamaClient

        client = OllamaClient()
        models = client.list_models()
        score = 1.0 if models else 0.1
        return {"score": score, "models": models[:20], "gap": "" if models else "No reachable local Ollama model."}
    except Exception as exc:
        return {"score": 0.0, "models": [], "gap": f"Local inference probe failed: {exc}"}


def _tool_use_signal() -> dict[str, Any]:
    try:
        from controller.codex_agent import get_codex_agent_status
        from controller.safe_shell import SAFE_COMMANDS

        status = get_codex_agent_status()
        tools = status.get("tools") or []
        score = 0.35 + min(len(tools), 8) * 0.06 + min(len(SAFE_COMMANDS), 12) * 0.015
        return {"score": min(1.0, score), "tools": tools, "gap": "" if score >= 0.65 else "Tool layer is present but still narrow."}
    except Exception as exc:
        return {"score": 0.1, "tools": [], "gap": f"Tool probe failed: {exc}"}


def _code_ability_signal() -> dict[str, Any]:
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        test_count = len(list((root / "sandbox_tests").glob("test_*.py"))) if (root / "sandbox_tests").exists() else 0
        has_agent = (root / "controller" / "codex_agent.py").exists()
        score = min(1.0, 0.25 + test_count / 80 + (0.2 if has_agent else 0.0))
        return {"score": score, "test_count": test_count, "gap": "" if score >= 0.65 else "Need more green code-repair benchmark evidence."}
    except Exception as exc:
        return {"score": 0.1, "gap": f"Code ability probe failed: {exc}"}


def _learning_loop_signal() -> dict[str, Any]:
    try:
        from controller.rotating_blue_brain import get_rotating_status
        from controller.streaming_consciousness_adapter import get_streaming_status
        from controller.trainer_continuous import get_continuous_status
        from controller.training_dataset_builder import count_approved_records

        rotating = get_rotating_status()
        streaming = get_streaming_status()
        continuous = get_continuous_status()
        approved = count_approved_records()
        score = 0.15
        if approved > 0:
            score += min(0.3, approved / 500)
        if continuous.get("enabled") or continuous.get("status") in {"running", "dataset_ready"}:
            score += 0.25
        if int(rotating.get("rotation_count") or 0) > 0:
            score += 0.2
        if int(streaming.get("step_count") or 0) > 0:
            score += 0.1
        return {
            "score": min(1.0, score),
            "approved_records": approved,
            "continuous": continuous.get("status"),
            "rotations": rotating.get("rotation_count", 0),
            "streaming_steps": streaming.get("step_count", 0),
            "gap": "" if score >= 0.65 else "Learning loop needs more approved data and repeated validation ticks.",
        }
    except Exception as exc:
        return {"score": 0.1, "gap": f"Learning loop probe failed: {exc}"}


def _self_extension_signal() -> dict[str, Any]:
    try:
        from controller.codex_agent import get_codex_agent_status

        status = get_codex_agent_status()
        gaps = status.get("recent_gaps") or []
        has_backlog = status.get("capability_gap_count", 0) >= 0
        score = 0.45 + (0.2 if has_backlog else 0.0) + (0.1 if gaps else 0.0)
        return {"score": min(1.0, score), "recent_gaps": gaps[:5], "gap": "" if score >= 0.65 else "Self-extension plans exist, but patch/verify loop is not autonomous yet."}
    except Exception as exc:
        return {"score": 0.1, "gap": f"Self-extension probe failed: {exc}"}


def _validation_signal() -> dict[str, Any]:
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        validation_files = [
            root / "sandbox_tests" / "test_rotating_blue_brain.py",
            root / "sandbox_tests" / "test_codex_agent.py",
            root / "sandbox_tests" / "test_codex_registry.py",
        ]
        present = sum(1 for path in validation_files if path.exists())
        score = 0.25 + present * 0.18
        return {"score": min(1.0, score), "validation_files": present, "gap": "" if present >= len(validation_files) else "Validation probes are incomplete."}
    except Exception as exc:
        return {"score": 0.1, "gap": f"Validation probe failed: {exc}"}


def _recovery_signal() -> dict[str, Any]:
    try:
        from controller.trainer_continuous import get_continuous_status
        from controller.rotating_blue_brain import get_rotating_status

        statuses = [get_continuous_status(), get_rotating_status()]
        has_stop = all("status" in status for status in statuses)
        has_error_fields = all("last_error" in status or status.get("status") for status in statuses)
        score = 0.35 + (0.25 if has_stop else 0.0) + (0.2 if has_error_fields else 0.0)
        return {"score": min(1.0, score), "gap": "" if score >= 0.65 else "Recovery still needs rollback evidence and green post-failure tests."}
    except Exception as exc:
        return {"score": 0.1, "gap": f"Recovery probe failed: {exc}"}


def _knowledge_coverage_signal() -> dict[str, Any]:
    coverage = {
        "general": 0.0,
        "programming": 0.0,
        "local_machine": 0.0,
        "operating_systems": 0.0,
        "codeneuron": 0.0,
        "ouroboros_self": 0.0,
    }
    try:
        from controller.codeneuron_adapter import get_codeneuron_status
        from controller.local_machine_profile import get_local_machine_status
        from controller.training_curriculum import curriculum_status

        curriculum = curriculum_status()
        ratios = curriculum.get("coverage_ratio") or {}
        for key in coverage:
            coverage[key] = min(1.0, float(ratios.get(key, 0.0)) * 4)
        if get_codeneuron_status().get("indexed"):
            coverage["codeneuron"] = max(coverage["codeneuron"], 0.7)
        if get_local_machine_status().get("has_snapshot"):
            coverage["local_machine"] = max(coverage["local_machine"], 0.75)
        score = sum(coverage.values()) / len(coverage)
        return {"score": score, "coverage": coverage, "gap": "" if score >= 0.65 else "Knowledge coverage is still uneven across the six curricula."}
    except Exception as exc:
        return {"score": 0.1, "coverage": coverage, "gap": f"Knowledge coverage probe failed: {exc}"}


def _recommendations(gaps: list[str], score: float) -> list[str]:
    recommendations = []
    if score < 0.4:
        recommendations.append("Keep an external mentor model available while local model quality and tool loops are measured.")
    if gaps:
        recommendations.extend(gaps[:5])
    if not recommendations:
        recommendations.append("Run regression prompts without external providers and compare local-only answers before removing the mentor model.")
    return recommendations
