"""Job models for the agent runtime.

A `JobRecord` is the canonical state for a single agent job. Status follows
the lifecycle described in BUILDPLAN_OUROBOROS_REAL_AGENT_ORCHESTRATION:

    queued -> planning -> running -> testing -> waiting_for_human -> completed
                                          \\-> failed
                                          \\-> cancelled

Phase 1 only uses queued / running / completed / failed / cancelled, but we
keep the full vocabulary so adapters added in later phases stay compatible.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


AGENT_TYPES: tuple[str, ...] = ("codex", "deepseek", "atlas", "claude", "roo", "ruflo", "grok", "swarm")

JOB_STATUSES: tuple[str, ...] = (
    "queued",
    "planning",
    "running",
    "testing",
    "waiting_for_human",
    "completed",
    "failed",
    "cancelled",
)

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_job_id(agent: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{agent}_{stamp}_{uuid.uuid4().hex[:8]}"


@dataclass
class JobRecord:
    """In-memory representation of an agent job."""

    job_id: str
    agent: str
    task: str
    status: str = "queued"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    workspace_root: str = ""
    allowed_roots: list[str] = field(default_factory=list)
    timeout_seconds: int = 240
    pid: int | None = None
    exit_code: int | None = None
    command: list[str] = field(default_factory=list)
    output_dir: str = ""
    stdout_file: str = ""
    stderr_file: str = ""
    events_file: str = ""
    result_file: str = ""
    output_file: str = ""
    response_preview: str = ""
    changed_files: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    service_actions: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    result_summary: str = ""
    cancel_requested: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobRecord":
        known = {key for key in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        cleaned = {key: value for key, value in payload.items() if key in known}
        if "metadata" not in cleaned:
            cleaned["metadata"] = {}
        # Backwards compatibility / defensive defaults so corrupted records still load.
        cleaned.setdefault("job_id", new_job_id(str(cleaned.get("agent") or "agent")))
        cleaned.setdefault("agent", "codex")
        cleaned.setdefault("task", "")
        cleaned.setdefault("status", "queued")
        return cls(**cleaned)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def touch(self, status: str | None = None) -> None:
        self.updated_at = utc_now_iso()
        if status is not None:
            self.status = status
