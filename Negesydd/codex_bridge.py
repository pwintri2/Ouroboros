"""VSCode Codex detection and lightweight messaging bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import os
import socket
import uuid


class CodexNotDetected(RuntimeError):
    """Raised when Codex cannot be detected."""


@dataclass
class CodexRequest:
    """Request sent to Codex."""

    request_id: str
    prompt: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary."""
        return asdict(self)


class CodexBridge:
    """Detect and communicate with Codex running in VSCode."""

    def __init__(
        self,
        socket_path: str = "/tmp/.vscode_codex_socket",
        outbox_dir: str = "/tmp/negesydd_codex_outbox",
        logger=None,
    ):
        """Initialize bridge paths."""
        self.socket_path = Path(socket_path)
        self.outbox_dir = Path(outbox_dir)
        self.logger = logger
        self.last_request: Optional[CodexRequest] = None

    def is_available(self) -> bool:
        """Return True when Codex/VSCode appears available."""
        return self.socket_path.exists() or bool(os.environ.get("VSCODE_PID")) or os.environ.get("TERM_PROGRAM") == "vscode"

    def detect_codex_vscode(self) -> bool:
        """Compatibility alias for availability detection."""
        return self.is_available()

    def create_request(self, prompt: str, metadata: Optional[Dict[str, Any]] = None) -> CodexRequest:
        """Create a Codex request envelope."""
        return CodexRequest(str(uuid.uuid4()), prompt, dict(metadata or {}))

    def send_request(self, prompt: str, metadata: Optional[Dict[str, Any]] = None, require_available: bool = False) -> CodexRequest:
        """Send a request to Codex via socket if possible, otherwise write to outbox."""
        if require_available and not self.is_available():
            raise CodexNotDetected("Codex VSCode bridge is not available")
        request = self.create_request(prompt, metadata)
        self.last_request = request
        payload = json.dumps(request.to_dict(), sort_keys=True)
        if self.socket_path.exists():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(1)
                    client.connect(str(self.socket_path))
                    client.sendall(payload.encode("utf-8"))
                return request
            except OSError:
                pass
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        (self.outbox_dir / f"{request.request_id}.json").write_text(payload, encoding="utf-8")
        return request

    def capture_output(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Read a response file from the outbox directory if present."""
        response_path = self.outbox_dir / f"{request_id}.response.json"
        if not response_path.exists():
            return None
        return json.loads(response_path.read_text(encoding="utf-8"))

    def get_active_document(self) -> Optional[str]:
        """Return active document path from environment fallback."""
        return os.environ.get("VSCODE_ACTIVE_DOCUMENT")

