import pytest

from error_handler import (
    CircuitBreaker,
    CircuitState,
    ErrorHandler,
    ErrorSeverity,
    RecoveryAction,
    RetryPolicy,
    retry,
)
from message_queue import MessageQueue
from message_types import Message, MessageType


def test_handle_exception_records_error():
    handler = ErrorHandler()

    try:
        raise ValueError("bad input")
    except ValueError as exc:
        record = handler.handle_exception(
            exc,
            component="parser",
            message="Parse failed",
            severity=ErrorSeverity.HIGH,
            context={"task_id": "task_1"},
        )

    assert record.exception_type == "ValueError"
    assert record.recovery_action is RecoveryAction.RETRY
    assert record.context["task_id"] == "task_1"
    assert "bad input" in record.traceback
    assert handler.get_errors(component="parser") == [record]


def test_execute_with_retry_eventually_succeeds_without_sleep():
    attempts = {"count": 0}
    handler = ErrorHandler(retry_policy=RetryPolicy(max_retries=3, base_delay_seconds=0))

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    assert handler.execute_with_retry(flaky, component="flaky", sleep=False) == "ok"
    assert attempts["count"] == 3
    assert len(handler.get_errors()) == 2


def test_execute_with_retry_reraises_after_limit():
    handler = ErrorHandler(retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0))

    with pytest.raises(RuntimeError):
        handler.execute_with_retry(
            lambda: (_ for _ in ()).throw(RuntimeError("still broken")),
            component="worker",
            sleep=False,
        )

    assert len(handler.get_errors()) == 2
    assert handler.get_errors()[-1].recovery_action is RecoveryAction.HALT


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=30)

    assert breaker.can_execute()
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    assert not breaker.can_execute()


def test_circuit_breaker_half_open_after_timeout():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.01)
    breaker.record_failure()
    breaker.last_failure_time -= 1

    assert breaker.can_execute()
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


def test_dead_letter_integration():
    queue = MessageQueue()
    handler = ErrorHandler(message_queue=queue)
    message = Message.create("src", "dst", MessageType.ERROR, {"error": "boom"})

    handler.move_to_dead_letter(message, "failed processing")

    dead_letters = queue.get_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0].metadata["dead_letter_reason"] == "failed processing"


def test_diagnostics_summarize_errors_and_circuits():
    handler = ErrorHandler()
    handler.record_error("agent_pool", "Agent offline", severity=ErrorSeverity.CRITICAL)
    handler.get_circuit_breaker("agent_pool").record_failure()

    diagnostics = handler.get_diagnostics()

    assert diagnostics["total_errors"] == 1
    assert diagnostics["by_severity"]["critical"] == 1
    assert diagnostics["by_component"]["agent_pool"] == 1
    assert diagnostics["circuit_breakers"]["agent_pool"]["failure_count"] == 1


def test_retry_decorator():
    attempts = {"count": 0}

    @retry(max_retries=2, base_delay_seconds=0, sleep=False)
    def flaky():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("again")
        return "done"

    assert flaky() == "done"
    assert attempts["count"] == 2
