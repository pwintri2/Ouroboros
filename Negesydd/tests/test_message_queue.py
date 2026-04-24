from message_queue import MessageQueue
from message_types import Message, MessageType, Priority


def test_queue_put_get():
    """Test basic put and get."""
    queue = MessageQueue()
    msg = Message.create("source", "dest", MessageType.PROMPT, {"text": "test"})
    queue.put(msg)
    retrieved = queue.get(timeout=1)
    assert retrieved.message_id == msg.message_id


def test_queue_empty():
    """Test empty queue handling."""
    queue = MessageQueue()
    assert queue.is_empty()
    assert queue.size() == 0


def test_dead_letter_queue():
    """Test dead letter queue."""
    queue = MessageQueue()
    msg = Message.create("src", "dst", MessageType.ERROR, {"error": "test"})
    queue.put_dead_letter(msg, "Processing failed")
    dead_letters = queue.get_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0].metadata["dead_letter_reason"] == "Processing failed"


def test_callback_registration():
    """Test message callbacks."""
    queue = MessageQueue()
    callback_called = []

    def test_callback(msg):
        callback_called.append(msg)

    queue.register_callback(MessageType.PROMPT, test_callback)
    msg = Message.create("src", "dst", MessageType.PROMPT, {"text": "test"})
    queue.trigger_callbacks(msg)
    assert len(callback_called) == 1


def test_priority_ordering():
    queue = MessageQueue()
    low = Message.create("src", "dst", MessageType.PROMPT, {"text": "low"}, priority=Priority.LOW)
    high = Message.create("src", "dst", MessageType.PROMPT, {"text": "high"}, priority=Priority.HIGH)
    queue.put(low)
    queue.put(high)
    assert queue.get(timeout=1).message_id == high.message_id
