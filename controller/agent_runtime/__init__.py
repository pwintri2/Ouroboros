"""Agent runtime for Ouroboros real agent orchestration.

The runtime turns slash-commands into background jobs with persistent state,
event logs, and a lifecycle the cockpit can observe. Phase 1 ships the
fundament: models, store, event log, orchestrator, and a Codex adapter.
"""

from controller.agent_runtime.events import EventLog, append_event, read_events
from controller.agent_runtime.models import (
    AGENT_TYPES,
    JOB_STATUSES,
    JobRecord,
    new_job_id,
    utc_now_iso,
)
from controller.agent_runtime.orchestrator import AgentOrchestrator, get_orchestrator
from controller.agent_runtime.store import JobStore

__all__ = [
    "AGENT_TYPES",
    "AgentOrchestrator",
    "EventLog",
    "JOB_STATUSES",
    "JobRecord",
    "JobStore",
    "append_event",
    "get_orchestrator",
    "new_job_id",
    "read_events",
    "utc_now_iso",
]
