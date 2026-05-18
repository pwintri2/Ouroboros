"""Repeated tool-call detection inspired by Cline's loop-detection.

The guard tracks per-session counters keyed by tool name + a hash of the
canonicalised arguments. A soft threshold emits a warning (the agent should
self-correct), a hard threshold blocks further repeats. Counters reset when a
different tool/args combination is observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import defaultdict
from typing import Any, Mapping


SOFT_THRESHOLD = 3
HARD_THRESHOLD = 5

_IGNORED_ARG_KEYS = frozenset({"approval", "task_progress", "session_id"})


class LoopGuard:
    """Per-session repeated tool-call detector."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, defaultdict[str, int]] = {}
        self._last_signature: dict[str, str] = {}

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            self._counters.pop(session_id, None)
            self._last_signature.pop(session_id, None)

    def reset_all(self) -> None:
        with self._lock:
            self._counters.clear()
            self._last_signature.clear()

    def evaluate(
        self,
        session_id: str,
        *,
        tool: str,
        args: Mapping[str, Any] | None,
        soft_threshold: int = SOFT_THRESHOLD,
        hard_threshold: int = HARD_THRESHOLD,
    ) -> dict[str, Any]:
        signature = _signature(tool, args)
        soft = max(2, int(soft_threshold or SOFT_THRESHOLD))
        hard = max(soft + 1, int(hard_threshold or HARD_THRESHOLD))
        with self._lock:
            counters = self._counters.setdefault(session_id, defaultdict(int))
            last = self._last_signature.get(session_id)
            if last != signature:
                counters.clear()
            counters[signature] += 1
            self._last_signature[session_id] = signature
            count = counters[signature]
        warning = count >= soft and count < hard
        blocked = count >= hard
        return {
            "tool": str(tool or ""),
            "signature": signature,
            "count": count,
            "soft_threshold": soft,
            "hard_threshold": hard,
            "warning": bool(warning),
            "blocked": bool(blocked),
            "reason": (
                f"Tool {tool} is {count} keer met identieke argumenten gepland; agent moet ander pad kiezen."
                if blocked
                else (
                    f"Tool {tool} herhaalt zich ({count}x); plan zou moeten varieren."
                    if warning
                    else ""
                )
            ),
            "fake_success": False,
        }


_GUARD = LoopGuard()


def evaluate_step(session_id: str, *, tool: str, args: Mapping[str, Any] | None) -> dict[str, Any]:
    if not session_id or not tool:
        return {"tool": str(tool or ""), "count": 0, "warning": False, "blocked": False, "fake_success": False}
    return _GUARD.evaluate(session_id, tool=tool, args=args)


def reset_session(session_id: str) -> None:
    _GUARD.reset_session(session_id)


def reset_all() -> None:
    _GUARD.reset_all()


def thresholds_from_env() -> tuple[int, int]:
    try:
        soft = max(2, int(os.getenv("WINTRIP_AGENTIC_LOOP_SOFT", str(SOFT_THRESHOLD))))
    except ValueError:
        soft = SOFT_THRESHOLD
    try:
        hard = max(soft + 1, int(os.getenv("WINTRIP_AGENTIC_LOOP_HARD", str(HARD_THRESHOLD))))
    except ValueError:
        hard = max(soft + 1, HARD_THRESHOLD)
    return soft, hard


def _signature(tool: str, args: Mapping[str, Any] | None) -> str:
    canonical_args = _canonicalise_args(args or {})
    try:
        text = json.dumps(canonical_args, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        text = str(canonical_args)
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{tool}:{digest}"


def _canonicalise_args(args: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in args.items():
        if str(key).lower() in _IGNORED_ARG_KEYS:
            continue
        clean[str(key)] = _canonicalise_value(value)
    return clean


def _canonicalise_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonicalise_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list):
        return [_canonicalise_value(item) for item in value]
    if isinstance(value, tuple):
        return [_canonicalise_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonicalise_value(item) for item in value)
    return value
