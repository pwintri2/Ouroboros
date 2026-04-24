from message_types import Message, MessageType, Priority


def test_message_creation():
    """Test creating a message with factory method."""
    msg = Message.create(
        source="gemini_cli",
        destination="messenger",
        message_type=MessageType.PROMPT,
        content={"text": "test"},
    )
    assert msg.message_id is not None
    assert msg.timestamp is not None
    assert msg.source == "gemini_cli"


def test_message_json_serialization():
    """Test JSON round-trip."""
    msg = Message.create(
        source="agent_1",
        destination="agent_2",
        message_type=MessageType.RESPONSE,
        content={"result": "success"},
        priority=Priority.HIGH,
    )
    json_str = msg.to_json()
    msg2 = Message.from_json(json_str)
    assert msg.message_id == msg2.message_id
    assert msg.content == msg2.content
    assert msg2.priority is Priority.HIGH


def test_error_message():
    """Test error message handling."""
    msg = Message.create(
        source="agent_1",
        destination="messenger",
        message_type=MessageType.ERROR,
        content={"text": "Failed"},
        error={"error_code": 500, "error_message": "Internal error"},
    )
    assert msg.is_error()


def test_correlation_id_from_context():
    msg = Message.create(
        source="agent_1",
        destination="messenger",
        message_type=MessageType.STATUS,
        content={"state": "ready"},
        context={"correlation_id": "corr-1", "task_id": "task-1"},
    )
    assert msg.get_correlation_id() == "corr-1"

