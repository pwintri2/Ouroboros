"""Task execution with dependency resolution for Negesydd."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import concurrent.futures
import time

from config_parser import PlanConfig, TaskConfig
from error_handler import ErrorHandler


class TaskStatus(Enum):
    """Execution status for a task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskDependencyError(RuntimeError):
    """Raised when task dependencies are invalid or cyclic."""


class ExecutionTimeout(RuntimeError):
    """Raised when a task exceeds its allowed runtime."""


@dataclass
class TaskResult:
    """Result of executing a single task."""

    task_id: str
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert the result to a dictionary."""
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass
class ExecutionReport:
    """Aggregate report for a plan execution."""

    results: Dict[str, TaskResult] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Return True when no task failed."""
        return all(result.status is not TaskStatus.FAILED for result in self.results.values())

    def to_dict(self) -> Dict[str, Any]:
        """Convert the report to a dictionary."""
        return {"success": self.success, "results": {k: v.to_dict() for k, v in self.results.items()}}


class TaskExecutor:
    """Execute plan tasks sequentially or in dependency-aware batches."""

    def __init__(
        self,
        handlers: Optional[Dict[str, Callable[[TaskConfig], Any]]] = None,
        logger=None,
        error_handler: Optional[ErrorHandler] = None,
    ):
        """Initialize the task executor."""
        self.handlers = handlers or {}
        self.logger = logger
        self.error_handler = error_handler or ErrorHandler(logger=logger)

    def resolve_order(self, tasks: List[TaskConfig]) -> List[TaskConfig]:
        """Return tasks in topological dependency order."""
        task_map = {task.id: task for task in tasks}
        if len(task_map) != len(tasks):
            raise TaskDependencyError("Duplicate task ids are not allowed")

        visiting: Set[str] = set()
        visited: Set[str] = set()
        ordered: List[TaskConfig] = []

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise TaskDependencyError(f"Cyclic dependency detected at {task_id}")
            if task_id not in task_map:
                raise TaskDependencyError(f"Unknown task dependency: {task_id}")
            visiting.add(task_id)
            for dependency in task_map[task_id].depends_on:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)
            ordered.append(task_map[task_id])

        for task in tasks:
            visit(task.id)
        return ordered

    def execute_task(self, task: TaskConfig) -> TaskResult:
        """Execute one task with its registered agent handler."""
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            handler = self.handlers.get(task.agent, self.default_handler)
            output = handler(task)
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.COMPLETED,
                output=output,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=time.monotonic() - started,
            )
        except Exception as exc:
            self.error_handler.handle_exception(exc, component=f"task.{task.id}", message="Task failed")
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=str(exc),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=time.monotonic() - started,
            )

    def execute_plan(self, plan: PlanConfig) -> ExecutionReport:
        """Execute a plan according to its execution mode."""
        if plan.execution.mode == "parallel_where_possible":
            return self.execute_parallel_where_possible(plan.tasks)
        report = ExecutionReport()
        for task in self.resolve_order(plan.tasks):
            if any(report.results.get(dep, TaskResult(dep, TaskStatus.PENDING)).status is TaskStatus.FAILED for dep in task.depends_on):
                if plan.execution.on_failure == "skip_dependent":
                    report.results[task.id] = TaskResult(task.id, TaskStatus.SKIPPED, error="Dependency failed")
                    continue
            result = self.execute_task(task)
            report.results[task.id] = result
            if result.status is TaskStatus.FAILED and plan.execution.on_failure == "halt":
                break
        return report

    def execute_parallel_where_possible(self, tasks: List[TaskConfig]) -> ExecutionReport:
        """Execute ready tasks in parallel batches while respecting dependencies."""
        task_map = {task.id: task for task in tasks}
        remaining = set(task_map)
        completed: Set[str] = set()
        report = ExecutionReport()
        while remaining:
            ready = [task_map[task_id] for task_id in remaining if set(task_map[task_id].depends_on) <= completed]
            if not ready:
                raise TaskDependencyError("No executable tasks found; dependency cycle likely exists")
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(ready)) as pool:
                future_map = {pool.submit(self.execute_task, task): task for task in ready}
                for future in concurrent.futures.as_completed(future_map):
                    task = future_map[future]
                    report.results[task.id] = future.result()
                    remaining.remove(task.id)
                    completed.add(task.id)
        return report

    @staticmethod
    def default_handler(task: TaskConfig) -> Dict[str, Any]:
        """Default no-op handler used when no agent-specific handler is registered."""
        return {"task_id": task.id, "agent": task.agent, "status": "accepted"}

