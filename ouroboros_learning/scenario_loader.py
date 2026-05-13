"""Load scenarios and teacher demonstrations from JSON or simple YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import Scenario, TeacherDemonstration, scenario_from_dict, teacher_demonstration_from_dict


def load_scenario(path: str | Path) -> Scenario:
    payload = _load_structured_file(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Scenario file must contain an object: {path}")
    return scenario_from_dict(payload)


def load_demonstration(path: str | Path) -> TeacherDemonstration:
    payload = _load_structured_file(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Demonstration file must contain an object: {path}")
    return teacher_demonstration_from_dict(payload)


def _load_structured_file(path: str | Path) -> Any:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    suffix = target.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        return _load_yaml(text)
    raise ValueError(f"Unsupported scenario file extension: {target.suffix}")


def _load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore
    except Exception:
        return _parse_simple_yaml(text)
    return yaml.safe_load(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by repository-owned seed scenarios.

    Supported forms are top-level ``key: value`` scalars and top-level lists
    written as:

    ``key:``
    ``  - value``
    """
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if not current_list_key:
                raise ValueError("List item without a parent key in YAML scenario")
            result.setdefault(current_list_key, []).append(_clean_scalar(stripped[2:]))
            continue
        if not line.startswith(" ") and ":" in line:
            key, raw_value = line.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            if not raw_value:
                result[key] = []
                current_list_key = key
            else:
                result[key] = _clean_scalar(raw_value)
                current_list_key = None
            continue
        raise ValueError(f"Unsupported YAML line: {raw_line!r}")
    return result


def _clean_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text
