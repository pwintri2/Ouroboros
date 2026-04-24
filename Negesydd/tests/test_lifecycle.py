from config_parser import PlanConfig
from lifecycle import LifecycleManager, LifecycleState
from task_executor import TaskExecutor


def make_plan():
    return PlanConfig.from_dict(
        {
            "version": "1.0",
            "name": "Plan",
            "description": "Test plan",
            "tasks": [{"id": "a", "description": "A", "agent": "goose"}],
        }
    )


def test_lifecycle_start_and_shutdown():
    manager = LifecycleManager(task_executor=TaskExecutor())
    manager.start(make_plan())
    assert manager.state is LifecycleState.READY
    assert manager.get_timeline()[0]["event"] == "starting"
    manager.shutdown()
    assert manager.state is LifecycleState.STOPPED


def test_lifecycle_execute_plan():
    manager = LifecycleManager(task_executor=TaskExecutor())
    report = manager.execute(make_plan())
    assert report.success
    assert manager.state is LifecycleState.COMPLETED


def test_lifecycle_load_prompt():
    manager = LifecycleManager()
    config = manager.load_config(prompt="Do work")
    assert config.name == "Direct Prompt"

