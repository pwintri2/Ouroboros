"""Startup and shutdown orchestration for Negesydd."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from config_parser import ConfigParser, PlanConfig
from message_types import LifecycleEvent
from messenger import MessengerCore
from task_executor import ExecutionReport, TaskExecutor


class LifecycleState(Enum):
    """Lifecycle state for the Negesydd runtime."""

    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


@dataclass
class LifecycleRecord:
    """Recorded lifecycle transition."""

    event: LifecycleEvent
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)


class LifecycleManager:
    """Coordinate Negesydd startup, plan execution, and graceful shutdown."""

    def __init__(
        self,
        messenger: Optional[MessengerCore] = None,
        task_executor: Optional[TaskExecutor] = None,
        logger=None,
    ):
        """Initialize the lifecycle manager."""
        self.messenger = messenger or MessengerCore(logger=logger)
        self.task_executor = task_executor or TaskExecutor(logger=logger)
        self.logger = logger
        self.state = LifecycleState.NEW
        self.records: List[LifecycleRecord] = []
        self.config: Optional[PlanConfig] = None

    def load_config(self, plan_path: Optional[str] = None, prompt: Optional[str] = None) -> PlanConfig:
        """Load a plan from a file or prompt text."""
        if plan_path:
            self.config = ConfigParser.from_file(plan_path)
        elif prompt is not None:
            self.config = ConfigParser.from_prompt(prompt)
        else:
            raise ValueError("plan_path or prompt is required")
        return self.config

    def start(self, config: Optional[PlanConfig] = None) -> None:
        """Run the startup sequence and transition to READY."""
        self.state = LifecycleState.STARTING
        self._record(LifecycleEvent.STARTING)
        if config is not None:
            self.config = config
        self.messenger.discover_agents()
        self.messenger.detect_codex_vscode()
        self.state = LifecycleState.READY
        self._record(LifecycleEvent.READY)
        self.messenger.emit_event("system_ready", {"state": self.state.value})

    def execute(self, config: Optional[PlanConfig] = None) -> ExecutionReport:
        """Execute the loaded or provided plan."""
        if config is not None:
            self.config = config
        if self.config is None:
            raise ValueError("No lifecycle configuration loaded")
        if self.state is LifecycleState.NEW:
            self.start(self.config)
        self.state = LifecycleState.EXECUTING
        self._record(LifecycleEvent.EXECUTING, {"tasks": len(self.config.tasks)})
        try:
            report = self.task_executor.execute_plan(self.config)
        except Exception as exc:
            self.state = LifecycleState.FAILED
            self._record(LifecycleEvent.FAILED, {"error": str(exc)})
            raise
        self.state = LifecycleState.COMPLETED if report.success else LifecycleState.FAILED
        self._record(LifecycleEvent.COMPLETED if report.success else LifecycleEvent.FAILED, report.to_dict())
        return report

    def shutdown(self) -> None:
        """Gracefully stop background services."""
        self.state = LifecycleState.SHUTTING_DOWN
        self._record(LifecycleEvent.SHUTTING_DOWN)
        self.messenger.agent_pool.stop_health_monitoring()
        self.state = LifecycleState.STOPPED

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Return lifecycle records as dictionaries."""
        return [{"event": record.event.value, "timestamp": record.timestamp, "details": record.details} for record in self.records]

    def _record(self, event: LifecycleEvent, details: Optional[Dict[str, Any]] = None) -> None:
        self.records.append(LifecycleRecord(event, datetime.now(timezone.utc).isoformat(), dict(details or {})))

