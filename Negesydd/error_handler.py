"""Error recovery and resilience utilities for Negesydd."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar
import time
import traceback
import uuid

try:
    from message_queue import MessageQueue
    from message_types import Message
except ImportError:  # pragma: no cover - allows isolated import in partial builds
    MessageQueue = Any  # type: ignore
    Message = Any  # type: ignore


T = TypeVar("T")


class ErrorSeverity(Enum):
    """Severity levels for captured errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryAction(Enum):
    """Recovery decisions the handler can return."""

    RETRY = "retry"
    SKIP = "skip"
    HALT = "halt"
    DEAD_LETTER = "dead_letter"


class CircuitState(Enum):
    """State of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryPolicy:
    """Retry policy with exponential backoff."""

    max_retries: int = 3
    base_delay_seconds: float = 0.1
    backoff_factor: float = 2.0
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,)

    def get_delay(self, attempt: int) -> float:
        """Return the delay before retrying an attempt."""
        if attempt <= 0:
            return 0.0
        return self.base_delay_seconds * (self.backoff_factor ** (attempt - 1))

    def can_retry(self, exception: BaseException, attempt: int) -> bool:
        """Return True if an exception should be retried at the given attempt."""
        return attempt < self.max_retries and isinstance(exception, self.retryable_exceptions)


@dataclass
class ErrorRecord:
    """Structured diagnostic record for a handled error."""

    error_id: str
    timestamp: str
    component: str
    message: str
    exception_type: str
    exception_message: str
    severity: ErrorSeverity
    recovery_action: RecoveryAction
    traceback: str
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert this error record to a JSON-serializable dictionary."""
        payload = asdict(self)
        payload["severity"] = self.severity.value
        payload["recovery_action"] = self.recovery_action.value
        return payload


class CircuitBreaker:
    """Simple circuit breaker for protecting unreliable operations."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
        name: str = "default",
    ):
        """Initialize the circuit breaker."""
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be positive")
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED

    def can_execute(self) -> bool:
        """Return True if the protected operation may execute."""
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.HALF_OPEN:
            return True
        if self.last_failure_time is None:
            return True
        if time.monotonic() - self.last_failure_time >= self.recovery_timeout_seconds:
            self.state = CircuitState.HALF_OPEN
            return True
        return False

    def record_success(self) -> None:
        """Reset the circuit after a successful operation."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed operation and open the circuit if needed."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def to_dict(self) -> Dict[str, Any]:
        """Return circuit breaker diagnostics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
        }


class ErrorHandler:
    """Centralized error handling, retry, and recovery coordination."""

    def __init__(
        self,
        logger=None,
        retry_policy: Optional[RetryPolicy] = None,
        message_queue: Optional[MessageQueue] = None,
    ):
        """Initialize the error handler."""
        self.logger = logger
        self.retry_policy = retry_policy or RetryPolicy()
        self.message_queue = message_queue
        self.errors: List[ErrorRecord] = []
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

    def handle_exception(
        self,
        exception: BaseException,
        component: str = "unknown",
        message: str = "Unhandled exception",
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        recovery_action: Optional[RecoveryAction] = None,
    ) -> ErrorRecord:
        """Capture an exception, log it, and return a structured record."""
        action = recovery_action or self._default_action_for_severity(severity)
        record = ErrorRecord(
            error_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            component=component,
            message=message,
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            severity=severity,
            recovery_action=action,
            traceback="".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            ),
            context=dict(context or {}),
        )
        self.errors.append(record)

        if self.logger is not None:
            self.logger.error(
                message,
                exception=exception if isinstance(exception, Exception) else None,
                context=record.to_dict(),
            )
        return record

    def should_retry(self, exception: BaseException, attempt: int) -> bool:
        """Return True if an operation should retry after an exception."""
        return self.retry_policy.can_retry(exception, attempt)

    def execute_with_retry(
        self,
        operation: Callable[[], T],
        component: str = "operation",
        retry_policy: Optional[RetryPolicy] = None,
        sleep: bool = True,
    ) -> T:
        """Execute an operation with retry and exponential backoff."""
        policy = retry_policy or self.retry_policy
        attempt = 0
        while True:
            try:
                return operation()
            except BaseException as exc:
                self.handle_exception(
                    exc,
                    component=component,
                    message=f"{component} failed on attempt {attempt + 1}",
                    recovery_action=RecoveryAction.RETRY
                    if policy.can_retry(exc, attempt)
                    else RecoveryAction.HALT,
                )
                if not policy.can_retry(exc, attempt):
                    raise
                attempt += 1
                delay = policy.get_delay(attempt)
                if sleep and delay > 0:
                    time.sleep(delay)

    def get_circuit_breaker(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> CircuitBreaker:
        """Return a named circuit breaker, creating it if needed."""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout_seconds=recovery_timeout_seconds,
                name=name,
            )
        return self.circuit_breakers[name]

    def execute_with_circuit_breaker(
        self,
        name: str,
        operation: Callable[[], T],
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> T:
        """Execute an operation guarded by a named circuit breaker."""
        breaker = self.get_circuit_breaker(name, failure_threshold, recovery_timeout_seconds)
        if not breaker.can_execute():
            raise RuntimeError(f"Circuit breaker '{name}' is open")

        try:
            result = operation()
        except BaseException:
            breaker.record_failure()
            raise
        breaker.record_success()
        return result

    def move_to_dead_letter(
        self,
        message: Message,
        reason: str,
        queue: Optional[MessageQueue] = None,
    ) -> None:
        """Move a failed message to the configured dead letter queue."""
        target_queue = queue or self.message_queue
        if target_queue is None:
            raise ValueError("A MessageQueue is required for dead letter handling")
        target_queue.put_dead_letter(message, reason)

    def record_error(
        self,
        component: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorRecord:
        """Record a non-exception error condition."""
        return self.handle_exception(
            RuntimeError(message),
            component=component,
            message=message,
            severity=severity,
            context=context,
        )

    def get_errors(
        self,
        severity: Optional[ErrorSeverity] = None,
        component: Optional[str] = None,
    ) -> List[ErrorRecord]:
        """Return stored errors, optionally filtered by severity or component."""
        records = self.errors
        if severity is not None:
            records = [record for record in records if record.severity is severity]
        if component is not None:
            records = [record for record in records if record.component == component]
        return list(records)

    def clear_errors(self) -> None:
        """Clear stored error records."""
        self.errors.clear()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return a diagnostic snapshot for dashboards and logs."""
        by_severity: Dict[str, int] = {severity.value: 0 for severity in ErrorSeverity}
        by_component: Dict[str, int] = {}
        for record in self.errors:
            by_severity[record.severity.value] += 1
            by_component[record.component] = by_component.get(record.component, 0) + 1

        return {
            "total_errors": len(self.errors),
            "by_severity": by_severity,
            "by_component": by_component,
            "circuit_breakers": {
                name: breaker.to_dict() for name, breaker in self.circuit_breakers.items()
            },
        }

    @staticmethod
    def _default_action_for_severity(severity: ErrorSeverity) -> RecoveryAction:
        if severity is ErrorSeverity.LOW:
            return RecoveryAction.SKIP
        if severity is ErrorSeverity.CRITICAL:
            return RecoveryAction.HALT
        return RecoveryAction.RETRY


def retry(
    max_retries: int = 3,
    base_delay_seconds: float = 0.1,
    backoff_factor: float = 2.0,
    sleep: bool = True,
):
    """Decorate a function with ErrorHandler retry behavior."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            handler = ErrorHandler(
                retry_policy=RetryPolicy(
                    max_retries=max_retries,
                    base_delay_seconds=base_delay_seconds,
                    backoff_factor=backoff_factor,
                )
            )
            return handler.execute_with_retry(
                lambda: func(*args, **kwargs),
                component=func.__name__,
                sleep=sleep,
            )

        return wrapper

    return decorator
