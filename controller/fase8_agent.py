"""Fase 8 agent layer: tool-calling, persistent goals, and async runs."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

from controller.external_capabilities import external_capabilities_status, external_capability_tool_schemas


APPROVAL_PHRASE = "Akkoord"
MAX_GOAL_CHARS = 12000
MAX_TOOL_ARG_CHARS = 8000


@dataclass
class Fase8Step:
    step_id: str
    title: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "tool": self.tool,
            "args": self.args,
            "status": self.status,
            "result": self.result,
        }


class Fase8Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or _default_store_path()).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def all(self) -> dict[str, Any]:
        with self._lock:
            return self._load()

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self.all().get("tasks", {}).get(task_id)

    def upsert(self, task: dict[str, Any]) -> dict[str, Any]:
        task["updated_at"] = _now_iso()
        with self._lock:
            payload = self._load()
            payload.setdefault("tasks", {})[str(task["task_id"])] = task
            payload["updated_at"] = _now_iso()
            self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return dict(task)

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        tasks = list(self.all().get("tasks", {}).values())
        tasks.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return tasks[: max(1, min(int(limit or 20), 100))]

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"tasks": {}, "updated_at": None}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"tasks": {}, "updated_at": None}
        if not isinstance(payload, dict):
            return {"tasks": {}, "updated_at": None}
        if not isinstance(payload.get("tasks"), dict):
            payload["tasks"] = {}
        return payload


class Fase8ToolDispatcher:
    def __init__(self, agent_tools: Any = None):
        self.agent_tools = agent_tools
        self.last_choice: dict[str, Any] | None = None

    def schemas(self) -> list[dict[str, Any]]:
        schemas = [
            _schema(
                "world_grok_ask",
                "Vraag Grok via de World Agent. Open/submits zijn Akkoord-gated; sessies/CAPTCHA worden niet omzeild.",
                {"question": "string", "approval": "string", "open_tab": "boolean", "submit": "boolean"},
                ["question"],
            ),
            _schema(
                "world_open_url",
                "Open een externe http(s) URL via de cockpit/frontend action.",
                {"url": "string"},
                ["url"],
            ),
            _schema(
                "browser_search",
                "Doe een veilige browser research/search via DuckDuckGo/browser_research.",
                {"query": "string", "approval": "string"},
                ["query"],
            ),
            _schema("memory_search", "Zoek semantisch in het lokale geheugen.", {"query": "string", "limit": "integer"}, ["query"]),
            _schema("run_tests", "Draai een veilige testsuite. Vereist Akkoord.", {"test_selector": "string", "approval": "string"}, ["test_selector"]),
            _schema("safe_shell", "Voer een safe-shell command uit. Vereist Akkoord.", {"command": "string", "approval": "string"}, ["command"]),
            _schema("planner_create", "Decomponeer een goal in persistente uitvoerbare stappen.", {"goal": "string"}, ["goal"]),
        ]
        schemas.extend(external_capability_tool_schemas())
        return schemas

    def choose(self, prompt: str, approval: str = "") -> dict[str, Any]:
        text = _clean_text(prompt)
        lowered = text.lower()
        if re.search(r"\bgrok(?:\.com)?\b", lowered):
            question = _extract_grok_question(text)
            return self._choice("world_grok_ask", {"question": question, "approval": approval, "open_tab": False, "submit": True}, "explicit_grok")
        if re.search(r"\b(open|ga naar|url)\b", lowered) and re.search(r"https?://", text):
            return self._choice("world_open_url", {"url": re.search(r"https?://\S+", text).group(0)}, "explicit_url")
        if re.search(r"\b(zoek online|browser search|web search|zoek op internet)\b", lowered):
            return self._choice("browser_search", {"query": _strip_leading_command(text), "approval": approval}, "browser_search")
        if re.search(r"\b(wat weet|geheugen|memory)\b", lowered):
            return self._choice("memory_search", {"query": _strip_leading_command(text), "limit": 5}, "memory")
        if re.search(r"\b(test|unittest|pytest)\b", lowered):
            return self._choice("run_tests", {"test_selector": "sandbox_tests.test_world_agent sandbox_tests.test_tauri_backend_routes", "approval": approval}, "tests")
        if re.search(r"\b(plan|decompose|opsplits|roadmap|fase 8|fase8)\b", lowered):
            return self._choice("planner_create", {"goal": text}, "planner")
        return self._choice("memory_search", {"query": text or "Ouroboros", "limit": 5}, "safe_default_memory")

    def dispatch(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_tool = str(tool or "").strip()
        payload = _bounded_args(args or {})
        if clean_tool == "world_grok_ask":
            from controller.world_agent import ask_grok_via_world_agent

            return ask_grok_via_world_agent(
                str(payload.get("question") or ""),
                approval=str(payload.get("approval") or ""),
                open_tab=bool(payload.get("open_tab", False)),
                submit=payload.get("submit", True) is not False,
            )
        if clean_tool == "world_open_url":
            url = str(payload.get("url") or "")
            return {
                "status": "success",
                "tool": clean_tool,
                "response": f"Open URL aangevraagd: {url}",
                "frontend_action": {"type": "open_url", "url": url, "target": "_blank", "agent": "fase8"},
                "fake_success": False,
            }
        if clean_tool == "browser_search":
            return _run_agent_tool(self.agent_tools, "browser_research", payload)
        if clean_tool == "memory_search":
            return _run_agent_tool(self.agent_tools, "memory_search", payload)
        if clean_tool == "run_tests":
            return _run_agent_tool(self.agent_tools, "run_tests", payload)
        if clean_tool == "safe_shell":
            return _run_agent_tool(self.agent_tools, "safe_shell", payload)
        if clean_tool == "planner_create":
            return {"status": "success", "tool": clean_tool, "plan": create_plan(str(payload.get("goal") or "")), "fake_success": False}
        if clean_tool == "external_capabilities_status":
            return external_capabilities_status()
        if clean_tool == "agent_runtime_submit":
            return _submit_agent_runtime(payload)
        return {"status": "error", "tool": clean_tool, "reason": f"Onbekende Fase 8 tool: {clean_tool}", "fake_success": False}

    def _choice(self, tool: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
        self.last_choice = {"tool": tool, "args": args, "reason": reason, "chosen_at": _now_iso()}
        return dict(self.last_choice)


class Fase8Runner:
    def __init__(self, store: Fase8Store | None = None, dispatcher: Fase8ToolDispatcher | None = None):
        self.store = store or Fase8Store()
        self.dispatcher = dispatcher or Fase8ToolDispatcher()
        self._stop_flags: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        tasks = self.store.list(limit=12)
        return {
            "status": "online",
            "tasks": tasks,
            "task_count": len(tasks),
            "tools": self.dispatcher.schemas(),
            "tool_schema_count": len(self.dispatcher.schemas()),
            "external_capabilities": external_capabilities_status(),
            "fake_success": False,
        }

    def create_plan(self, goal: str) -> dict[str, Any]:
        return create_plan(goal)

    def run(self, goal: str, *, approval: str = "", max_iterations: int | None = None, continuous: bool = False) -> dict[str, Any]:
        clean_goal = _clean_text(goal)
        if not clean_goal:
            return {"status": "blocked", "reason": "Goal ontbreekt.", "fake_success": False}
        task_id = f"fase8_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        plan = create_plan(clean_goal)
        task = {
            "task_id": task_id,
            "goal": clean_goal,
            "status": "running",
            "running": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "approval": "approved" if str(approval or "").strip() == APPROVAL_PHRASE else "pending",
            "continuous": bool(continuous),
            "max_iterations": max_iterations,
            "current_step": 0,
            "plan": plan,
            "results": [],
            "fake_success": False,
        }
        self.store.upsert(task)
        stop_flag = threading.Event()
        with self._lock:
            self._stop_flags[task_id] = stop_flag
        thread = threading.Thread(
            target=self._run_thread,
            name=f"fase8-task-{task_id}",
            args=(task_id, approval, stop_flag),
            daemon=True,
        )
        thread.start()
        return {"status": "running", "task_id": task_id, "task": task, "background": True, "fake_success": False}

    def stop(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            flag = self._stop_flags.get(task_id)
        if flag is not None:
            flag.set()
        task = self.store.get(task_id)
        if not task:
            return {"status": "not_found", "task_id": task_id, "fake_success": False}
        task.update({"status": "stopping", "running": False, "stop_requested_at": _now_iso()})
        self.store.upsert(task)
        return {"status": "stopping", "task": task, "fake_success": False}

    def get(self, task_id: str) -> dict[str, Any]:
        task = self.store.get(task_id)
        if not task:
            return {"status": "not_found", "task_id": task_id, "fake_success": False}
        return {"status": task.get("status", "unknown"), "task": task, "fake_success": False}

    def _run_thread(self, task_id: str, approval: str, stop_flag: threading.Event) -> None:
        task = self.store.get(task_id)
        if not task:
            return
        steps = list((task.get("plan") or {}).get("steps") or [])
        max_iterations = task.get("max_iterations")
        allowed = len(steps) if not max_iterations else max(1, min(int(max_iterations), 100))
        results: list[dict[str, Any]] = list(task.get("results") or [])
        try:
            for index, step in enumerate(steps[:allowed]):
                if stop_flag.is_set():
                    task.update({"status": "stopped", "running": False, "stopped_at": _now_iso()})
                    self.store.upsert(task)
                    return
                step["status"] = "running"
                task["current_step"] = index + 1
                self.store.upsert(task)
                result = self.dispatcher.dispatch(str(step.get("tool") or ""), dict(step.get("args") or {}) | {"approval": approval})
                ok_statuses = {"success", "opened", "login_required", "rate_limited", "online", "available"}
                step["status"] = "completed" if str(result.get("status")) in ok_statuses else "failed"
                step["result"] = result
                results.append({"step_id": step.get("step_id"), "tool": step.get("tool"), "status": result.get("status"), "result": result})
                task["results"] = results
                task["plan"]["steps"][index] = step
                self.store.upsert(task)
                if step["status"] == "failed":
                    task.update({"status": "failed", "running": False, "finished_at": _now_iso()})
                    self.store.upsert(task)
                    return
            task.update({"status": "completed", "running": False, "finished_at": _now_iso()})
            self.store.upsert(task)
        except Exception as exc:
            task.update({"status": "error", "running": False, "error": str(exc), "finished_at": _now_iso()})
            self.store.upsert(task)


def create_plan(goal: str) -> dict[str, Any]:
    clean_goal = _clean_text(goal)
    steps: list[Fase8Step] = []
    lowered = clean_goal.lower()
    if re.search(r"\bgrok(?:\.com)?\b", lowered):
        steps.append(Fase8Step("step_1", "Vraag Grok via World Agent", "world_grok_ask", {"question": _extract_grok_question(clean_goal), "open_tab": False, "submit": True}))
    if re.search(r"\b(agent|openhands|agents|capabilit|mogelijkheden)\b", lowered):
        steps.append(Fase8Step(f"step_{len(steps)+1}", "Inspecteer AgentS/OpenHands capabilities", "external_capabilities_status", {}))
    if re.search(r"\b(test|verifieer|verify)\b", lowered):
        steps.append(Fase8Step(f"step_{len(steps)+1}", "Draai Fase 8 regressietests", "run_tests", {"test_selector": "sandbox_tests.test_world_agent sandbox_tests.test_tauri_backend_routes"}))
    if not steps:
        steps.append(Fase8Step("step_1", "Zoek lokaal geheugen voor context", "memory_search", {"query": clean_goal, "limit": 5}))
        steps.append(Fase8Step("step_2", "Inspecteer AgentS/OpenHands capabilities", "external_capabilities_status", {}))
    return {
        "goal": clean_goal,
        "created_at": _now_iso(),
        "step_count": len(steps),
        "steps": [step.to_dict() for step in steps],
        "storage": "json",
        "fake_success": False,
    }


_RUNNER: Fase8Runner | None = None
_RUNNER_LOCK = threading.Lock()


def get_fase8_runner(agent_tools: Any = None) -> Fase8Runner:
    global _RUNNER
    with _RUNNER_LOCK:
        if _RUNNER is None:
            _RUNNER = Fase8Runner(dispatcher=Fase8ToolDispatcher(agent_tools=agent_tools))
        elif agent_tools is not None:
            _RUNNER.dispatcher.agent_tools = agent_tools
        return _RUNNER


def _schema(name: str, description: str, props: dict[str, str], required: list[str]) -> dict[str, Any]:
    properties = {key: {"type": value} for key, value in props.items()}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}}


def _run_agent_tool(agent_tools: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if not callable(getattr(agent_tools, "run_tool", None)):
        return {"status": "unavailable", "tool": tool, "reason": "AgentToolRegistry niet beschikbaar.", "fake_success": False}
    return agent_tools.run_tool(tool, args)


def _submit_agent_runtime(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        record = get_orchestrator().submit(str(args.get("agent") or ""), str(args.get("task") or ""))
        return {"status": "running", "job": record.to_dict(), "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


def _extract_grok_question(text: str) -> str:
    from controller.world_agent import detect_world_intent

    intent = detect_world_intent(text)
    if intent is not None and intent.query:
        return intent.query
    return _strip_leading_command(text)


def _strip_leading_command(text: str) -> str:
    return re.sub(r"(?i)^(zoek online naar|zoek op internet naar|browser search|web search|vraag(?: aan)? grok|ask grok)\s*:?\s*", "", text).strip()


def _clean_text(text: object) -> str:
    value = " ".join(str(text or "").replace("\x00", " ").strip().split())
    return value[:MAX_GOAL_CHARS]


def _bounded_args(args: dict[str, Any]) -> dict[str, Any]:
    bounded: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            bounded[str(key)] = value[:MAX_TOOL_ARG_CHARS]
        else:
            bounded[str(key)] = value
    return bounded


def _default_store_path() -> Path:
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/home/pwintri2/WintripAI")
    return workspace / ".secrets" / "fase8_tasks.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
