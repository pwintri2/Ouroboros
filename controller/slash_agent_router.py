"""Slash-command router for cockpit controlled coding agents.

The cockpit chat remains the human entrypoint. Prompts that start with `/`
are routed to bounded local agent adapters instead of an LLM provider. Codex
and Ruflo/Claude can run on the host through the authenticated host bridge;
Roo uses the local Python Roo adapter and task handoff files.
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
        return Path(os.getenv("WINTRIP_ROO_PATH") or "/home/pwintri2/Roo").expanduser().resolve()

    def ruflo_path() -> Path:
        return Path(os.getenv("WINTRIP_RUFLO_PATH") or "/home/pwintri2/ruflo").expanduser().resolve()

    def get_self_context_status() -> dict[str, Any]:
        return {"status": "unavailable", "fake_success": False}


APPROVAL_PHRASE = "Akkoord"
SUPPORTED_COMMANDS = ("agents", "help", "codex", "ruflo", "claude", "roo")
HOST_AGENT_COMMANDS = {"codex", "ruflo", "claude"}
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
            "/ruflo <opdracht>": "Start Ruflo swarm-coordinatie rond de opdracht.",
            "/claude <opdracht>": "Laat Claude Code in WintripAI werken als auth beschikbaar is.",
            "/roo <opdracht>": "Gebruik Roo adapter of maak een Roo IDE-handoff.",
        },
        "roots": _agent_roots(),
        "approval_phrase": APPROVAL_PHRASE,
        "preapproved": _approval_effective("") == APPROVAL_PHRASE,
        "fake_success": False,
    }


def handle_slash_command(prompt: str, approval: str = "", timeout_seconds: int = 240) -> dict[str, Any] | None:
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
        return execute_roo_agent_task(task=task, approval=approval)
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


def execute_roo_agent_task(task: str, approval: str = "") -> dict[str, Any]:
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

    handoff = _write_agent_handoff("roo", task)
    return _agent_result(
        "roo",
        "roo_task_handoff",
        "handoff",
        started,
        response=(
            "Roo taak staat klaar als IDE-handoff. Gebruik Roo in VS Code op deze taak, "
            "of specificeer /roo read, /roo list, /roo search, /roo run: voor directe adapter-acties."
        ),
        handoff=handoff,
    )


def _run_codex_exec(task: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
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
        if job.get("response_preview"):
            label += f"\n{str(job.get('response_preview')).strip()[-1200:]}"
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
    whisper = ((living_tick or {}).get("whisper") or {}).get("text") if isinstance(living_tick, dict) else ""
    if whisper:
        response += f"\nLiving Ouroboros: {whisper}"
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
            "/ruflo <opdracht>",
            "/claude <opdracht>",
            "/roo <opdracht>",
            "/agents",
        ]
    )


def _agent_roots() -> dict[str, str]:
    return {
        "wintripai": str(workspace_root()),
        "ruflo": str(ruflo_path()),
        "roo": str(roo_path()),
        "codex": str(codex_path()),
    }


def _host_wintrip_root() -> Path:
    configured = os.getenv("WINTRIP_HOST_WORKSPACE") or os.getenv("WINTRIP_PROJECT_ROOT") or "/home/pwintri2/WintripAI"
    root = Path(configured).expanduser()
    if not root.exists():
        root = workspace_root()
    return root.resolve()


def _host_env() -> dict[str, str]:
    env = dict(os.environ)
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
    extra_bins = [node_bin, str(Path.home() / ".local" / "bin"), *codex_bins]
    env["PATH"] = os.pathsep.join([*extra_bins, env.get("PATH", "")])
    env.setdefault("WINTRIP_HOST_WORKSPACE", str(_host_wintrip_root()))
    return env


def _command_exists(name: str) -> bool:
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
