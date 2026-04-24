"""Configuration parsing for Negesydd plan files and extended prompts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import re

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only in minimal host envs
    yaml = None


class ConfigError(ValueError):
    """Raised when a Negesydd configuration is invalid."""


@dataclass
class ExecutionConfig:
    """Execution policy for a Negesydd plan."""

    mode: str = "sequential"
    timeout_total_seconds: int = 3600
    on_failure: str = "halt"
    retry_policy: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate execution settings."""
        valid_modes = {"sequential", "parallel", "parallel_where_possible"}
        valid_failure_modes = {"halt", "continue", "skip_dependent"}
        if self.mode not in valid_modes:
            raise ConfigError(f"Invalid execution mode: {self.mode}")
        if self.on_failure not in valid_failure_modes:
            raise ConfigError(f"Invalid failure policy: {self.on_failure}")
        if self.timeout_total_seconds <= 0:
            raise ConfigError("timeout_total_seconds must be positive")


@dataclass
class TaskConfig:
    """A single task in a Negesydd execution plan."""

    id: str
    description: str
    agent: str
    depends_on: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    name: Optional[str] = None
    priority: str = "normal"
    context_from: Optional[Any] = None
    instructions: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskConfig":
        """Build a task from a dictionary."""
        if not isinstance(data, dict):
            raise ConfigError("Task entries must be mappings")

        missing = [key for key in ("id", "description", "agent") if not data.get(key)]
        if missing:
            raise ConfigError(f"Task missing required field(s): {', '.join(missing)}")

        known = {
            "id",
            "name",
            "description",
            "agent",
            "depends_on",
            "timeout_seconds",
            "priority",
            "context_from",
            "instructions",
        }
        metadata = {key: value for key, value in data.items() if key not in known}

        depends_on = data.get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list):
            raise ConfigError(f"Task {data['id']} depends_on must be a list or string")

        timeout_seconds = int(data.get("timeout_seconds", 300))
        if timeout_seconds <= 0:
            raise ConfigError(f"Task {data['id']} timeout_seconds must be positive")

        return cls(
            id=str(data["id"]),
            name=data.get("name"),
            description=str(data["description"]),
            agent=str(data["agent"]),
            depends_on=[str(item) for item in depends_on],
            timeout_seconds=timeout_seconds,
            priority=str(data.get("priority", "normal")),
            context_from=data.get("context_from"),
            instructions=data.get("instructions"),
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary."""
        return asdict(self)


@dataclass
class PlanConfig:
    """Structured Negesydd plan configuration."""

    version: str
    name: str
    description: str
    agents: Dict[str, List[str]]
    tasks: List[TaskConfig]
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    metadata: Dict[str, Any] = field(default_factory=dict)
    notification: Optional[Dict[str, Any]] = None
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    raw_prompt: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanConfig":
        """Build a plan from a dictionary and validate it."""
        if not isinstance(data, dict):
            raise ConfigError("Configuration must be a mapping")

        missing = [key for key in ("version", "name", "description", "tasks") if key not in data]
        if missing:
            raise ConfigError(f"Configuration missing required field(s): {', '.join(missing)}")

        agents = data.get("agents") or {}
        if not isinstance(agents, dict):
            raise ConfigError("agents must be a mapping")
        normalized_agents = {
            "required": _as_string_list(agents.get("required", []), "agents.required"),
            "optional": _as_string_list(agents.get("optional", []), "agents.optional"),
        }

        tasks_data = data.get("tasks") or []
        if not isinstance(tasks_data, list) or not tasks_data:
            raise ConfigError("tasks must be a non-empty list")

        execution_data = data.get("execution") or {}
        if not isinstance(execution_data, dict):
            raise ConfigError("execution must be a mapping")

        execution = ExecutionConfig(
            mode=str(execution_data.get("mode", "sequential")),
            timeout_total_seconds=int(execution_data.get("timeout_total_seconds", 3600)),
            on_failure=str(execution_data.get("on_failure", "halt")),
            retry_policy=dict(execution_data.get("retry_policy", {})),
        )

        plan = cls(
            version=str(data["version"]),
            name=str(data["name"]),
            description=str(data["description"]),
            agents=normalized_agents,
            tasks=[TaskConfig.from_dict(task) for task in tasks_data],
            execution=execution,
            metadata=dict(data.get("metadata", {})),
            notification=data.get("notification"),
            outputs=list(data.get("outputs", [])),
            raw_prompt=data.get("raw_prompt"),
        )
        plan.validate()
        return plan

    def validate(self) -> None:
        """Validate plan structure and task dependency references."""
        self.execution.validate()
        task_ids = [task.id for task in self.tasks]
        duplicates = {task_id for task_id in task_ids if task_ids.count(task_id) > 1}
        if duplicates:
            raise ConfigError(f"Duplicate task id(s): {', '.join(sorted(duplicates))}")

        known_ids = set(task_ids)
        for task in self.tasks:
            unknown = [dep for dep in task.depends_on if dep not in known_ids]
            if unknown:
                raise ConfigError(
                    f"Task {task.id} references unknown dependency/dependencies: "
                    f"{', '.join(unknown)}"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the plan to a plain dictionary."""
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "agents": self.agents,
            "metadata": self.metadata,
            "execution": asdict(self.execution),
            "tasks": [task.to_dict() for task in self.tasks],
            "notification": self.notification,
            "outputs": self.outputs,
            "raw_prompt": self.raw_prompt,
        }

    def to_json(self) -> str:
        """Serialize the plan to JSON."""
        return json.dumps(self.to_dict(), default=str, sort_keys=True)

    def to_string(self) -> str:
        """Return a readable YAML representation."""
        if yaml is None:
            return json.dumps(self.to_dict(), default=str, indent=2, sort_keys=True)
        return yaml.safe_dump(self.to_dict(), sort_keys=False)


class ConfigParser:
    """Parser for YAML/JSON plan files and extended Negesydd prompts."""

    PLAN_START = "[NEGESYDD_PLAN]"
    CONTEXT_START = "[INITIAL_CONTEXT]"
    STEPS_START = "[STEPS]"
    PLAN_END = "[END_NEGESYDD_PLAN]"

    @classmethod
    def from_file(cls, path: str | Path) -> PlanConfig:
        """Load a plan from a YAML, YML, or JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        text = file_path.read_text(encoding="utf-8")
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            return cls.from_json(text)
        if suffix in {".yaml", ".yml", ""}:
            return cls.from_yaml(text)
        raise ConfigError(f"Unsupported config file extension: {file_path.suffix}")

    @classmethod
    def from_yaml(cls, yaml_text: str) -> PlanConfig:
        """Load a plan from YAML text."""
        if yaml is None:
            raise ConfigError("PyYAML is required to parse YAML configuration files")
        data = yaml.safe_load(yaml_text)
        if data is None:
            raise ConfigError("YAML configuration is empty")
        return PlanConfig.from_dict(data)

    @classmethod
    def from_json(cls, json_text: str) -> PlanConfig:
        """Load a plan from JSON text."""
        return PlanConfig.from_dict(json.loads(json_text))

    @classmethod
    def from_prompt(
        cls,
        prompt: str,
        agents: Optional[List[str]] = None,
        default_agent: str = "codex_vscode",
    ) -> PlanConfig:
        """Parse an extended prompt or wrap plain text as a single-task plan."""
        if cls.PLAN_START not in prompt:
            return cls._plain_prompt_to_plan(prompt, agents=agents, default_agent=default_agent)

        plan_block = cls._extract_between(prompt, cls.PLAN_START, cls.CONTEXT_START)
        context_block = cls._extract_between(prompt, cls.CONTEXT_START, cls.STEPS_START)
        steps_block = cls._extract_between(prompt, cls.STEPS_START, cls.PLAN_END)
        trailing_prompt = prompt.split(cls.PLAN_END, 1)[1].strip() if cls.PLAN_END in prompt else ""

        plan_options = cls._parse_key_values(plan_block)
        required_agents = _split_csv(plan_options.get("agents_required")) or agents or [default_agent]
        optional_agents = _split_csv(plan_options.get("agents_optional"))
        timeout_minutes = int(plan_options.get("timeout_minutes", "60"))
        execution_mode = plan_options.get("execution_mode", "sequential")

        tasks = cls._steps_to_tasks(steps_block, required_agents, default_agent)
        description = context_block.strip() or trailing_prompt or "Prompt-based Negesydd plan"
        if trailing_prompt:
            description = f"{description}\n\n{trailing_prompt}".strip()

        return PlanConfig.from_dict(
            {
                "version": "1.0",
                "name": plan_options.get("name", "Prompt Plan"),
                "description": description,
                "agents": {"required": required_agents, "optional": optional_agents},
                "execution": {
                    "mode": execution_mode,
                    "timeout_total_seconds": timeout_minutes * 60,
                    "on_failure": plan_options.get("on_failure", "halt"),
                },
                "tasks": tasks,
                "raw_prompt": prompt,
            }
        )

    @classmethod
    def parse_file(cls, path: str | Path) -> PlanConfig:
        """Compatibility alias for from_file."""
        return cls.from_file(path)

    @classmethod
    def parse_prompt(cls, prompt: str, agents: Optional[List[str]] = None) -> PlanConfig:
        """Compatibility alias for from_prompt."""
        return cls.from_prompt(prompt, agents=agents)

    @staticmethod
    def _extract_between(text: str, start: str, end: str) -> str:
        if start not in text:
            return ""
        after_start = text.split(start, 1)[1]
        if end not in after_start:
            return after_start.strip()
        return after_start.split(end, 1)[0].strip()

    @staticmethod
    def _parse_key_values(text: str) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for line in text.splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or ":" not in clean:
                continue
            key, value = clean.split(":", 1)
            values[key.strip()] = value.strip()
        return values

    @classmethod
    def _plain_prompt_to_plan(
        cls,
        prompt: str,
        agents: Optional[List[str]],
        default_agent: str,
    ) -> PlanConfig:
        selected_agents = agents or [default_agent]
        primary_agent = selected_agents[0]
        return PlanConfig.from_dict(
            {
                "version": "1.0",
                "name": "Direct Prompt",
                "description": prompt.strip() or "Direct prompt",
                "agents": {"required": selected_agents, "optional": []},
                "execution": {
                    "mode": "sequential",
                    "timeout_total_seconds": 3600,
                    "on_failure": "halt",
                },
                "tasks": [
                    {
                        "id": "task_1",
                        "description": prompt.strip() or "Execute direct prompt",
                        "agent": primary_agent,
                        "depends_on": [],
                        "timeout_seconds": 300,
                        "instructions": prompt.strip(),
                    }
                ],
                "raw_prompt": prompt,
            }
        )

    @staticmethod
    def _steps_to_tasks(
        steps_block: str,
        required_agents: List[str],
        default_agent: str,
    ) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        agent_cycle = required_agents or [default_agent]

        for index, line in enumerate(steps_block.splitlines(), start=1):
            clean = line.strip()
            if not clean:
                continue
            clean = re.sub(r"^\d+[\.)]\s*", "", clean)
            agent = _infer_agent(clean, agent_cycle, index - 1)
            task_id = f"task_{len(tasks) + 1}"
            depends_on = [tasks[-1]["id"]] if tasks else []
            tasks.append(
                {
                    "id": task_id,
                    "description": clean,
                    "agent": agent,
                    "depends_on": depends_on,
                    "timeout_seconds": 300,
                    "instructions": clean,
                }
            )

        if not tasks:
            tasks.append(
                {
                    "id": "task_1",
                    "description": "Execute prompt",
                    "agent": agent_cycle[0],
                    "depends_on": [],
                    "timeout_seconds": 300,
                }
            )
        return tasks


def _as_string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ConfigError(f"{field_name} must be a list or string")


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _infer_agent(text: str, fallback_agents: List[str], index: int) -> str:
    lower = text.lower()
    for agent in fallback_agents:
        if agent.lower() in lower:
            return agent
    if "codex" in lower:
        return "codex_vscode"
    if "gorilla" in lower:
        return "gorilla"
    if "goose" in lower:
        return "goose"
    return fallback_agents[index % len(fallback_agents)]


def load_config(path: str | Path) -> PlanConfig:
    """Load a Negesydd configuration file."""
    return ConfigParser.from_file(path)
