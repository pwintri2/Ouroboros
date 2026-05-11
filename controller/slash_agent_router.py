"""Slash-command router for cockpit controlled coding agents.

The cockpit chat remains the human entrypoint. Prompts that start with `/`
are routed to bounded local agent adapters instead of an LLM provider. Codex
and Ruflo/Claude can run on the host through the authenticated host bridge;
Roo uses direct read/list/search adapters for safe inspections and the real
Roo Code CLI as a job for agentic tasks.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.safe_shell import workspace_root

try:
    from controller.ouroboros_self_context import codex_path, get_self_context_status, roo_path, ruflo_path
except Exception:
    def codex_path() -> Path:
        return Path(os.getenv("WINTRIP_CODEX_PATH") or "/home/pwintri2/Codex").expanduser().resolve()

    def roo_path() -> Path:
        return Path(os.getenv("WINTRIP_ROO_CODE_PATH") or os.getenv("WINTRIP_ROO_PATH") or "/home/pwintri2/Roo-code").expanduser().resolve()

    def ruflo_path() -> Path:
        return Path(os.getenv("WINTRIP_RUFLO_PATH") or "/home/pwintri2/ruflo").expanduser().resolve()

    def get_self_context_status() -> dict[str, Any]:
        return {"status": "unavailable", "fake_success": False}


APPROVAL_PHRASE = "Akkoord"
SUPPORTED_COMMANDS = ("agents", "help", "codex", "deepseek", "atlas", "ruflo", "claude", "roo")
HOST_AGENT_COMMANDS = {"codex", "deepseek", "atlas", "ruflo", "claude"}
ECOSYSTEM_AGENT_COMMANDS = {"deepseek", "atlas"}
MAX_TASK_CHARS = 8000
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)
def parse_slash_command(prompt: str) -> dict[str, str] | None:
    text = str(prompt or "").strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text[1:].partition(" ")
    command = head.strip().lower()
    if not command:
        command = "help"
    return {"command": command, "task": rest.strip()}


def slash_command_catalog() -> dict[str, Any]:
    return {
        "status": "online",
        "commands": {
            "/agents": "Toon beschikbare agent-routes en context.",
            "/codex <opdracht>": "Laat Codex CLI in WintripAI werken.",
            "/codex status": "Codex binary, auth en jobs status.",
            "/codex capabilities": "Inventory van Codex subsystemen in de repo.",
            "/codex discovery": "Repo + auth evidence overzicht.",
            "/codex jobs": "Recente codex jobs uit de agent runtime.",
            "/codex version": "Codex CLI version probe.",
            "/codex app-status": "Status van de Codex app-server subsystem.",
            "/codex mcp-status": "Status van de Codex MCP server subsystem.",
            "/codex run <opdracht>": "Expliciete run van een codex taak.",
            "/deepseek status": "DeepSeek CLI/root/runtime status.",
            "/deepseek capabilities": "DeepSeek agentische rollen, docs en CLI-functies.",
            "/deepseek doctor": "DeepSeek doctor --json probe.",
            "/deepseek run <opdracht>": "Laat DeepSeek exec agentisch werken in WintripAI.",
            "/atlas status": "Atlas CLI/root/runtime status.",
            "/atlas capabilities": "Atlas SDD crew, context-pack en CLI-functies.",
            "/atlas doctor": "Atlas doctor probe.",
            "/atlas ask <opdracht>": "Laat Atlas een vraag/taak beantwoorden via de CLI.",
            "/ruflo <opdracht>": "Start Ruflo swarm-coordinatie rond de opdracht.",
            "/claude <opdracht>": "Laat Claude Code in WintripAI werken als auth beschikbaar is.",
            "/roo status": "Roo Code CLI/root/runtime status.",
            "/roo jobs": "Recente Roo jobs uit de agent runtime.",
            "/roo <opdracht>": "Laat Roo Code agentisch werken met het in Cockpit gekozen model.",
        },
        "roots": _agent_roots(),
        "approval_phrase": APPROVAL_PHRASE,
        "preapproved": _approval_effective("") == APPROVAL_PHRASE,
        "fake_success": False,
    }


def handle_slash_command(
    prompt: str,
    approval: str = "",
    timeout_seconds: int = 1800,
    provider: str = "",
    model: str = "",
) -> dict[str, Any] | None:
    parsed = parse_slash_command(prompt)
    if parsed is None:
        return None
    command = parsed["command"]
    task = parsed["task"]
    if command in {"agents", "help", "?"}:
        return {
            **slash_command_catalog(),
            "route": "slash_agent",
            "agent": "catalog",
            "response": _catalog_text(),
        }
    if command not in SUPPORTED_COMMANDS:
        return {
            "status": "error",
            "route": "slash_agent",
            "agent": command,
            "response": f"Onbekend slash-commando: /{command}\n\n{_catalog_text()}",
            "catalog": slash_command_catalog(),
            "fake_success": False,
        }
    if command == "codex":
        codex_sub = _codex_subcommand(task, approval=approval, timeout_seconds=timeout_seconds)
        if codex_sub is not None:
            return codex_sub
    if command in ECOSYSTEM_AGENT_COMMANDS:
        ecosystem_sub = _ecosystem_subcommand(command, task, approval=approval, timeout_seconds=timeout_seconds)
        if ecosystem_sub is not None:
            return ecosystem_sub
    if command == "roo":
        roo_sub = _roo_subcommand(task, approval=approval, provider=provider, model=model, timeout_seconds=timeout_seconds)
        if roo_sub is not None:
            return roo_sub
    if command in HOST_AGENT_COMMANDS and task.lower() in {"status", "jobs", "latest", "laatste"}:
        return _agent_jobs_result(command)
    if not task:
        return {
            "status": "blocked",
            "route": "slash_agent",
            "agent": command,
            "response": f"Geef een opdracht mee, bijvoorbeeld /{command} voeg test toe voor self-context.",
            "catalog": slash_command_catalog(),
            "fake_success": False,
        }
    if command == "roo":
        return execute_roo_agent_task(task=task, approval=approval, provider=provider, model=model, timeout_seconds=timeout_seconds)
    return execute_host_agent_command(
        agent=command,
        task=task,
        approval=approval,
        timeout_seconds=timeout_seconds,
        prefer_bridge=True,
    )


def execute_host_agent_command(
    agent: str,
    task: str,
    approval: str = "",
    timeout_seconds: int = 240,
    prefer_bridge: bool = True,
) -> dict[str, Any]:
    started = time.time()
    agent = str(agent or "").strip().lower()
    task = _clip(str(task or "").strip(), MAX_TASK_CHARS)
    if agent not in HOST_AGENT_COMMANDS:
        return {"status": "error", "agent": agent, "reason": "Unsupported host agent.", "fake_success": False}
    if not task:
        return {"status": "blocked", "agent": agent, "reason": "Task is empty.", "fake_success": False}
    effective_approval = _approval_effective(approval)
    if effective_approval != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "route": "slash_agent",
            "agent": agent,
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "response": f"/{agent} wacht op {APPROVAL_PHRASE}.",
            "fake_success": False,
        }
    bridged = None
    if prefer_bridge:
        bridged = _bridge_agent_command(agent=agent, task=task, approval=effective_approval, timeout_seconds=timeout_seconds)
        if bridged is not None and not bridged.get("transport_error"):
            return bridged
    if agent == "codex":
        return _run_codex_exec(task=task, timeout_seconds=timeout_seconds)
    if agent in ECOSYSTEM_AGENT_COMMANDS:
        return _submit_ecosystem_agent_runtime(
            agent=agent,
            task=task,
            timeout_seconds=timeout_seconds,
            started=started,
            bridge_result=bridged,
            approval=effective_approval,
        )
    if agent == "ruflo":
        if _allow_inline_host_agents():
            return _run_ruflo_swarm(task=task, timeout_seconds=timeout_seconds)
        if _allow_runtime_host_agents():
            return _submit_host_agent_runtime(agent="ruflo", task=task, timeout_seconds=timeout_seconds, started=started)
        return _write_host_agent_handoff(agent="ruflo", task=task, started=started, bridge_result=bridged)
    if agent == "claude":
        if _allow_inline_host_agents():
            return _run_claude_code(task=task, timeout_seconds=timeout_seconds)
        if _allow_runtime_host_agents():
            return _submit_host_agent_runtime(agent="claude", task=task, timeout_seconds=timeout_seconds, started=started)
        return _write_host_agent_handoff(agent="claude", task=task, started=started, bridge_result=bridged)
    return {"status": "error", "agent": agent, "reason": "Agent dispatch failed.", "fake_success": False}


def execute_roo_agent_task(
    task: str,
    approval: str = "",
    provider: str = "",
    model: str = "",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    started = time.time()
    task = _clip(str(task or "").strip(), MAX_TASK_CHARS)
    if not task:
        return {"status": "blocked", "agent": "roo", "reason": "Task is empty.", "fake_success": False}
    lowered = task.lower()
    try:
        from controller import roo_tools

        if lowered.startswith(("read ", "lees ")):
            path = task.split(maxsplit=1)[1].strip()
            result = roo_tools.read_file(path)
            return _agent_result("roo", "roo_read_file", result.get("status", "error"), started, roo_result=result)
        if lowered.startswith(("list ", "ls ")):
            path = task.split(maxsplit=1)[1].strip() if " " in task else "."
            result = roo_tools.list_files(path or ".", recursive=False)
            return _agent_result("roo", "roo_list_files", result.get("status", "error"), started, roo_result=result)
        if lowered.startswith(("search ", "zoek ")):
            remainder = task.split(maxsplit=1)[1].strip() if " " in task else ""
            path, _, regex = remainder.partition(" ")
            result = roo_tools.search_files(path or ".", regex or ".")
            return _agent_result("roo", "roo_search_files", result.get("status", "error"), started, roo_result=result)
        if lowered.startswith(("run: ", "commando: ", "shell: ")):
            command = task.split(":", 1)[1].strip()
            result = roo_tools.execute_command(command, approval=_approval_effective(approval))
            return _agent_result("roo", "roo_execute_command", result.get("status", "error"), started, roo_result=result)
    except Exception as exc:
        return _agent_result("roo", "roo_adapter", "error", started, reason=str(exc))

    effective_approval = _approval_effective(approval)
    if effective_approval != APPROVAL_PHRASE:
        local_llm = _roo_selection_is_local(provider, model)
        return _agent_result(
            "roo",
            "roo_cli",
            "blocked",
            started,
            route="roo_runtime",
            provider="roo",
            model=str(model or ""),
            requested_provider=str(provider or ""),
            local_only=local_llm,
            approval_required=True,
            approval_phrase=APPROVAL_PHRASE,
            blocked_tools=["roo_cli"],
            provenance={
                "blocked_tools": ["roo_cli"],
                "planned_tools": ["roo_cli"],
                "planner_source": "slash_roo_runtime",
            },
            response=(
                f"/roo wacht op exact {APPROVAL_PHRASE}. Roo Code kan bestanden wijzigen en commando's uitvoeren; "
                "de Cockpit-modelkeuze wordt na approval aan de Roo job meegegeven."
            ),
        )
    return _submit_roo_agent_runtime(
        task=task,
        provider=provider,
        model=model,
        approval=effective_approval,
        timeout_seconds=timeout_seconds,
        started=started,
    )


def _run_codex_exec(task: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    timeout_seconds = max(int(timeout_seconds or 0), int(os.getenv("WINTRIP_CODEX_TIMEOUT_SECONDS", "1800") or 1800))
    if not _command_exists("codex"):
        return _agent_result(
            "codex",
            "codex_exec",
            "missing",
            started,
            response=(
                "Codex CLI staat niet in PATH van de backend. "
                "Installeer Codex op de host of voeg het pad toe aan het backend-process, en probeer opnieuw."
            ),
        )
    auth = _codex_login_status()
    if not auth.get("logged_in"):
        return _login_required("codex", started, "https://chatgpt.com/codex")
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        record = orchestrator.submit(
            agent="codex",
            task=task,
            timeout_seconds=int(timeout_seconds or 240),
            metadata={"prompt": _agent_prompt("Codex", task)},
        )
    except Exception as exc:
        return _agent_result("codex", "codex_exec", "error", started, reason=str(exc))
    job_payload = record.to_dict()
    return _agent_result(
        "codex",
        "codex_exec",
        "running",
        started,
        job=job_payload,
        response=(
            f"Codex job {record.job_id} gestart in de agent runtime. "
            "Volg live in Agent Jobs of vraag `/Codex status` voor de laatste samenvatting."
        ),
    )


def _codex_subcommand(task: str, approval: str = "", timeout_seconds: int = 1800) -> dict[str, Any] | None:
    """Handle `/codex <subcommand>` patterns that don't run a free-form task.

    Returns None when the input is a free-form task (delegated to the existing
    runtime path). Returns a result dict for known subcommands.
    """

    text = str(task or "").strip()
    if not text:
        return None
    head, _, rest = text.partition(" ")
    head_lower = head.lower()
    rest = rest.strip()

    if head_lower in {"status", "health"}:
        return _codex_status_subcommand()
    if head_lower in {"capabilities", "caps", "inventory"}:
        return _codex_capabilities_subcommand()
    if head_lower in {"jobs", "latest", "laatste"}:
        return _agent_jobs_result("codex")
    if head_lower in {"discovery", "discover", "evidence"}:
        return _codex_discovery_subcommand()
    if head_lower in {"version", "--version"}:
        return _codex_version_subcommand()
    if head_lower in {"app-status", "app", "app_mode"}:
        return _codex_subsystem_subcommand("app_mode", "App server / app mode")
    if head_lower in {"mcp-status", "mcp"}:
        return _codex_subsystem_subcommand("mcp", "MCP server / client")
    if head_lower == "run":
        if not rest:
            return {
                "status": "blocked",
                "route": "slash_agent",
                "agent": "codex",
                "response": "Geef een opdracht mee, bijvoorbeeld /codex run voeg test toe voor self-context.",
                "fake_success": False,
            }
        return execute_host_agent_command(
            agent="codex",
            task=rest,
            approval=approval,
            timeout_seconds=timeout_seconds,
            prefer_bridge=True,
        )
    return None


def _ecosystem_subcommand(agent: str, task: str, approval: str = "", timeout_seconds: int = 1800) -> dict[str, Any] | None:
    text = str(task or "").strip()
    if not text:
        return None
    head, _, rest = text.partition(" ")
    head_lower = head.lower()
    rest = rest.strip()

    if head_lower in {"status", "health"}:
        return _ecosystem_status_subcommand(agent)
    if head_lower in {"capabilities", "caps", "inventory"}:
        return _ecosystem_capabilities_subcommand(agent)
    if head_lower in {"jobs", "latest", "laatste"}:
        return _agent_jobs_result(agent)
    if head_lower in {"doctor", "diagnostics", "diagnose"}:
        return _ecosystem_doctor_subcommand(agent, timeout_seconds=timeout_seconds)
    if head_lower in {"version", "--version"}:
        return _ecosystem_version_subcommand(agent)
    if head_lower in {"read", "lees", "list", "ls", "search", "zoek"}:
        return _ecosystem_source_subcommand(agent, head_lower, rest)
    run_heads = {"run", "exec"}
    if agent == "atlas":
        run_heads.add("ask")
    if head_lower in run_heads:
        if not rest:
            verb = "ask" if agent == "atlas" else "run"
            return {
                "status": "blocked",
                "route": "slash_agent",
                "agent": agent,
                "response": f"Geef een opdracht mee, bijvoorbeeld /{agent} {verb} vat de agentic status samen.",
                "fake_success": False,
            }
        return execute_host_agent_command(
            agent=agent,
            task=rest,
            approval=approval,
            timeout_seconds=timeout_seconds,
            prefer_bridge=True,
        )
    return None


def _ecosystem_source_subcommand(agent: str, verb: str, rest: str) -> dict[str, Any]:
    started = time.time()
    try:
        root = _ecosystem_source_root(agent)
        if not root.exists():
            return _agent_result(agent, f"{agent}_source", "missing", started, response=f"{agent} root is niet zichtbaar: {root}")
        if verb in {"list", "ls"}:
            target = _resolve_ecosystem_source_path(agent, root, rest or ".")
            if target is None:
                return _agent_result(agent, f"{agent}_source_list", "blocked", started, response="Pad valt buiten de agent-root of lijkt secret-achtig.")
            items = _safe_list_source(target)
            return _agent_result(agent, f"{agent}_source_list", "success", started, response="\n".join(items) + ("\n" if items else ""), root=str(root), path=str(target))
        if verb in {"read", "lees"}:
            target = _resolve_ecosystem_source_path(agent, root, rest or "README.md")
            if target is None or not target.is_file():
                return _agent_result(agent, f"{agent}_source_read", "blocked", started, response="Bestand is niet veilig leesbaar of bestaat niet.")
            text = target.read_text(encoding="utf-8", errors="replace")[:12000]
            return _agent_result(agent, f"{agent}_source_read", "success", started, response=text, root=str(root), path=str(target))
        query_path, _, pattern = str(rest or "").partition(" ")
        target = _resolve_ecosystem_source_path(agent, root, query_path or ".")
        if target is None:
            return _agent_result(agent, f"{agent}_source_search", "blocked", started, response="Pad valt buiten de agent-root of lijkt secret-achtig.")
        pattern = pattern or "."
        matches = _safe_search_source(target, pattern)
        return _agent_result(agent, f"{agent}_source_search", "success", started, response="\n".join(matches) + ("\n" if matches else ""), root=str(root), path=str(target), match_count=len(matches))
    except Exception as exc:
        return _agent_result(agent, f"{agent}_source", "error", started, reason=str(exc)[:500])


def _roo_subcommand(
    task: str,
    approval: str = "",
    provider: str = "",
    model: str = "",
    timeout_seconds: int = 1800,
) -> dict[str, Any] | None:
    text = str(task or "").strip()
    if not text:
        return None
    head, _, rest = text.partition(" ")
    head_lower = head.lower()
    rest = rest.strip()
    if head_lower in {"status", "health"}:
        return _roo_status_subcommand()
    if head_lower in {"jobs", "latest", "laatste"}:
        return _agent_jobs_result("roo")
    if head_lower in {"run", "ask", "code"}:
        if not rest:
            return _agent_result(
                "roo",
                "roo_cli",
                "blocked",
                time.time(),
                response="Geef een opdracht mee, bijvoorbeeld /roo run maak de runtime status zichtbaar.",
            )
        return execute_roo_agent_task(
            task=rest,
            approval=approval,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    return None


def _roo_status_subcommand() -> dict[str, Any]:
    started = time.time()
    try:
        from controller.agent_runtime.adapters.roo_cli import roo_status

        status = roo_status(prefer_bridge=True)
    except Exception as exc:
        return _agent_result("roo", "roo_status", "error", started, reason=str(exc)[:500])
    lines = [
        f"/roo status: {status.get('status')}",
        f"- root: {status.get('root')} (present={status.get('root_exists')})",
        f"- binary: {status.get('binary') or 'n/a'}",
        f"- node: {status.get('node') or 'n/a'}",
        f"- runtime reachable: {status.get('runtime_reachable')}",
        f"- supported providers: {', '.join(list(status.get('supported_cli_providers') or [])[:12]) or '(unknown)'}",
        f"- ollama supported by CLI: {status.get('ollama_cli_supported')}",
    ]
    version_probe = status.get("version_probe") if isinstance(status.get("version_probe"), dict) else {}
    if version_probe.get("stdout"):
        lines.append(f"- version: {str(version_probe.get('stdout')).strip()}")
    if version_probe.get("stderr") and not version_probe.get("stdout"):
        lines.append(f"- version stderr: {str(version_probe.get('stderr')).strip()[:400]}")
    return _agent_result("roo", "roo_status", str(status.get("status") or "unknown"), started, roo_status=status, response="\n".join(lines))


def _ecosystem_status_subcommand(agent: str) -> dict[str, Any]:
    started = time.time()
    try:
        from controller.agent_runtime.adapters.ecosystem_cli import ecosystem_agent_status

        status = ecosystem_agent_status(agent)
    except Exception as exc:
        return _agent_result(agent, f"{agent}_status", "error", started, reason=str(exc)[:500])
    launcher = status.get("launcher") if isinstance(status.get("launcher"), dict) else {}
    version_probe = status.get("version_probe") if isinstance(status.get("version_probe"), dict) else {}
    lines = [
        f"/{agent} status: {status.get('status')}",
        f"- root: {status.get('root')} (present={status.get('root_exists')})",
        f"- runtime reachable: {status.get('runtime_reachable')}",
        f"- launcher: {launcher.get('kind') or 'n/a'} ({launcher.get('path') or 'n/a'})",
        f"- version probe: {version_probe.get('status')} exit={version_probe.get('exit_code')}",
        f"- capabilities: {', '.join(list(status.get('capabilities') or [])[:8]) or '(none)'}",
        f"- reason: {status.get('reason') or ''}",
    ]
    return _agent_result(
        agent,
        f"{agent}_status",
        str(status.get("status") or "unknown"),
        started,
        ecosystem_status=status,
        response="\n".join(lines),
    )


def _ecosystem_capabilities_subcommand(agent: str) -> dict[str, Any]:
    started = time.time()
    try:
        from controller.agent_runtime.adapters.ecosystem_cli import ecosystem_agent_capabilities
        from controller.external_capabilities import external_capabilities_status

        runtime_caps = ecosystem_agent_capabilities(agent)
        external = external_capabilities_status()
    except Exception as exc:
        return _agent_result(agent, f"{agent}_capabilities", "error", started, reason=str(exc)[:500])
    source = ((external.get("capabilities") or {}).get(agent) or {}) if isinstance(external, dict) else {}
    roles = list(source.get("role_taxonomy") or [])
    patterns = list(source.get("agentic_patterns") or [])
    entrypoints = list(runtime_caps.get("entrypoints") or source.get("entrypoints") or [])
    commands = runtime_caps.get("commands") if isinstance(runtime_caps.get("commands"), dict) else {}
    lines = [
        f"/{agent} capabilities: {runtime_caps.get('status')}",
        f"- root: {runtime_caps.get('root') or source.get('root')}",
        f"- entrypoints: {len(entrypoints)}",
        f"- roles: {len(roles)}",
        f"- patterns: {len(patterns)}",
    ]
    for key, command in list(commands.items())[:8]:
        lines.append(f"- {key}: {command}")
    for role in roles[:6]:
        if isinstance(role, dict):
            lines.append(f"- role {role.get('label') or role.get('id')}: {role.get('value')}")
    return _agent_result(
        agent,
        f"{agent}_capabilities",
        "success",
        started,
        ecosystem_capabilities=runtime_caps,
        external_capability=source,
        response="\n".join(lines),
    )


def _ecosystem_doctor_subcommand(agent: str, timeout_seconds: int = 1800) -> dict[str, Any]:
    started = time.time()
    try:
        from controller.agent_runtime.adapters.ecosystem_cli import ecosystem_agent_doctor

        result = ecosystem_agent_doctor(agent, timeout_seconds=min(int(timeout_seconds or 20), 120))
    except Exception as exc:
        return _agent_result(agent, f"{agent}_doctor", "error", started, reason=str(exc)[:500])
    lines = [
        f"/{agent} doctor: {result.get('status')}",
        f"- exit: {result.get('exit_code')}",
        f"- reason: {result.get('reason') or ''}",
    ]
    if result.get("stdout"):
        lines.append(str(result.get("stdout"))[-1600:])
    if result.get("stderr"):
        lines.append(str(result.get("stderr"))[-1600:])
    return _agent_result(
        agent,
        f"{agent}_doctor",
        str(result.get("status") or "unknown"),
        started,
        doctor=result,
        response="\n".join(line for line in lines if line),
    )


def _ecosystem_version_subcommand(agent: str) -> dict[str, Any]:
    status_result = _ecosystem_status_subcommand(agent)
    status_result["tool"] = f"{agent}_version"
    version_probe = (status_result.get("ecosystem_status") or {}).get("version_probe") or {}
    status_result["response"] = (
        f"/{agent} version: {version_probe.get('status')}\n"
        f"{str(version_probe.get('stdout') or version_probe.get('stderr') or '').strip()}"
    ).strip()
    return status_result


def _codex_status_subcommand() -> dict[str, Any]:
    started = time.time()
    try:
        from controller.codex_status import codex_overall_status

        overall = codex_overall_status()
    except Exception as exc:
        return _agent_result("codex", "codex_status", "error", started, reason=str(exc)[:500])
    binary_status = (overall.get("binary") or {}).get("status")
    auth_status = (overall.get("auth") or {}).get("status")
    version_value = (overall.get("version") or {}).get("version") or "?"
    summary_lines = [
        f"/codex status: {overall.get('status')}",
        f"- repo: {overall.get('repo_path')} (present={overall.get('repo_present')})",
        f"- binary: {binary_status} ({(overall.get('binary') or {}).get('path') or 'n/a'})",
        f"- version: {version_value}",
        f"- auth: {auth_status}",
        f"- capabilities: {(overall.get('capabilities') or {}).get('summary', {})}",
        f"- recent codex jobs: {(overall.get('jobs') or {}).get('count', 0)}",
    ]
    return _agent_result(
        "codex",
        "codex_status",
        "success",
        started,
        codex_status=overall,
        response="\n".join(summary_lines),
    )


def _codex_capabilities_subcommand() -> dict[str, Any]:
    started = time.time()
    try:
        from controller.codex_registry import get_codex_capability_inventory

        inventory = get_codex_capability_inventory()
    except Exception as exc:
        return _agent_result("codex", "codex_capabilities", "error", started, reason=str(exc)[:500])
    subsystems = inventory.get("subsystems") or []
    detected = [item for item in subsystems if item.get("detected")]
    lines = [
        f"/codex capabilities: {len(detected)}/{len(subsystems)} detected",
        f"- repo: {inventory.get('repo_path')}",
        f"- callable python helpers: {(inventory.get('callable_python') or {}).get('callable_count', 0)}",
    ]
    for item in detected[:18]:
        lines.append(f"- {item.get('label')} ({item.get('invocation')})")
    return _agent_result(
        "codex",
        "codex_capabilities",
        "success",
        started,
        codex_capabilities=inventory,
        response="\n".join(lines),
    )


def _codex_discovery_subcommand() -> dict[str, Any]:
    started = time.time()
    try:
        from controller.codex_status import codex_auth_summary, codex_repo_evidence, discover_codex_capabilities

        payload = {
            "repo": discover_codex_capabilities(),
            "evidence": codex_repo_evidence(),
            "auth": codex_auth_summary(),
        }
    except Exception as exc:
        return _agent_result("codex", "codex_discovery", "error", started, reason=str(exc)[:500])
    repo_summary = payload["repo"].get("summary", {})
    auth = payload["auth"]
    evidence_keys = list((payload["evidence"].get("evidence") or {}).keys())
    lines = [
        f"/codex discovery: repo={payload['repo'].get('status')} auth={auth.get('status')}",
        f"- repo: {payload['repo'].get('repo_path')}",
        f"- detected subsystems: {repo_summary.get('detected', 0)}/{repo_summary.get('total', 0)}",
        f"- evidence files: {', '.join(evidence_keys[:10]) or '(none)'}",
        f"- auth home: {auth.get('home')} (auth_present={auth.get('auth_present')}, mode={auth.get('auth_mode')})",
    ]
    return _agent_result(
        "codex",
        "codex_discovery",
        "success",
        started,
        codex_discovery=payload,
        response="\n".join(lines),
    )


def _codex_version_subcommand() -> dict[str, Any]:
    started = time.time()
    try:
        from controller.codex_status import codex_version

        info = codex_version()
    except Exception as exc:
        return _agent_result("codex", "codex_version", "error", started, reason=str(exc)[:500])
    response = (
        f"/codex version: {info.get('status')}\n"
        f"- version: {info.get('version') or '?'}\n"
        f"- binary: {(info.get('binary') or {}).get('path') or 'n/a'}"
    )
    return _agent_result("codex", "codex_version", info.get("status") or "unknown", started, codex_version=info, response=response)


def _codex_subsystem_subcommand(key: str, label: str) -> dict[str, Any]:
    started = time.time()
    try:
        from controller.codex_status import discover_codex_capabilities

        inventory = discover_codex_capabilities()
    except Exception as exc:
        return _agent_result("codex", f"codex_{key}", "error", started, reason=str(exc)[:500])
    record = next((item for item in inventory.get("capabilities", []) if item.get("key") == key), None)
    if not record:
        return _agent_result(
            "codex",
            f"codex_{key}",
            "missing",
            started,
            response=f"/codex {key}: subsystem '{key}' niet bekend in deze inventory.",
        )
    detected = record.get("detected")
    paths = record.get("paths") or []
    response = (
        f"/codex {key}: {label}\n"
        f"- detected: {detected}\n"
        f"- invocation: {record.get('invocation')}\n"
        f"- paths: {', '.join(paths) or '(none)'}\n"
        f"- description: {record.get('description')}"
    )
    return _agent_result(
        "codex",
        f"codex_{key}",
        "success" if detected else "missing",
        started,
        codex_subsystem=record,
        response=response,
    )


def _agent_jobs_result(agent: str) -> dict[str, Any]:
    started = time.time()
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        jobs = get_orchestrator().list_jobs(agent=agent, limit=10)
    except Exception as exc:
        return _agent_result(agent, "agent_jobs", "error", started, reason=str(exc), jobs=[])
    latest = jobs[0] if jobs else None
    lines = [f"/{agent} jobs:"]
    if not jobs:
        lines.append("Nog geen jobs gevonden.")
    for job in jobs[:5]:
        label = f"- {job.get('job_id')}: {job.get('status')}"
        preview = _agent_job_clean_preview(job)
        if preview:
            label += f"\n{preview[-1200:]}"
        lines.append(label)
    return _agent_result(
        agent,
        "agent_jobs",
        "success",
        started,
        jobs=jobs,
        latest=latest,
        response="\n".join(lines),
    )


def _agent_job_clean_preview(job: dict[str, Any]) -> str:
    for key in ("output_file", "result_file"):
        path_text = str(job.get(key) or "")
        if not path_text:
            continue
        text = _read_job_artifact_text(path_text, limit=200000)
        if key == "result_file":
            for artifact_text in _read_roo_stdout_artifacts(text):
                extracted = _extract_roo_preview_from_text(artifact_text)
                if extracted:
                    return extracted
        extracted = _extract_roo_preview_from_text(text)
        if extracted:
            return extracted
    return _extract_roo_preview_from_text(str(job.get("response_preview") or ""))


def _read_job_artifact_text(path_text: str, *, limit: int = 200000) -> str:
    candidates = [Path(path_text)]
    if path_text.startswith("/workspace/"):
        candidates.append(workspace_root() / path_text.removeprefix("/workspace/"))
    host_prefix = "/home/pwintri2/WintripAI/"
    if path_text.startswith(host_prefix):
        candidates.append(workspace_root() / path_text.removeprefix(host_prefix))
    for path in candidates:
        try:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")[:limit]
        except Exception:
            continue
    return ""


def _extract_roo_preview_from_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    extracted = _extract_roo_preview_from_json(parsed)
    if extracted:
        return extracted
    result_content = re.search(r'"type"\s*:\s*"result".{0,400}?"content"\s*:\s*"((?:\\.|[^"\\])*)"', raw, flags=re.S)
    if result_content:
        try:
            return json.loads(f'"{result_content.group(1)}"').strip()
        except Exception:
            return result_content.group(1).strip()
    matches = re.findall(r'"type"\s*:\s*"assistant".{0,1200}?"content"\s*:\s*"((?:\\.|[^"\\])*)"', raw, flags=re.S)
    if matches:
        try:
            return json.loads(f'"{matches[-1]}"').strip()
        except Exception:
            return matches[-1].strip()
    if raw.startswith("{") and '"events"' in raw:
        return "Roo job voltooid; open Agent Jobs voor de volledige event-trace."
    if _looks_like_roo_event_fragment(raw):
        return ""
    return raw.strip()


def _looks_like_roo_event_fragment(text: str) -> bool:
    raw = str(text or "")
    markers = sum(1 for marker in ('"done"', '"type"', '"tool_use"', '"thinking"', '"status"', '"content"') if marker in raw)
    return markers >= 4


def _read_roo_stdout_artifacts(result_text: str) -> list[str]:
    try:
        parsed = json.loads(result_text)
    except Exception:
        return []
    if not isinstance(parsed, dict):
        return []
    out: list[str] = []
    for artifact in parsed.get("artifacts") or []:
        artifact_text = str(artifact or "")
        if not artifact_text.endswith(("roo_stdout.log", "stdout.log")):
            continue
        text = _read_job_artifact_text(artifact_text, limit=200000)
        if text:
            out.append(text)
    return out


def _extract_roo_preview_from_json(value: Any) -> str:
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        events = value.get("events")
        if isinstance(events, list):
            for item in reversed(events):
                if isinstance(item, dict) and item.get("type") == "assistant":
                    event_content = item.get("content")
                    if isinstance(event_content, str) and event_content.strip():
                        return event_content.strip()
        response = value.get("response_preview")
        if isinstance(response, str) and response.strip():
            return _extract_roo_preview_from_text(response)
    return ""


def _run_ruflo_swarm(task: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    if not _command_exists("ruflo"):
        return _agent_result("ruflo", "ruflo_swarm", "missing", started, response="Ruflo CLI is niet gevonden op de host.")
    claude_auth = _claude_auth_status()
    if not claude_auth.get("logged_in"):
        return _login_required("ruflo", started, "https://claude.ai/login")
    prompt = _agent_prompt("Ruflo swarm", task)
    commands = [
        ["ruflo", "swarm", "init", "--v3-mode"],
        ["ruflo", "agent", "spawn", "-t", "coder"],
        ["ruflo", "task", "create", "-t", "implementation", "-d", prompt],
        ["ruflo", "swarm", "start", "-o", prompt, "-s", "development"],
    ]
    results = []
    for command in commands:
        results.append(_run_command(command, cwd=_host_wintrip_root(), timeout_seconds=max(10, min(timeout_seconds, 90))))
    status = "success" if any(item.get("status") == "success" for item in results) else results[-1].get("status", "error")
    return _agent_result("ruflo", "ruflo_swarm", status, started, commands=[_public_command(item) for item in commands], steps=results)


def _run_claude_code(task: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    if not _command_exists("claude"):
        return _agent_result("claude", "claude_code", "missing", started, response="Claude Code CLI is niet gevonden op de host.")
    auth = _claude_auth_status()
    if not auth.get("logged_in"):
        return _login_required("claude", started, "https://claude.ai/login")
    prompt = _agent_prompt("Claude Code", task)
    command = [
        "claude",
        "-p",
        prompt,
        "--add-dir",
        str(ruflo_path()),
        "--add-dir",
        str(codex_path()),
        "--add-dir",
        str(roo_path()),
        "--permission-mode",
        "acceptEdits",
        "--output-format",
        "json",
    ]
    result = _run_command(command, cwd=_host_wintrip_root(), timeout_seconds=timeout_seconds)
    return _agent_result("claude", "claude_code", result["status"], started, command=_public_command(command), process=result)


def _submit_host_agent_runtime(agent: str, task: str, timeout_seconds: int, started: float | None = None) -> dict[str, Any]:
    started = started or time.time()
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if agent not in orchestrator.adapters:
            orchestrator.register_adapter(agent, _host_agent_runtime_adapter(agent))
        record = orchestrator.submit(
            agent=agent,
            task=task,
            timeout_seconds=int(timeout_seconds or 240),
            metadata={"prompt": _agent_prompt(agent.title(), task), "slash_agent": agent},
        )
    except Exception as exc:
        return _agent_result(agent, f"{agent}_runtime", "error", started, reason=str(exc))
    return _agent_result(
        agent,
        f"{agent}_runtime",
        "running",
        started,
        job=record.to_dict(),
        response=(
            f"{agent} job {record.job_id} gestart in de agent runtime. "
            f"Volg live in Agent Jobs of vraag `/{agent} status` voor de laatste samenvatting."
        ),
    )


def _submit_ecosystem_agent_runtime(
    agent: str,
    task: str,
    timeout_seconds: int,
    started: float | None = None,
    bridge_result: dict[str, Any] | None = None,
    approval: str = "",
) -> dict[str, Any]:
    started = started or time.time()
    try:
        from controller.agent_runtime.adapters.ecosystem_cli import ecosystem_agent_status

        runtime_status = ecosystem_agent_status(agent, prefer_bridge=False)
    except Exception as exc:
        return _agent_result(agent, f"{agent}_runtime", "error", started, reason=str(exc)[:500])

    runnable = bool(runtime_status.get("runtime_reachable"))
    cargo_fallback = agent == "deepseek" and bool(runtime_status.get("cargo_fallback_available"))
    if not runnable and not cargo_fallback:
        response = (
            f"/{agent} is nog niet launchable in deze runtime.\n"
            f"- status: {runtime_status.get('status')}\n"
            f"- root: {runtime_status.get('root')}\n"
            f"- reason: {runtime_status.get('reason')}\n"
            "Start de host bridge of bouw/installeer de CLI, dan kan dezelfde slash-opdracht als job draaien."
        )
        if bridge_result and bridge_result.get("transport_error"):
            response += f"\nBridge fallback: {bridge_result.get('reason')}"
        return _agent_result(
            agent,
            f"{agent}_runtime",
            str(runtime_status.get("status") or "missing"),
            started,
            ecosystem_status=runtime_status,
            bridge=bridge_result,
            response=response,
        )
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        record = orchestrator.submit(
            agent=agent,
            task=task,
            timeout_seconds=int(timeout_seconds or 240),
            metadata={
                "prompt": _agent_prompt(agent.title(), task),
                "slash_agent": agent,
                "runtime_status": runtime_status,
                "approval": _approval_effective(approval),
                "approval_status": "approved" if _approval_effective(approval) == APPROVAL_PHRASE else "missing",
            },
        )
    except Exception as exc:
        return _agent_result(agent, f"{agent}_runtime", "error", started, reason=str(exc)[:500], ecosystem_status=runtime_status)
    return _agent_result(
        agent,
        f"{agent}_runtime",
        "running",
        started,
        job=record.to_dict(),
        ecosystem_status=runtime_status,
        response=(
            f"{agent} job {record.job_id} gestart in de agent runtime. "
            f"Volg live in Agent Jobs of vraag `/{agent} jobs` voor de laatste samenvatting."
        ),
    )


def _ecosystem_source_root(agent: str) -> Path:
    from controller.agent_runtime.adapters.ecosystem_cli import atlas_root, deepseek_root

    return deepseek_root() if agent == "deepseek" else atlas_root()


def _resolve_ecosystem_source_path(agent: str, root: Path, raw_path: str) -> Path | None:
    text = str(raw_path or ".").strip().replace("\\", "/") or "."
    alias, _, rest = text.partition("/")
    if alias.lower() == agent:
        text = rest or "."
    if _secretish_path(text):
        return None
    candidate = Path(text)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    try:
        rel = str(target.relative_to(root.resolve()))
    except ValueError:
        rel = str(target)
    return None if _secretish_path(rel) else target


def _safe_list_source(target: Path, *, limit: int = 160) -> list[str]:
    if target.is_file():
        return [target.name]
    if not target.exists():
        return []
    items: list[str] = []
    for child in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".git") or _secretish_path(child.name):
            continue
        items.append(child.name + ("/" if child.is_dir() else ""))
        if len(items) >= limit:
            items.append("... truncated")
            break
    return items


def _safe_search_source(target: Path, pattern: str, *, limit: int = 120) -> list[str]:
    regex = re.compile(pattern)
    roots = [target] if target.is_file() else [path for path in target.rglob("*") if path.is_file()]
    matches: list[str] = []
    for path in roots:
        if any(_secretish_path(part) for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{path}:{line_no}:{line[:260]}")
                if len(matches) >= limit:
                    matches.append("... truncated")
                    return matches
    return matches


def _secretish_path(value: str) -> bool:
    lowered = str(value or "").casefold()
    return any(marker in lowered for marker in ("secret", "token", "key", "auth", "cookie", "session", ".env", "credential"))


def _submit_roo_agent_runtime(
    task: str,
    provider: str,
    model: str,
    approval: str,
    timeout_seconds: int,
    started: float | None = None,
) -> dict[str, Any]:
    started = started or time.time()
    try:
        from controller.agent_runtime.adapters.roo_cli import roo_status
        from controller.agent_runtime.orchestrator import get_orchestrator
        from controller.roo_cli_runtime import cockpit_provider_for_roo_selection, map_cockpit_provider

        selected_provider = str(provider or "").strip().lower()
        selected_model = str(model or "").strip()
        cockpit_provider = cockpit_provider_for_roo_selection(selected_provider, selected_model)
        provider_map = map_cockpit_provider(cockpit_provider, selected_model)
        if provider_map.get("status") != "mapped":
            return _agent_result(
                "roo",
                "roo_cli",
                "blocked",
                started,
                route="roo_runtime",
                provider="roo",
                requested_provider=selected_provider,
                model=selected_model,
                local_only=cockpit_provider == "ollama",
                cockpit_provider=cockpit_provider,
                cockpit_model=selected_model,
                roo_provider_map=provider_map,
                configuration_required=True,
                response=str(provider_map.get("reason") or f"Roo ondersteunt Cockpit-provider `{cockpit_provider}` nog niet."),
            )
        roo_provider = str(provider_map.get("roo_provider") or "")
        if roo_provider == "roo" and not (_roo_cloud_auth_ready() or _roo_api_key_ready(cockpit_provider, provider_map)):
            return _agent_result(
                "roo",
                "roo_cli",
                "blocked",
                started,
                route="roo_runtime",
                provider="roo",
                requested_provider=selected_provider,
                model=selected_model,
                local_only=False,
                cockpit_provider=cockpit_provider,
                cockpit_model=selected_model,
                roo_provider_map=provider_map,
                configuration_required=True,
                response=(
                    f"Roo kan `{selected_model}` pas via Roo Cloud starten nadat Roo Cloud in Cockpit is ingelogd. "
                    "Ga naar Models -> Roo Cloud Account -> Login."
                ),
            )
        if roo_provider != "roo" and not _roo_api_key_ready(cockpit_provider, provider_map):
            return _agent_result(
                "roo",
                "roo_cli",
                "blocked",
                started,
                route="roo_runtime",
                provider="roo",
                requested_provider=selected_provider,
                model=selected_model,
                local_only=False,
                cockpit_provider=cockpit_provider,
                cockpit_model=selected_model,
                roo_provider_map=provider_map,
                configuration_required=True,
                response=(
                    f"Roo kan `{selected_model}` pas via `{cockpit_provider}` starten als de API key "
                    "in Cockpit of de host-omgeving beschikbaar is."
                ),
            )
        runtime_status = roo_status(prefer_bridge=True)
        record = get_orchestrator().submit(
            agent="roo",
            task=task,
            timeout_seconds=_roo_agent_timeout_seconds(timeout_seconds),
            metadata={
                "prompt": _agent_prompt("Roo Code", task),
                "slash_agent": "roo",
                "approval": approval,
                "approval_status": "approved" if approval == APPROVAL_PHRASE else "missing",
                "selected_cockpit_provider": selected_provider,
                "selected_cockpit_model": selected_model,
                "cockpit_provider": cockpit_provider,
                "cockpit_model": selected_model,
                "roo_provider_map": provider_map,
                "runtime_status": {
                    "status": runtime_status.get("status"),
                    "available": runtime_status.get("available"),
                    "via_bridge": runtime_status.get("via_bridge"),
                    "ollama_cli_supported": runtime_status.get("ollama_cli_supported"),
                },
            },
        )
    except Exception as exc:
        return _agent_result("roo", "roo_cli", "error", started, reason=str(exc)[:500])
    return _agent_result(
        "roo",
        "roo_cli",
        "running",
        started,
        route="roo_runtime",
        provider="roo",
        requested_provider=str(provider or "").strip().lower(),
        model=str(model or "").strip(),
        local_only=record.metadata.get("cockpit_provider") == "ollama",
        cockpit_provider=record.metadata.get("cockpit_provider"),
        cockpit_model=record.metadata.get("cockpit_model"),
        roo_provider_map=record.metadata.get("roo_provider_map"),
        job=record.to_dict(),
        provenance={
            "tools_used": ["roo_cli"],
            "planner_source": "slash_roo_runtime",
        },
        response=(
            f"Roo Code job {record.job_id} gestart met Cockpit-model `{model or 'model'}` "
            f"via provider `{provider or 'auto'}`. Volg live in Agent Jobs of vraag `/roo jobs`."
        ),
    )


def _roo_agent_timeout_seconds(requested: int | float | None = None) -> int:
    try:
        configured = int(os.getenv("WINTRIP_ROO_AGENT_TIMEOUT_SECONDS", "1800"))
    except ValueError:
        configured = 1800
    try:
        requested_int = int(requested or 0)
    except (TypeError, ValueError):
        requested_int = 0
    return max(300, min(max(configured, requested_int), 7200))


def _roo_selection_is_local(provider: str, model: str) -> bool:
    try:
        from controller.roo_cli_runtime import cockpit_provider_for_roo_selection

        return cockpit_provider_for_roo_selection(provider, model) == "ollama"
    except Exception:
        return str(provider or "").strip().lower() in {"", "local", "ollama"}


def _roo_api_key_ready(cockpit_provider: str, provider_map: dict[str, Any]) -> bool:
    """Check if an API key is available from any source: env, key store, or subscription."""
    api_key_env = str(provider_map.get("api_key_env") or "")
    if not api_key_env:
        return True
    # Try the unified resolver which checks env -> api_key_store -> subscription_store
    try:
        from controller.roo_cli_runtime import api_key_available_for_provider

        return api_key_available_for_provider(cockpit_provider, provider_map)
    except Exception:
        pass
    # Fallback: original logic (env + key store only)
    if os.getenv(api_key_env):
        return True
    aliases = {
        "chatgpt": "openai",
        "openai-native": "openai",
        "openai": "openai",
        "claude": "anthropic",
        "anthropic": "anthropic",
        "gemini": "google",
        "google": "google",
    }
    try:
        from controller.api_key_store import load_provider_api_keys

        keys = load_provider_api_keys()
    except Exception:
        keys = {}
    provider_id = aliases.get(str(cockpit_provider or "").strip().lower(), str(cockpit_provider or "").strip().lower())
    return bool(keys.get(provider_id))


def _roo_cloud_auth_ready() -> bool:
    try:
        from controller.agent_runtime.adapters.roo_cli import roo_cloud_auth_status

        status = roo_cloud_auth_status(prefer_bridge=True)
        return bool(status.get("logged_in"))
    except Exception:
        return False


def _host_agent_runtime_adapter(agent: str):
    def adapter(job: Any, log: Any, on_progress: Any) -> dict[str, Any]:
        log.append("slash_host_agent_start", {"agent": agent})
        if agent == "ruflo":
            result = _run_ruflo_swarm(task=job.task, timeout_seconds=int(job.timeout_seconds or 240))
        elif agent == "claude":
            result = _run_claude_code(task=job.task, timeout_seconds=int(job.timeout_seconds or 240))
        else:
            result = {"status": "failed", "reason": f"unsupported host runtime agent: {agent}"}
        response = str(result.get("response") or _default_response(result) or "")
        if agent == "ruflo":
            try:
                from controller.agent_runtime.adapters.ruflo_swarm import analyze_ruflo_swarm_signal

                coherence = 0.82 if result.get("status") in {"success", "handoff"} else 0.42
                nexus_event = analyze_ruflo_swarm_signal(
                    job.task,
                    coherence=coherence,
                    agent_id=job.job_id,
                    metadata={"slash_status": result.get("status"), "tool": result.get("tool")},
                )
                log.append("ruflo_quantum_corruption_nexus", nexus_event)
                if nexus_event.get("action") == "sacred_corruption" and nexus_event.get("recommended_prompt"):
                    response = f"{response}\n\n## Nexus creative retry\n\n{nexus_event['recommended_prompt']}"
            except Exception as exc:
                log.append("ruflo_quantum_corruption_nexus_error", {"reason": str(exc)})
        try:
            Path(job.output_file).write_text(response, encoding="utf-8")
        except Exception:
            pass
        log.append("slash_host_agent_result", {"agent": agent, "status": result.get("status")})
        final_status = "completed" if result.get("status") in {"success", "handoff", "login_required", "missing"} else "failed"
        return {
            "status": final_status,
            "exit_code": 0 if final_status == "completed" else None,
            "response_preview": response[:2000],
            "reason": str(result.get("reason") or "")[:1000],
            "slash_result": result,
        }

    return adapter


def _write_host_agent_handoff(agent: str, task: str, started: float, bridge_result: dict[str, Any] | None = None) -> dict[str, Any]:
    handoff = _write_agent_handoff(agent, task)
    living_tick = _living_agent_whisper(agent, task, status="handoff", handoff_path=str(handoff.get("path") or ""))
    response = (
        f"/{agent} is niet inline gestart om de cockpit responsief te houden. "
        f"Taak staat klaar als handoff: {handoff.get('path')}"
    )
    if bridge_result and bridge_result.get("reason"):
        response += f"\nBridge fallback: {bridge_result.get('reason')}"
    return _agent_result(
        agent,
        f"{agent}_handoff",
        "handoff",
        started,
        handoff=handoff,
        bridge=bridge_result,
        living=living_tick,
        response=response,
    )


def _bridge_agent_command(agent: str, task: str, approval: str, timeout_seconds: int) -> dict[str, Any] | None:
    base_url = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
    if not base_url or not token_path:
        return None
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
        body = json.dumps(
            {"agent": agent, "task": task, "approval": approval, "timeout_seconds": timeout_seconds}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/agents/command",
            data=body,
            headers={"Content-Type": "application/json", "X-Ouroboros-Bridge-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_bridge_timeout_seconds(timeout_seconds)) as response:
            data = json.loads(response.read().decode("utf-8"))
        data["via_bridge"] = True
        return data
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            data = {"status": "error", "reason": str(exc), "fake_success": False}
        data["via_bridge"] = True
        return data
    except Exception as exc:
        return {
            "status": "bridge_unavailable",
            "route": "slash_agent",
            "agent": agent,
            "reason": f"Host bridge agent call failed: {exc}",
            "via_bridge": True,
            "transport_error": True,
            "fake_success": False,
        }


def _bridge_timeout_seconds(timeout_seconds: int) -> int:
    try:
        configured = int(os.getenv("WINTRIP_SLASH_BRIDGE_TIMEOUT_SECONDS", "8"))
    except ValueError:
        configured = 8
    return max(1, min(configured, max(1, int(timeout_seconds or 8)), 30))


def _allow_inline_host_agents() -> bool:
    return str(os.getenv("WINTRIP_SLASH_INLINE_HOST_AGENTS") or "").strip().lower() in {"1", "true", "yes", "ja"}


def _allow_runtime_host_agents() -> bool:
    return str(os.getenv("WINTRIP_SLASH_RUNTIME_HOST_AGENTS") or "").strip().lower() in {"1", "true", "yes", "ja"}


def _run_command(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    timeout_seconds = max(1, min(int(timeout_seconds or 60), 600))
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env=_host_env(),
            check=False,
        )
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": _redact(proc.stdout[-12000:]),
            "stderr": _redact(proc.stderr[-12000:]),
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "exit_code": None,
            "stdout": _redact((exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else ""),
            "stderr": _redact((exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else ""),
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "duration_seconds": round(time.time() - started, 3), "fake_success": False}


def _codex_login_status() -> dict[str, Any]:
    if not _command_exists("codex"):
        return {"logged_in": False}
    result = _run_command(["codex", "login", "status"], cwd=_host_wintrip_root(), timeout_seconds=10)
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    logged_in = result.get("status") == "success" and "logged in" in output
    return {"logged_in": logged_in, "status": result.get("status"), "source": "codex login status"}


def _claude_auth_status() -> dict[str, Any]:
    if not _command_exists("claude"):
        return {"logged_in": False}
    result = _run_command(["claude", "auth", "status"], cwd=_host_wintrip_root(), timeout_seconds=10)
    logged_in = False
    try:
        payload = json.loads(result.get("stdout", "") or "{}")
        logged_in = bool(payload.get("loggedIn"))
    except Exception:
        logged_in = "logged" in str(result.get("stdout", "")).lower()
    return {"logged_in": logged_in, "status": result.get("status")}


def _login_required(agent: str, started: float, url: str) -> dict[str, Any]:
    return _agent_result(
        agent,
        "login_required",
        "login_required",
        started,
        response=f"{agent} heeft eerst een browser/CLI-login nodig.",
        frontend_action={"type": "open_url", "url": url, "target": "_blank", "agent": agent},
    )


def _agent_prompt(agent_label: str, task: str) -> str:
    roots = _agent_roots()
    self_context = _agent_self_context_prompt_block()
    return (
        f"{agent_label} werkt nu als onderdeel van Ouroboros.\n\n"
        f"Opdracht van Philip:\n{task}\n\n"
        "Systeemcontext:\n"
        f"- WintripAI root: {roots['wintripai']}\n"
        f"- Ruflo root: {roots['ruflo']}\n"
        f"- Roo root: {roots['roo']}\n"
        f"- Codex root: {roots['codex']}\n"
        f"- DeepSeek root: {roots['deepseek']}\n"
        f"- Atlas root: {roots['atlas']}\n"
        "- Lees AGENTS.md en OUROBOROS_IDE_CONTEXT.md wanneer aanwezig.\n"
        "- Werk in WintripAI tenzij Philip expliciet iets anders vraagt.\n"
        "- Respecteer bestaande dirty worktree; revert geen onbekende wijzigingen.\n"
        "- Schrijf geen API keys, OAuth tokens, bearer tokens of browser session data naar bestanden/logs.\n"
        "- Valideer met gerichte tests waar haalbaar en rapporteer echte stdout/stderr.\n"
        f"{self_context}"
    )


def _agent_self_context_prompt_block() -> str:
    try:
        status = get_self_context_status()
    except Exception as exc:
        return f"\nOuroboros self-context:\n- Status: unavailable ({_clip(_redact(str(exc)), 240)})\n"
    if not isinstance(status, dict):
        return "\nOuroboros self-context:\n- Status: unavailable (invalid status payload)\n"

    lines = [
        "\nOuroboros self-context:",
        f"- Status: {_clip(_redact(status.get('status', 'unknown')), 80)}",
        f"- State path: {_clip(_redact(status.get('state_path', '')), 220)}",
        f"- Conversations: {_int_or_zero(status.get('conversation_count'))}",
        f"- Lessons: {_int_or_zero(status.get('lesson_count'))}",
    ]
    latest = [item for item in list(status.get("latest_conversations") or []) if isinstance(item, dict)]
    if latest:
        lines.append("- Latest conversations:")
        for item in latest[:3]:
            conversation_id = _clip(_redact(item.get("conversation_id", "")), 100)
            summary = _clip(_redact(str(item.get("summary") or "").replace("\n", " ")), 360)
            turn_count = _int_or_zero(item.get("turn_count"))
            if summary:
                lines.append(f"  - {conversation_id} ({turn_count} turns): {summary}")
            else:
                lines.append(f"  - {conversation_id} ({turn_count} turns)")
    lessons = [item for item in list(status.get("recent_lessons") or []) if isinstance(item, dict)]
    if lessons:
        lines.append("- Recent lessons:")
        for item in lessons[:3]:
            text = _clip(_redact(str(item.get("text") or "").replace("\n", " ")), 420)
            keywords = ", ".join(_clip(_redact(keyword), 40) for keyword in list(item.get("keywords") or [])[:6])
            if text:
                suffix = f" [keywords: {keywords}]" if keywords else ""
                lines.append(f"  - {text}{suffix}")
    ruflo = status.get("ruflo") if isinstance(status.get("ruflo"), dict) else {}
    if ruflo:
        ruflo_status = _clip(_redact(ruflo.get("status", "unknown")), 80)
        ruflo_path_value = _clip(_redact(ruflo.get("path", "")), 220)
        lines.append(f"- Ruflo status: {ruflo_status}" + (f" ({ruflo_path_value})" if ruflo_path_value else ""))
    lines.append("- Gebruik deze server-side context als continuïteitslaag; vertrouw niet op browsergeschiedenis alleen.")
    return "\n".join(lines) + "\n"


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _write_agent_handoff(agent: str, task: str) -> dict[str, Any]:
    out_dir = _agent_output_dir() / agent
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_stamp()}_{agent}_task.md"
    path.write_text(
        f"# {agent.title()} Agent Task\n\n"
        f"- Created: {datetime.utcnow().isoformat()}Z\n"
        f"- Agent: `{agent}`\n\n"
        f"## Task\n\n{task}\n\n"
        f"## Context\n\n"
        f"- WintripAI: `{_agent_roots()['wintripai']}`\n"
        f"- Ruflo: `{_agent_roots()['ruflo']}`\n"
        f"- Roo: `{_agent_roots()['roo']}`\n"
        f"- Codex: `{_agent_roots()['codex']}`\n"
        f"- DeepSeek: `{_agent_roots()['deepseek']}`\n"
        f"- Atlas: `{_agent_roots()['atlas']}`\n"
        f"- Shared map: `OUROBOROS_IDE_CONTEXT.md`\n",
        encoding="utf-8",
    )
    return {"status": "written", "path": str(path)}


def _agent_output_dir() -> Path:
    root = workspace_root()
    path = root / "out" / "agent_tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _living_agent_whisper(agent: str, task: str, **metadata: Any) -> dict[str, Any] | None:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import get_living_ouroboros_loop

        return get_living_ouroboros_loop().observe_agent_event(
            {
                "agent": agent,
                "task": task[:500],
                **metadata,
            }
        )
    except Exception:
        return None


def _agent_result(agent: str, tool: str, status: str, started: float, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "route": "slash_agent",
        "agent": agent,
        "tool": tool,
        "duration_seconds": round(time.time() - started, 3),
        "roots": _agent_roots(),
        "fake_success": False,
    }
    payload.update(extra)
    payload.setdefault("response", _default_response(payload))
    return payload


def _default_response(payload: dict[str, Any]) -> str:
    parts = [
        f"/{payload.get('agent')} {payload.get('tool')}: {payload.get('status')}",
        str(payload.get("response") or ""),
    ]
    process = payload.get("process") if isinstance(payload.get("process"), dict) else None
    if process:
        if process.get("stdout"):
            parts.append(str(process.get("stdout")))
        if process.get("stderr"):
            parts.append(str(process.get("stderr")))
    roo_result = payload.get("roo_result") if isinstance(payload.get("roo_result"), dict) else None
    if roo_result:
        if roo_result.get("stdout"):
            parts.append(str(roo_result.get("stdout")))
        if roo_result.get("stderr"):
            parts.append(str(roo_result.get("stderr")))
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    for index, step in enumerate(steps[:4], start=1):
        if not isinstance(step, dict):
            continue
        line = f"step {index}: {step.get('status')} exit={step.get('exit_code')}"
        tail = str(step.get("stdout") or step.get("stderr") or step.get("reason") or "").strip()
        parts.append(f"{line}\n{tail[-1200:]}" if tail else line)
    return "\n".join(part for part in parts if part).strip()


def _catalog_text() -> str:
    return "\n".join(
        [
            "Slash agents:",
            "/codex <opdracht>",
            "/deepseek <opdracht>",
            "/atlas <opdracht>",
            "/ruflo <opdracht>",
            "/claude <opdracht>",
            "/roo <opdracht>",
            "/agents",
        ]
    )


def _agent_roots() -> dict[str, str]:
    from controller.ouroboros_paths import atlas_path, deepseek_path

    return {
        "wintripai": str(workspace_root()),
        "ruflo": str(ruflo_path()),
        "roo": str(roo_path()),
        "codex": str(codex_path()),
        "deepseek": str(deepseek_path()),
        "atlas": str(atlas_path()),
    }


def _host_wintrip_root() -> Path:
    configured = os.getenv("WINTRIP_HOST_WORKSPACE") or os.getenv("WINTRIP_PROJECT_ROOT") or "/home/pwintri2/WintripAI"
    root = Path(configured).expanduser()
    if not root.exists():
        root = workspace_root()
    return root.resolve()


def _host_env() -> dict[str, str]:
    env = dict(os.environ)
    configured_codex_binary = env.get("WINTRIP_CODEX_BINARY") or env.get("CODEX_BINARY")
    node_bin = str(Path.home() / ".nvm" / "versions" / "node" / "v22.22.2" / "bin")
    extension_bases = (
        Path.home() / ".windsurf" / "extensions",
        Path.home() / ".vscode" / "extensions",
        Path.home() / ".antigravity" / "extensions",
        Path.home() / ".cursor" / "extensions",
    )
    codex_bins = [
        str(path)
        for base in extension_bases
        for path in sorted(base.glob("openai.chatgpt-*/bin/linux-x86_64"))
        if path.exists()
    ]
    extra_bins = [
        str(Path(configured_codex_binary).expanduser().parent) if configured_codex_binary else "",
        "/codex_native/bin/linux-x86_64",
        node_bin,
        "/home/pwintri2/.cargo/bin",
        str(Path.home() / ".cargo" / "bin"),
        str(Path.home() / ".local" / "bin"),
        *codex_bins,
    ]
    env["PATH"] = os.pathsep.join([item for item in [*extra_bins, env.get("PATH", "")] if item])
    env.setdefault("WINTRIP_HOST_WORKSPACE", str(_host_wintrip_root()))
    return env


def _command_exists(name: str) -> bool:
    if name == "codex":
        configured = os.getenv("WINTRIP_CODEX_BINARY") or os.getenv("CODEX_BINARY")
        if configured and Path(configured).expanduser().exists():
            return True
    paths = _host_env().get("PATH", "").split(os.pathsep)
    return any((Path(path) / name).exists() for path in paths if path)


def _approval_effective(approval: str) -> str:
    if str(approval or "").strip() == APPROVAL_PHRASE:
        return APPROVAL_PHRASE
    if str(os.getenv("WINTRIP_SANDBOX_PREAPPROVED") or "").strip() == "1":
        return str(os.getenv("WINTRIP_DEFAULT_APPROVAL") or APPROVAL_PHRASE).strip()
    return str(approval or "").strip()


def _public_command(command: list[str]) -> list[str]:
    public: list[str] = []
    for item in command:
        text = str(item)
        public.append(_clip(_redact(text), 220))
    return public


def _redact(text: str) -> str:
    redacted = str(text or "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _clip(value: Any, limit: int = 4000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def _stamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
