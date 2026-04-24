import pytest

from config_parser import PlanConfig
from task_executor import TaskDependencyError, TaskExecutor, TaskStatus


def make_plan():
    return PlanConfig.from_dict(
        {
            "version": "1.0",
            "name": "Plan",
            "description": "Test plan",
            "tasks": [
                {"id": "a", "description": "A", "agent": "goose"},
                {"id": "b", "description": "B", "agent": "goose", "depends_on": ["a"]},
            ],
        }
    )


def test_resolve_order():
    executor = TaskExecutor()
    ordered = executor.resolve_order(list(reversed(make_plan().tasks)))
    assert [task.id for task in ordered] == ["a", "b"]


def test_execute_plan_success():
    calls = []
    executor = TaskExecutor(handlers={"goose": lambda task: calls.append(task.id) or {"ok": task.id}})
    report = executor.execute_plan(make_plan())
    assert report.success
    assert calls == ["a", "b"]
    assert report.results["a"].status is TaskStatus.COMPLETED


def test_cycle_detection():
    plan = PlanConfig.from_dict(
        {
            "version": "1.0",
            "name": "Plan",
            "description": "Cycle",
            "tasks": [
                {"id": "a", "description": "A", "agent": "goose", "depends_on": ["b"]},
                {"id": "b", "description": "B", "agent": "goose", "depends_on": ["a"]},
            ],
        }
    )
    with pytest.raises(TaskDependencyError):
        TaskExecutor().resolve_order(plan.tasks)


def test_execute_parallel_where_possible():
    report = TaskExecutor().execute_parallel_where_possible(make_plan().tasks)
    assert report.success
    assert set(report.results) == {"a", "b"}

