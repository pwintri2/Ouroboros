from datetime import datetime

from agent_pool import Agent, AgentPool, AgentStatus
from llm_core import SubTask, TaskDefinition
from message_queue import MessageQueue
from message_types import Message, MessageType
from messenger import MessengerCore, RoutingResult, create_messenger


class FakeLLM:
    def analyze_prompt(self, text):
        return TaskDefinition(
            task_name="Fake Task",
            subtasks=[SubTask(agent="goose", instruction=text, task_id="task_1")],
            critical_path=["task_1"],
        )

    def route_to_best_agent(self, task):
        return "goose"


def make_pool():
    pool = AgentPool()
    pool.add_agent(
        Agent(
            agent_id="goose",
            name="Goose",
            status=AgentStatus.IDLE,
            last_heartbeat=datetime.now(),
            uptime_seconds=10,
            capability_tags=["execute"],
        )
    )
    return pool


def test_messenger_init():
    messenger = create_messenger()

    assert isinstance(messenger, MessengerCore)
    assert isinstance(messenger.message_queue, MessageQueue)


def test_route_message_queues_message_and_updates_agent():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())

    result = messenger.route_message("gemini_cli", "goose", {"text": "hello"})

    assert isinstance(result, RoutingResult)
    assert result.success
    assert messenger.message_queue.size() == 1
    assert messenger.get_agent_status("goose") is AgentStatus.PROCESSING
    assert messenger.get_message_history()[0].message_id == result.message_id


def test_process_next_message_emits_delivery_event():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())
    messenger.route_message("gemini_cli", "goose", {"text": "hello"})

    message = messenger.process_next_message(timeout=1)

    assert message.destination == "goose"
    assert messenger.execution_timeline[-1].event_type == "message_delivered"


def test_queue_prompt_uses_llm_and_returns_task_id():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())

    task_id = messenger.queue_prompt("Run validation", context={"session_id": "s1"})

    message = messenger.process_next_message(timeout=1)
    assert task_id.startswith("task_")
    assert message.destination == "goose"
    assert message.context["task_id"] == task_id
    assert message.content["task_definition"]["task_name"] == "Fake Task"


def test_event_handler_receives_events():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())
    received = []

    messenger.register_event_handler("message_routed", received.append)
    messenger.route_message("src", "goose", {"text": "x"})

    assert len(received) == 1
    assert received[0].payload["destination"] == "goose"


def test_sync_execution_timeline():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())
    messenger.emit_event("system_ready", {"ok": True})

    timeline = messenger.sync_execution_timeline()

    assert timeline[0]["event_type"] == "system_ready"
    assert timeline[0]["payload"] == {"ok": True}


def test_detect_codex_vscode_from_agent_pool():
    pool = make_pool()
    pool.add_agent(
        Agent(
            agent_id="codex_vscode",
            name="Codex",
            status=AgentStatus.IDLE,
            last_heartbeat=datetime.now(),
            uptime_seconds=1,
        )
    )

    assert MessengerCore(agent_pool=pool, llm_core=FakeLLM()).detect_codex_vscode()


def test_complete_message_sets_agent_idle():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())
    messenger.route_message("src", "goose", {"text": "x"})
    message = messenger.process_next_message(timeout=1)

    messenger.complete_message(message)

    assert messenger.get_agent_status("goose") is AgentStatus.IDLE
    assert messenger.execution_timeline[-1].event_type == "message_completed"


def test_route_message_failure_records_error():
    full_queue = MessageQueue(max_size=1)
    full_queue.put(Message.create("src", "goose", MessageType.PROMPT, {"text": "first"}))
    messenger = MessengerCore(
        agent_pool=make_pool(),
        message_queue=full_queue,
        llm_core=FakeLLM(),
    )

    result = messenger.route_message("src", "goose", {"text": "x"})

    assert not result.success
    assert result.status == "failed"
    assert messenger.error_handler.get_errors(component="messenger")


def test_route_message_accepts_existing_message():
    messenger = MessengerCore(agent_pool=make_pool(), llm_core=FakeLLM())
    message = Message.create("src", "goose", MessageType.STATUS, {"ok": True})

    result = messenger.route_message(
        "ignored",
        "ignored",
        payload=message,
    )

    assert result.success
    assert result.source == "src"
    assert result.destination == "goose"
