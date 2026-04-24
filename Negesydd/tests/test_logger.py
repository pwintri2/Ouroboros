import json
from pathlib import Path

from logger import StructuredLogger


def test_logger_init(tmp_path):
    """Test logger initialization."""
    logger = StructuredLogger("test", log_dir=str(tmp_path))
    assert logger is not None
    assert Path(tmp_path, "test.log").exists()


def test_logger_info(tmp_path):
    """Test INFO level logging."""
    logger = StructuredLogger("test", log_dir=str(tmp_path))
    logger.info("Test message", {"key": "value"})

    record = json.loads(Path(tmp_path, "test.log").read_text().splitlines()[-1])
    assert record["message"] == "Test message"
    assert record["context"] == {"key": "value"}
    assert record["level"] == "INFO"


def test_correlation_id(tmp_path):
    """Test correlation ID tracking."""
    logger = StructuredLogger("test", log_dir=str(tmp_path))
    logger.set_correlation_id("test-123")
    logger.info("Message with correlation")

    record = json.loads(Path(tmp_path, "test.log").read_text().splitlines()[-1])
    assert record["correlation_id"] == "test-123"


def test_error_with_exception(tmp_path):
    """Test error logging with exception."""
    logger = StructuredLogger("test", log_dir=str(tmp_path))
    try:
        raise ValueError("Test error")
    except Exception as exc:
        logger.error("Error occurred", exception=exc)

    record = json.loads(Path(tmp_path, "test.log").read_text().splitlines()[-1])
    assert record["level"] == "ERROR"
    assert record["context"]["exception"]["type"] == "ValueError"
    assert "Test error" in record["context"]["exception"]["traceback"]

