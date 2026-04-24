"""Structured logging support for Negesydd."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class _ColorFormatter(logging.Formatter):
    """Render JSON log records with a colored prefix for humans."""

    def format(self, record: logging.LogRecord) -> str:
        color = StructuredLogger._COLORS.get(record.levelname, "")
        reset = StructuredLogger._RESET if color else ""
        return f"{color}{record.levelname}{reset} {record.getMessage()}"


class StructuredLogger:
    """
    Structured logging system for Negesydd with JSON output support.

    Features:
    - Multiple log levels (DEBUG, INFO, WARNING, ERROR)
    - JSON-formatted logs for machine parsing
    - File and console output
    - Correlation IDs for request tracing
    - Colored console output for readability
    """

    _COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
    }
    _RESET = "\033[0m"

    def __init__(self, name: str, log_dir: str = "./logs", level: str = "INFO"):
        """Initialize logger with file and console handlers."""
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.correlation_id: Optional[str] = None

        numeric_level = getattr(logging, level.upper(), logging.INFO)
        self.logger = logging.getLogger(f"negesydd.{name}.{id(self)}")
        self.logger.setLevel(numeric_level)
        self.logger.propagate = False

        file_handler = logging.FileHandler(self.log_dir / f"{name}.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        file_handler.setLevel(numeric_level)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(_ColorFormatter())
        console_handler.setLevel(numeric_level)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def debug(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log DEBUG level with optional context."""
        self._log("DEBUG", message, context=context, correlation_id=correlation_id)

    def info(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log INFO level with optional context."""
        self._log("INFO", message, context=context, correlation_id=correlation_id)

    def warning(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log WARNING level with optional context."""
        self._log("WARNING", message, context=context, correlation_id=correlation_id)

    def error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log ERROR level with exception traceback."""
        exception_context = dict(context or {})
        if exception is not None:
            exception_context["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": "".join(
                    traceback.format_exception(type(exception), exception, exception.__traceback__)
                ),
            }
        self._log("ERROR", message, context=exception_context, correlation_id=correlation_id)

    def set_correlation_id(self, correlation_id: str) -> None:
        """Set correlation ID for all subsequent logs in this request."""
        self.correlation_id = correlation_id

    def _log(
        self,
        level: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logger": self.name,
            "level": level,
            "message": message,
            "correlation_id": correlation_id or self.correlation_id,
            "context": context or {},
        }
        json_record = json.dumps(record, default=str, sort_keys=True)
        self.logger.log(getattr(logging, level), json_record)
