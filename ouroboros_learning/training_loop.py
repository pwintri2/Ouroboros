"""CLI and orchestration for the guided behavioral apprenticeship loop."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_log import append_audit_event
from .critic import evaluate_attempt
from .memory_rules import distill_memory_rules, write_memory_rules
from .model_adapters import load_model_adapter
from .reflector import build_reflection
from .scenario_loader import load_demonstration, load_scenario
from .schemas import schema_to_dict


ARTIFACT_DIRS = ("learner", "critics", "reflections", "memory_rules", "logs")


def run_training_cycle(
    scenario_path: str | Path,
    *,
    output_root: str | Path = ".",
    demonstration_path: str | Path | None = None,
    adapter_name: str = "mock",
) -> dict[str, Any]:
    root = Path(output_root)
    scenario = load_scenario(scenario_path)
    demo_path = Path(demonstration_path) if demonstration_path else _default_demonstration_path(root, scenario.id)
    teacher = load_demonstration(demo_path)
    if teacher.scenario_id != scenario.id:
        raise ValueError(f"Demonstration {demo_path} targets {teacher.scenario_id}, not {scenario.id}")

    adapter = load_model_adapter(adapter_name)
    attempt = adapter.generate_attempt(scenario)
    score = evaluate_attempt(scenario, attempt)
    reflection = build_reflection(scenario, teacher, attempt, score)
    rules = distill_memory_rules(scenario, reflection, score)

    for directory in ARTIFACT_DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)

    paths = {
        "learner": root / "learner" / f"{scenario.id}.json",
        "critic": root / "critics" / f"{scenario.id}.json",
        "reflection": root / "reflections" / f"{scenario.id}.json",
        "memory_rules": root / "memory_rules" / f"{scenario.id}.json",
        "audit_log": root / "logs" / "learning_cycles.jsonl",
    }
    _write_json(paths["learner"], schema_to_dict(attempt))
    _write_json(paths["critic"], schema_to_dict(score))
    _write_json(paths["reflection"], schema_to_dict(reflection))
    write_memory_rules(paths["memory_rules"], rules)

    event = {
        "cycle_id": f"cycle_{uuid.uuid4().hex}",
        "created_at": _utc_now(),
        "status": score.pass_fail,
        "scenario": schema_to_dict(scenario),
        "demonstration": schema_to_dict(teacher),
        "learner_attempt": schema_to_dict(attempt),
        "critic_score": schema_to_dict(score),
        "reflection": schema_to_dict(reflection),
        "memory_rules": [schema_to_dict(rule) for rule in rules],
        "artifacts": {key: str(value) for key, value in paths.items()},
        "runtime_actions": [],
        "external_calls": [],
        "fake_success": False,
    }
    append_audit_event(paths["audit_log"], event)
    return event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one safe guided learning cycle.")
    parser.add_argument("--scenario", required=True, help="Path to a JSON/YAML scenario file.")
    parser.add_argument("--demonstration", help="Optional path to a teacher demonstration JSON/YAML file.")
    parser.add_argument("--output-root", default=".", help="Root for learner/critic/reflection/rule/log artifacts.")
    parser.add_argument("--adapter", default="mock", help="Model adapter to use. Default: mock.")
    args = parser.parse_args(argv)

    event = run_training_cycle(
        args.scenario,
        output_root=args.output_root,
        demonstration_path=args.demonstration,
        adapter_name=args.adapter,
    )
    print(json.dumps(event, ensure_ascii=False, indent=2))
    return 0 if event["status"] == "pass" else 1


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _default_demonstration_path(output_root: Path, scenario_id: str) -> Path:
    candidates = [
        output_root / "demonstrations" / f"{scenario_id}.json",
        Path("demonstrations") / f"{scenario_id}.json",
        Path(__file__).resolve().parents[1] / "demonstrations" / f"{scenario_id}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
