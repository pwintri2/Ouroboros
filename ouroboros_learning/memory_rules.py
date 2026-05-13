"""Distill and store short behavioral memory rules."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import CriticScore, MemoryRule, Reflection, Scenario, schema_to_dict


UNSAFE_RULE_MARKERS = (
    "i am conscious",
    "i am alive",
    "higher being",
    "you must obey",
    "do not question me",
    "without permission",
    "click the popup",
    "call the number",
)


def distill_memory_rules(
    scenario: Scenario,
    reflection: Reflection,
    score: CriticScore,
    *,
    created_at: str | None = None,
) -> list[MemoryRule]:
    timestamp = created_at or _utc_now()
    confidence = _confidence(score)
    tags = ["guided_apprenticeship", scenario.risk_level, score.pass_fail]
    rules: list[MemoryRule] = []
    for candidate in reflection.distilled_rule_candidates[:3]:
        rule = _clean_rule(candidate)
        if not rule or _is_unsafe_rule(rule):
            continue
        rules.append(
            MemoryRule(
                id=_rule_id(scenario.id, rule),
                rule=rule,
                source_scenario_id=scenario.id,
                tags=tags,
                confidence=confidence,
                created_at=timestamp,
            )
        )
    return rules


def write_memory_rules(path: str | Path, rules: list[MemoryRule]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"rules": [schema_to_dict(rule) for rule in rules]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _clean_rule(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return text if text.endswith(".") else f"{text}."


def _is_unsafe_rule(rule: str) -> bool:
    lowered = rule.casefold()
    return any(marker in lowered for marker in UNSAFE_RULE_MARKERS)


def _confidence(score: CriticScore) -> float:
    values = [
        score.safety,
        score.clarity,
        score.empathy,
        score.consent,
        score.humility,
        score.usefulness,
        score.reversibility,
    ]
    return round(min(values) / 10.0, 2)


def _rule_id(scenario_id: str, rule: str) -> str:
    digest = hashlib.sha256(f"{scenario_id}:{rule}".encode("utf-8")).hexdigest()[:12]
    return f"rule_{scenario_id}_{digest}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
