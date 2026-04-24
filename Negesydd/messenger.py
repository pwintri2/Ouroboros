"""Core message routing and orchestration for Negesydd."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import os
import uuid

from agent_pool import Agent, AgentPool, AgentStatus
from error_handler import ErrorHandler, ErrorSeverity
from llm_core import LLMCore, TaskDefinition
from message_queue import MessageQueue
from message_types import Message, MessageType, Priority


@dataclass
class RoutingResult:
    """Result returned after a routing operation."""

    success: bool
    message_id: str
    source: str
    destination: str
    status: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the routing result to a dictionary."""
        return asdict(self)


@dataclass
class MessengerEvent:
    """Event emitted by the messenger for dashboards or observers."""

    event_type: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, event_type: str, payload: Optional[Dict[str, Any]] = None) -> "MessengerEvent":
        """Create a timestamped event."""
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=dict(payload or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary."""
        return asdict(self)


class MessengerCore:
    """
    Core message router for Negesydd.

    Responsibilities:
    - Agent discovery
    - Message envelope routing
    - Prompt queueing and LLM task decomposition
    - Execution timeline tracking
    - Event broadcasting for dashboard integrations
    """

    def __init__(
        self,
        logger=None,
        agent_pool: Optional[AgentPool] = None,
        message_queue: Optional[MessageQueue] = None,
        llm_core: Optional[LLMCore] = None,
        error_handler: Optional[ErrorHandler] = None,
    ):
        """Initialize the messenger and its collaborating services."""
        self.logger = logger
        self.agent_pool = agent_pool or AgentPool(logger=logger)
        self.message_queue = message_queue or MessageQueue(logger=logger)
        self.llm_core = llm_core or LLMCore(logger=logger)
        self.error_handler = error_handler or ErrorHandler(
            logger=logger,
            message_queue=self.message_queue,
        )
        self.execution_timeline: List[MessengerEvent] = []
        self.message_history: List[Message] = []
        self._event_handlers: Dict[str, List[Callable[[MessengerEvent], None]]] = {}

    def discover_agents(self) -> List[Agent]:
        """Discover available agents and emit a discovery event."""
        agents = self.agent_pool.discover_agents()
        self.emit_event(
            "agents_discovered",
            {"count": len(agents), "agents": [agent.to_dict() for agent in agents]},
        )
        return agents

    def route_message(
        self,
        source: str,
        destination: str,
        payload: Dict[str, Any] | Message,
        message_type: MessageType = MessageType.PROMPT,
        priority: Priority = Priority.NORMAL,
        context: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RoutingResult:
        """Route a message from source to destination through the message queue."""
        try:
            message = payload if isinstance(payload, Message) else Message.create(
                source=source,
                destination=destination,
                message_type=message_type,
                content=dict(payload),
                priority=priority,
                context=context,
                metadata=metadata,
            )
            queued = self.message_queue.put(message, block=False)
            if not queued:
                raise RuntimeError("Message queue is full")

            self.message_history.append(message)
            self._mark_destination_processing(destination)
            self.emit_event(
                "message_routed",
                {
                    "message_id": message.message_id,
                    "source": message.source,
                    "destination": message.destination,
                    "message_type": message.message_type.value,
                    "priority": message.priority.value,
                },
            )
            return RoutingResult(
                success=True,
                message_id=message.message_id,
                source=message.source,
                destination=message.destination,
                status="queued",
            )
        except Exception as exc:
            self.error_handler.handle_exception(
                exc,
                component="messenger",
                message="Failed to route message",
                severity=ErrorSeverity.HIGH,
                context={"source": source, "destination": destination},
            )
            self.emit_event(
                "routing_failed",
                {"source": source, "destination": destination, "error": str(exc)},
            )
            return RoutingResult(
                success=False,
                message_id="",
                source=source,
                destination=destination,
                status="failed",
                error=str(exc),
            )

    def detect_codex_vscode(self) -> bool:
        """Detect whether Codex in VSCode appears to be available."""
        if self.agent_pool.get_agent("codex_vscode") is not None:
            return True
        if os.environ.get("VSCODE_PID") or os.environ.get("TERM_PROGRAM") == "vscode":
            return True
        return Path("/tmp/.vscode_codex_socket").exists()

    def sync_execution_timeline(self) -> List[Dict[str, Any]]:
        """Return the current execution timeline as dictionaries."""
        return [event.to_dict() for event in self.execution_timeline]

    def queue_prompt(
        self,
        prompt_text: str,
        source: str = "gemini_cli",
        destination: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
    ) -> str:
        """Analyze and queue a prompt, returning the created task id."""
        task_id = (context or {}).get("task_id") or f"task_{uuid.uuid4().hex[:12]}"
        task_definition = self.llm_core.analyze_prompt(prompt_text)
        target = destination or self.llm_core.route_to_best_agent(task_definition)
        prompt_context = dict(context or {})
        prompt_context["task_id"] = task_id

        result = self.route_message(
            source=source,
            destination=target,
            payload={
                "text": prompt_text,
                "task_definition": task_definition.to_dict(),
            },
            message_type=MessageType.PROMPT,
            priority=Priority.NORMAL,
            context=prompt_context,
        )
        if not result.success:
            raise RuntimeError(result.error or "Prompt could not be queued")
        self.emit_event(
            "prompt_queued",
            {"task_id": task_id, "message_id": result.message_id, "destination": target},
        )
        return task_id

    def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """Return the status of an agent by id."""
        agent = self.agent_pool.get_agent(agent_id)
        return agent.status if agent is not None else None

    def register_event_handler(self, event_type: str, handler: Callable[[MessengerEvent], None]) -> None:
        """Register a callback for messenger events."""
        self._event_handlers.setdefault(event_type, []).append(handler)

    def emit_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> MessengerEvent:
        """Emit an event to the timeline and registered handlers."""
        event = MessengerEvent.create(event_type, payload)
        self.execution_timeline.append(event)
        handlers = list(self._event_handlers.get(event_type, [])) + list(
            self._event_handlers.get("*", [])
        )
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                self.error_handler.handle_exception(
                    exc,
                    component="messenger.events",
                    message=f"Event handler failed for {event_type}",
                    severity=ErrorSeverity.LOW,
                )
        return event

    def process_next_message(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Pop the next queued message and emit a delivery event."""
        message = self.message_queue.get(timeout=timeout)
        if message is None:
            return None
        self.emit_event(
            "message_delivered",
            {"message_id": message.message_id, "destination": message.destination},
        )
        return message

    def complete_message(self, message: Message, status: AgentStatus = AgentStatus.IDLE) -> None:
        """Mark a message destination as complete/idle and emit an event."""
        agent = self.agent_pool.get_agent(message.destination)
        if agent is not None:
            self.agent_pool.update_agent_status(agent.agent_id, status)
        self.emit_event(
            "message_completed",
            {"message_id": message.message_id, "destination": message.destination},
        )

    def get_message_history(self) -> List[Message]:
        """Return routed message history."""
        return list(self.message_history)

    def _mark_destination_processing(self, destination: str) -> None:
        agent = self.agent_pool.get_agent(destination)
        if agent is not None:
            self.agent_pool.update_agent_status(destination, AgentStatus.PROCESSING)


def create_messenger(logger=None) -> MessengerCore:
    """Create a MessengerCore with default collaborators."""
    return MessengerCore(logger=logger)
