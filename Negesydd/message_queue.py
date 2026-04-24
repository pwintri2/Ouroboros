"""Thread-safe message queue and routing callbacks for Negesydd."""

from __future__ import annotations

from queue import Empty, Full, PriorityQueue
from threading import Lock
from typing import Callable, List, Optional
import itertools

from message_types import Message, MessageType


class MessageQueue:
    """
    Thread-safe message queue for routing between components.

    Features:
    - FIFO queue with blocking put/get
    - Priority support
    - Callbacks for message delivery events
    - Dead letter queue for failed messages
    """

    def __init__(self, max_size: int = 10000, logger=None):
        self.queue: PriorityQueue = PriorityQueue(maxsize=max_size)
        self.dead_letter_queue: List[Message] = []
        self.logger = logger
        self._lock = Lock()
        self._callbacks: dict[MessageType, list[Callable[[Message], None]]] = {}
        self._counter = itertools.count()

    def put(self, message: Message, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Put message on queue.

        Returns: True if successful, False if queue full and non-blocking.
        """
        item = (-message.priority.value, next(self._counter), message)
        try:
            self.queue.put(item, block=block, timeout=timeout)
        except Full:
            return False
        return True

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Message]:
        """
        Get next message from queue.

        Returns: Message or None if empty and non-blocking.
        """
        try:
            _, _, message = self.queue.get(block=block, timeout=timeout)
        except Empty:
            return None
        self.trigger_callbacks(message)
        return message

    def put_dead_letter(self, message: Message, reason: str) -> None:
        """Move failed message to dead letter queue."""
        if message.metadata is None:
            message.metadata = {}
        message.metadata["dead_letter_reason"] = reason
        with self._lock:
            self.dead_letter_queue.append(message)

    def get_dead_letters(self) -> List[Message]:
        """Retrieve all dead letter messages."""
        with self._lock:
            return list(self.dead_letter_queue)

    def register_callback(self, message_type: MessageType, callback: Callable[[Message], None]) -> None:
        """Register callback for specific message type."""
        with self._lock:
            self._callbacks.setdefault(message_type, []).append(callback)

    def trigger_callbacks(self, message: Message) -> None:
        """Trigger all callbacks for message type."""
        callbacks = list(self._callbacks.get(message.message_type, []))
        for callback in callbacks:
            try:
                callback(message)
            except Exception as exc:
                if self.logger is not None:
                    self.logger.error("Message callback failed", exception=exc)

    def size(self) -> int:
        """Current queue size."""
        return self.queue.qsize()

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()

    def clear(self) -> None:
        """Clear all messages from queue."""
        with self.queue.mutex:
            self.queue.queue.clear()
            self.queue.unfinished_tasks = 0
            self.queue.all_tasks_done.notify_all()
