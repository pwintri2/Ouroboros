"""LLM integration for Negesydd task analysis and routing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional
import json
import re

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover - minimal host environments
    requests = None


class LLMError(RuntimeError):
    """Raised when an LLM operation fails."""


@dataclass
class SubTask:
    """A single LLM-proposed subtask."""

    agent: str
    instruction: str
    task_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], index: int) -> "SubTask":
        """Create a subtask from an LLM response dictionary."""
        return cls(
            agent=str(data.get("agent", "codex_vscode")),
            instruction=str(data.get("instruction") or data.get("description") or ""),
            task_id=str(data.get("task_id") or data.get("id") or f"task_{index}"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert this subtask to a dictionary."""
        return asdict(self)


@dataclass
class TaskDefinition:
    """Structured task definition produced by the LLM router."""

    task_name: str
    subtasks: List[SubTask]
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    estimated_duration_seconds: int = 300
    critical_path: List[str] = field(default_factory=list)
    raw_response: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], raw_response: Optional[str] = None) -> "TaskDefinition":
        """Create and validate a task definition from parsed JSON."""
        subtasks_data = data.get("subtasks") or []
        if not isinstance(subtasks_data, list) or not subtasks_data:
            raise LLMError("LLM response must include a non-empty subtasks list")

        subtasks = [SubTask.from_dict(item, index + 1) for index, item in enumerate(subtasks_data)]
        dependencies = data.get("dependencies") or {}
        if not isinstance(dependencies, dict):
            raise LLMError("dependencies must be an object")

        return cls(
            task_name=str(data.get("task_name") or data.get("name") or "Untitled Task"),
            subtasks=subtasks,
            dependencies={str(key): [str(item) for item in value] for key, value in dependencies.items()},
            estimated_duration_seconds=int(data.get("estimated_duration_seconds", 300)),
            critical_path=[str(item) for item in data.get("critical_path", [])],
            raw_response=raw_response,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert this task definition to a dictionary."""
        return {
            "task_name": self.task_name,
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
            "dependencies": self.dependencies,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "critical_path": self.critical_path,
            "raw_response": self.raw_response,
        }


class OllamaClient:
    """Small HTTP client for the Ollama API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "deepseek-coder:latest",
        timeout: float = 30.0,
        transport: Optional[Callable[..., Any]] = None,
    ):
        """Initialize the Ollama client."""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.transport = transport or (requests.post if requests is not None else None)

    def list_models(self) -> List[str]:
        """Return model names available from Ollama."""
        if requests is None:
            raise LLMError("requests is required for Ollama HTTP calls")
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(f"Ollama tags request failed: {exc}") from exc
        return [item.get("name", "") for item in response.json().get("models", [])]

    def is_model_available(self, model: Optional[str] = None) -> bool:
        """Return True if the configured model is available."""
        target = model or self.model
        return any(name == target or name.startswith(target.split(":")[0]) for name in self.list_models())

    def generate(self, prompt: str, model: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
        """Generate text from Ollama using the /api/generate endpoint."""
        if self.transport is None:
            raise LLMError("requests is required for Ollama HTTP calls")
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": options or {"temperature": 0.1},
        }
        try:
            response = self.transport(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise LLMError(f"Ollama generate request failed: {exc}") from exc

        data = response.json()
        return str(data.get("response", ""))


class LLMCore:
    """Deepseek-coder backed reasoning core for task routing."""

    DEFAULT_AGENTS = ("gorilla", "goose", "codex_vscode")

    def __init__(
        self,
        model: str = "deepseek-coder:latest",
        base_url: str = "http://localhost:11434",
        logger=None,
        client: Optional[OllamaClient] = None,
    ):
        """Initialize the LLM core."""
        self.model = model
        self.base_url = base_url
        self.logger = logger
        self.client = client or OllamaClient(base_url=base_url, model=model)

    def build_routing_prompt(self, text: str, available_agents: Optional[List[str]] = None) -> str:
        """Build the prompt used to ask the LLM for a task definition."""
        agents = available_agents or list(self.DEFAULT_AGENTS)
        return (
            "You are an intelligent task router. Analyze the user prompt and output "
            "a strict JSON task definition. Do not include markdown.\n\n"
            f"Available agents: {', '.join(agents)}\n\n"
            f"User prompt:\n{text}\n\n"
            "Output strict JSON with this shape:\n"
            "{\n"
            '  "task_name": "...",\n'
            '  "subtasks": [{"agent": "gorilla", "instruction": "..."}],\n'
            '  "dependencies": {"task_2": ["task_1"]},\n'
            '  "estimated_duration_seconds": 300,\n'
            '  "critical_path": ["task_1"]\n'
            "}"
        )

    def analyze_prompt(
        self,
        text: str,
        available_agents: Optional[List[str]] = None,
        use_fallback: bool = True,
    ) -> TaskDefinition:
        """Analyze a user prompt into a structured task definition."""
        prompt = self.build_routing_prompt(text, available_agents)
        try:
            response = self.client.generate(prompt, model=self.model)
            parsed = self.parse_task_response(response)
            parsed.raw_response = response
            return parsed
        except Exception as exc:
            if self.logger is not None:
                self.logger.warning("LLM prompt analysis failed; using fallback", {"error": str(exc)})
            if not use_fallback:
                raise
            return self.fallback_task_definition(text, available_agents)

    def parse_task_response(self, response: str) -> TaskDefinition:
        """Parse and validate a JSON task definition from an LLM response."""
        data = _extract_json_object(response)
        return TaskDefinition.from_dict(data, raw_response=response)

    def route_to_best_agent(
        self,
        task: TaskDefinition | str,
        available_agents: Optional[List[str]] = None,
    ) -> str:
        """Select the best available agent for a task definition or text prompt."""
        agents = available_agents or list(self.DEFAULT_AGENTS)
        text = task if isinstance(task, str) else " ".join(sub.instruction for sub in task.subtasks)
        lower = text.lower()

        scored = {agent: 0 for agent in agents}
        for agent in agents:
            agent_lower = agent.lower()
            if agent_lower in lower:
                scored[agent] += 5
            if "codex" in agent_lower and any(word in lower for word in ("code", "implement", "generate")):
                scored[agent] += 3
            if "gorilla" in agent_lower and any(word in lower for word in ("analyze", "plan", "design")):
                scored[agent] += 3
            if "goose" in agent_lower and any(word in lower for word in ("run", "execute", "test", "validate")):
                scored[agent] += 3

        return max(agents, key=lambda agent: scored[agent])

    def summarize_results(self, execution_log: List[Dict[str, Any]], use_llm: bool = False) -> str:
        """Summarize execution results for terminal or dashboard display."""
        if not execution_log:
            return "No execution events recorded."

        if use_llm:
            prompt = "Summarize these Negesydd execution events:\n" + json.dumps(
                execution_log, default=str, indent=2
            )
            try:
                return self.client.generate(prompt, model=self.model)
            except LLMError:
                pass

        total = len(execution_log)
        failed = [event for event in execution_log if str(event.get("status", "")).lower() in {"failed", "error"}]
        completed = [
            event for event in execution_log if str(event.get("status", "")).lower() in {"completed", "success"}
        ]
        return (
            f"Execution summary: {total} event(s), {len(completed)} completed, "
            f"{len(failed)} failed."
        )

    def count_tokens(self, text: str) -> int:
        """Estimate token count with a conservative whitespace/punctuation split."""
        return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))

    def validate_response(self, response: str) -> bool:
        """Return True if a response can be parsed as a task definition."""
        try:
            self.parse_task_response(response)
        except Exception:
            return False
        return True

    def test_connection(self) -> bool:
        """Return True if Ollama is reachable and the configured model is available."""
        return self.client.is_model_available(self.model)

    def fallback_task_definition(
        self,
        text: str,
        available_agents: Optional[List[str]] = None,
    ) -> TaskDefinition:
        """Create a deterministic task definition without calling the LLM."""
        agents = available_agents or list(self.DEFAULT_AGENTS)
        agent = self.route_to_best_agent(text, agents)
        return TaskDefinition(
            task_name=_make_task_name(text),
            subtasks=[SubTask(agent=agent, instruction=text.strip() or "Execute task", task_id="task_1")],
            dependencies={},
            estimated_duration_seconds=300,
            critical_path=["task_1"],
        )


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMError("LLM response did not contain a JSON object")
        data = json.loads(stripped[start : end + 1])

    if not isinstance(data, dict):
        raise LLMError("LLM response JSON must be an object")
    return data


def _make_task_name(text: str) -> str:
    words = re.findall(r"\w+", text)
    if not words:
        return "Direct Task"
    return " ".join(words[:6]).title()


_default_core: Optional[LLMCore] = None


def _core() -> LLMCore:
    global _default_core
    if _default_core is None:
        _default_core = LLMCore()
    return _default_core


def analyze_prompt(text: str) -> TaskDefinition:
    """Analyze a prompt using the default LLM core."""
    return _core().analyze_prompt(text)


def route_to_best_agent(task: TaskDefinition | str) -> str:
    """Route a task using the default LLM core."""
    return _core().route_to_best_agent(task)


def summarize_results(execution_log: List[Dict[str, Any]]) -> str:
    """Summarize execution results using the default LLM core."""
    return _core().summarize_results(execution_log)


def test_connection() -> bool:
    """Check whether the default LLM core can reach Ollama."""
    return _core().test_connection()


def test_deepseek_connection() -> bool:
    """Compatibility alias for checking deepseek-coder availability."""
    return test_connection()
