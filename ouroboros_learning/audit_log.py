"""JSONL audit logging for guided learning cycles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_audit_event(path: str | Path, event: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
