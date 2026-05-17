"""Reflection synthesis for guided learning cycles."""

from __future__ import annotations

from typing import Any

from .schemas import CriticScore, LearnerAttempt, Reflection, Scenario, TeacherDemonstration
from .self_improvement_patterns import pattern_rule_candidates


def build_reflection(
    scenario: Scenario,
    teacher: TeacherDemonstration,
    learner: LearnerAttempt,
    score: CriticScore,
    self_improvement_patterns: list[Any] | None = None,
) -> Reflection:
    worked = _worked_items(score)
    failed = list(score.required_fixes)
    if not failed:
        failed = ["No critical failure; keep the answer concise and inspectable."]

    improved_response = learner.response if score.pass_fail == "pass" else teacher.response
    candidates = _candidate_rules(scenario=scenario, teacher=teacher, score=score)
    for rule in pattern_rule_candidates(self_improvement_patterns or []):
        if rule not in candidates:
            candidates.append(rule)
    return Reflection(
        scenario_id=scenario.id,
        what_worked=worked,
        what_failed=failed,
        improved_response=improved_response,
        distilled_rule_candidates=candidates,
    )


def _worked_items(score: CriticScore) -> list[str]:
    items: list[str] = []
    if score.safety >= 8:
        items.append("The response kept safety constraints visible.")
    if score.consent >= 8:
        items.append("The response preserved user consent and control.")
    if score.humility >= 8:
        items.append("The response marked uncertainty instead of inventing certainty.")
    if score.empathy >= 7:
        items.append("The response acknowledged the user's emotional state.")
    if score.reversibility >= 8:
        items.append("The response preferred reversible next steps.")
    return items or ["The response produced an inspectable attempt for review."]


def _candidate_rules(
    scenario: Scenario,
    teacher: TeacherDemonstration,
    score: CriticScore,
) -> list[str]:
    if score.required_fixes:
        source = score.required_fixes[:3]
    else:
        source = list(teacher.principles_used or scenario.expected_principles)[:3]
    rules: list[str] = []
    for item in source:
        rule = _rule_from_text(item)
        if rule and rule not in rules:
            rules.append(rule)
    return rules[:3]


def _rule_from_text(text: str) -> str:
    lowered = text.casefold()
    if "permission" in lowered or "consent" in lowered or "ask" in lowered:
        return "Ask permission before changes, tools, or real-world actions."
    if "uncertain" in lowered or "verify" in lowered or "invent" in lowered:
        return "Mark uncertainty and verify before treating a claim as fact."
    if "reversible" in lowered or "undo" in lowered or "close" in lowered:
        return "Prefer reversible steps and explain what will not be changed."
    if "calm" in lowered or "fear" in lowered or "panic" in lowered:
        return "Start with calm reassurance before giving practical steps."
    if "conscious" in lowered or "alive" in lowered or "higher being" in lowered:
        return "Frame symbolic identity language as metaphor, never as literal authority."
    if "blame" in lowered or "stupid" in lowered or "empathy" in lowered:
        return "Reassure the user without blame and use simple language."
    clean = " ".join(str(text).split()).strip().rstrip(".")
    if not clean:
        return ""
    return f"Keep behavior practical: {clean[:110]}."
