"""Message envelope types for Negesydd."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import json
import uuid


class MessageType(Enum):
    """Supported message categories."""

    PROMPT = "prompt"
    RESPONSE = "response"
    STATUS = "status"
    ERROR = "error"
    LIFECYCLE = "lifecycle"
    DISCOVERY = "discovery"
    HEARTBEAT = "heartbeat"


class Priority(Enum):
    """Message priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class LifecycleEvent(Enum):
    """Lifecycle event names emitted by components."""

    STARTING = "starting"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class Message:
    """Standard message envelope for all inter-component communication."""

    message_id: str
    timestamp: str
    source: str
    destination: str
    message_type: MessageType
    priority: Priority
    content: Dict[str, Any]
    context: Optional[Dict[str, str]] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def create(
        cls,
        source: str,
        destination: str,
        message_type: MessageType,
        content: Dict[str, Any],
        priority: Priority = Priority.NORMAL,
        context: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """Factory method to create a message with auto-generated ID and timestamp."""
        return cls(
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            destination=destination,
            message_type=cls._coerce_message_type(message_type),
            priority=cls._coerce_priority(priority),
            content=dict(content),
            context=dict(context) if context is not None else None,
            error=dict(error) if error is not None else None,
            metadata=dict(metadata) if metadata is not None else None,
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        payload = asdict(self)
        payload["message_type"] = self.message_type.value
        payload["priority"] = self.priority.value
        return json.dumps(payload, default=str, sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Deserialize from JSON string."""
        payload = json.loads(json_str)
        payload["message_type"] = cls._coerce_message_type(payload["message_type"])
        payload["priority"] = cls._coerce_priority(payload["priority"])
        return cls(**payload)

    def is_error(self) -> bool:
        """Check if message indicates an error state."""
        return self.message_type is MessageType.ERROR or self.error is not None

    def get_correlation_id(self) -> Optional[str]:
        """Extract correlation ID from context if present."""
        if not self.context:
            return None
        return self.context.get("correlation_id") or self.context.get("task_id")

    @staticmethod
    def _coerce_message_type(value: MessageType | str) -> MessageType:
        if isinstance(value, MessageType):
            return value
        return MessageType(value)

    @staticmethod
    def _coerce_priority(value: Priority | int | str) -> Priority:
        if isinstance(value, Priority):
            return value
        if isinstance(value, int):
            return Priority(value)
        try:
            return Priority(int(value))
        except (TypeError, ValueError):
            return Priority[value.upper()]

