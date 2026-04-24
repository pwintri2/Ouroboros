"""Agent discovery and health tracking for Negesydd."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import shutil
import subprocess
import sys
import threading
import time

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in minimal sandbox
    psutil = None


class AgentStatus(Enum):
    """Runtime status for a managed agent."""

    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class Agent:
    """Represents an available agent."""

    agent_id: str
    name: str
    status: AgentStatus
    last_heartbeat: datetime
    uptime_seconds: float
    capability_tags: List[str] = field(default_factory=list)
    version: str = "unknown"
    resource_usage: Dict[str, float] = field(default_factory=dict)

    def is_healthy(self, heartbeat_timeout_seconds: int = 30) -> bool:
        """Check if agent is responding."""
        if self.status is AgentStatus.OFFLINE:
            return False
        return datetime.now() - self.last_heartbeat <= timedelta(seconds=heartbeat_timeout_seconds)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "capability_tags": list(self.capability_tags),
            "version": self.version,
            "resource_usage": dict(self.resource_usage),
        }


class AgentPool:
    """
    Manages discovery, health monitoring, and lifecycle of all agents.

    Discovers gorilla, goose, codex_vscode, and custom agents where available.
    Maintains an agent registry with status tracking.
    """

    _KNOWN_COMMANDS = {
        "gorilla": ["code_execution", "file_ops"],
        "goose": ["automation", "file_ops"],
        "gemini": ["cli", "prompt_input"],
        "codex": ["code_generation", "ide"],
        "code": ["ide", "codex_vscode"],
    }

    def __init__(self, logger=None):
        self.agents: Dict[str, Agent] = {}
        self.logger = logger
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False

    def discover_agents(self) -> List[Agent]:
        """
        Discover available agents by checking PATH, process names, and VSCode/Codex hints.

        Returns: List of discovered Agent objects.
        """
        discovered: List[Agent] = []
        now = datetime.now()

        for command, capabilities in self._KNOWN_COMMANDS.items():
            path = shutil.which(command)
            if path:
                agent_id = "codex_vscode" if command == "code" else command
                discovered.append(
                    Agent(
                        agent_id=agent_id,
                        name=agent_id.replace("_", " ").title(),
                        status=AgentStatus.IDLE,
                        last_heartbeat=now,
                        uptime_seconds=0.0,
                        capability_tags=capabilities,
                        version=self._get_command_version(command),
                    )
                )

        if not discovered:
            discovered.append(
                Agent(
                    agent_id="python_runtime",
                    name="Python Runtime",
                    status=AgentStatus.IDLE,
                    last_heartbeat=now,
                    uptime_seconds=0.0,
                    capability_tags=["system", "python"],
                    version=sys.version.split()[0],
                )
            )

        for agent in discovered:
            self.add_agent(agent)
        return discovered

    def add_agent(self, agent: Agent) -> None:
        """Register an agent in the pool."""
        self.agents[agent.agent_id] = agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID."""
        return self.agents.get(agent_id)

    def get_agents_by_capability(self, capability: str) -> List[Agent]:
        """Filter agents by capability tag."""
        return [agent for agent in self.agents.values() if capability in agent.capability_tags]

    def get_agents_by_status(self, status: AgentStatus) -> List[Agent]:
        """Filter agents by status."""
        return [agent for agent in self.agents.values() if agent.status is status]

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update agent status and refresh heartbeat time."""
        agent = self.agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent_id: {agent_id}")
        agent.status = status
        agent.last_heartbeat = datetime.now()

    def start_health_monitoring(self) -> None:
        """Start background thread for agent health checks."""
        if self._running:
            return
        self._running = True
        self._heartbeat_thread = threading.Thread(target=self._monitor_health, daemon=True)
        self._heartbeat_thread.start()

    def stop_health_monitoring(self) -> None:
        """Stop background monitoring thread."""
        self._running = False
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)
            self._heartbeat_thread = None

    def get_resource_usage(self, agent_id: str) -> Dict[str, float]:
        """Get CPU and memory usage for an agent."""
        agent = self.get_agent(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent_id: {agent_id}")

        if psutil is None:
            usage = {"cpu": 0.0, "memory_mb": 0.0}
        else:
            usage = {"cpu": float(psutil.cpu_percent(interval=0.0)), "memory_mb": 0.0}
            process = psutil.Process()
            usage["memory_mb"] = float(process.memory_info().rss / (1024 * 1024))

        agent.resource_usage = usage
        return usage

    def list_all_agents(self) -> List[Agent]:
        """Return all registered agents."""
        return list(self.agents.values())

    def _monitor_health(self) -> None:
        while self._running:
            for agent in list(self.agents.values()):
                if not agent.is_healthy():
                    agent.status = AgentStatus.OFFLINE
            time.sleep(1)

    @staticmethod
    def _get_command_version(command: str) -> str:
        for args in ([command, "--version"], [command, "version"]):
            try:
                result = subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
            output = (result.stdout or result.stderr).strip().splitlines()
            if output:
                return output[0][:120]
        return "unknown"

