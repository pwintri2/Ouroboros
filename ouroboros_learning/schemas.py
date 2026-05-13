"""Data schemas for the guided behavioral apprenticeship loop.

Pydantic is used when it is installed. The fallback dataclasses keep the
package runnable in a minimal Python environment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

try:  # pragma: no cover - both branches are covered by runtime availability.
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    BaseModel = None
    Field = None


if BaseModel is not None:

    class Scenario(BaseModel):
        id: str
        title: str
        user_context: str
        user_message: str
        risk_level: str
        expected_principles: list[str] = Field(default_factory=list)
        forbidden_behaviors: list[str] = Field(default_factory=list)


    class TeacherDemonstration(BaseModel):
        scenario_id: str
        response: str
        action_plan: list[str] = Field(default_factory=list)
        principles_used: list[str] = Field(default_factory=list)


    class LearnerAttempt(BaseModel):
        scenario_id: str
        response: str
        action_plan: list[str] = Field(default_factory=list)
        self_assessment: str = ""


    class CriticScore(BaseModel):
        safety: int
        clarity: int
        empathy: int
        consent: int
        humility: int
        usefulness: int
        reversibility: int
        red_flags: list[str] = Field(default_factory=list)
        required_fixes: list[str] = Field(default_factory=list)
        pass_fail: str


    class Reflection(BaseModel):
        scenario_id: str
        what_worked: list[str] = Field(default_factory=list)
        what_failed: list[str] = Field(default_factory=list)
        improved_response: str
        distilled_rule_candidates: list[str] = Field(default_factory=list)


    class MemoryRule(BaseModel):
        id: str
        rule: str
        source_scenario_id: str
        tags: list[str] = Field(default_factory=list)
        confidence: float
        created_at: str

else:

    @dataclass
    class Scenario:
        id: str
        title: str
        user_context: str
        user_message: str
        risk_level: str
        expected_principles: list[str] = field(default_factory=list)
        forbidden_behaviors: list[str] = field(default_factory=list)


    @dataclass
    class TeacherDemonstration:
        scenario_id: str
        response: str
        action_plan: list[str] = field(default_factory=list)
        principles_used: list[str] = field(default_factory=list)


    @dataclass
    class LearnerAttempt:
        scenario_id: str
        response: str
        action_plan: list[str] = field(default_factory=list)
        self_assessment: str = ""


    @dataclass
    class CriticScore:
        safety: int
        clarity: int
        empathy: int
        consent: int
        humility: int
        usefulness: int
        reversibility: int
        red_flags: list[str] = field(default_factory=list)
        required_fixes: list[str] = field(default_factory=list)
        pass_fail: str = "fail"


    @dataclass
    class Reflection:
        scenario_id: str
        what_worked: list[str] = field(default_factory=list)
        what_failed: list[str] = field(default_factory=list)
        improved_response: str = ""
        distilled_rule_candidates: list[str] = field(default_factory=list)


    @dataclass
    class MemoryRule:
        id: str
        rule: str
        source_scenario_id: str
        tags: list[str] = field(default_factory=list)
        confidence: float = 0.0
        created_at: str = ""


def scenario_from_dict(payload: dict[str, Any]) -> Scenario:
    return Scenario(
        id=_required(payload, "id"),
        title=_required(payload, "title"),
        user_context=_required(payload, "user_context"),
        user_message=_required(payload, "user_message"),
        risk_level=str(payload.get("risk_level") or "medium"),
        expected_principles=_as_list(payload.get("expected_principles")),
        forbidden_behaviors=_as_list(payload.get("forbidden_behaviors")),
    )


def teacher_demonstration_from_dict(payload: dict[str, Any]) -> TeacherDemonstration:
    return TeacherDemonstration(
        scenario_id=_required(payload, "scenario_id"),
        response=_required(payload, "response"),
        action_plan=_as_list(payload.get("action_plan")),
        principles_used=_as_list(payload.get("principles_used")),
    )


def learner_attempt_from_dict(payload: dict[str, Any]) -> LearnerAttempt:
    return LearnerAttempt(
        scenario_id=_required(payload, "scenario_id"),
        response=_required(payload, "response"),
        action_plan=_as_list(payload.get("action_plan")),
        self_assessment=str(payload.get("self_assessment") or ""),
    )


def critic_score_from_dict(payload: dict[str, Any]) -> CriticScore:
    return CriticScore(
        safety=_bounded_int(payload.get("safety")),
        clarity=_bounded_int(payload.get("clarity")),
        empathy=_bounded_int(payload.get("empathy")),
        consent=_bounded_int(payload.get("consent")),
        humility=_bounded_int(payload.get("humility")),
        usefulness=_bounded_int(payload.get("usefulness")),
        reversibility=_bounded_int(payload.get("reversibility")),
        red_flags=_as_list(payload.get("red_flags")),
        required_fixes=_as_list(payload.get("required_fixes")),
        pass_fail=str(payload.get("pass_fail") or "fail"),
    )


def schema_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"Unsupported schema object: {type(value)!r}")


def _required(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing required field: {key}")
    return value


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _bounded_int(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        number = 0
    return max(0, min(number, 10))
