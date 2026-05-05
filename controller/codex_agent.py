"""Small agentic bridge around the Codex registry and local Ouroboros tools.

The bridge is intentionally bounded: it can remember chat, choose a few real
tools, ask the frontend to open a browser tab, run safe shell commands in the
Docker workspace, and log missing capabilities as implementation backlog.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from controller.safe_shell import run_safe_shell, workspace_root


APPROVAL_PHRASE = "Akkoord"
URL_RE = re.compile(r"https?://[^\s)>\]]+")
COMMAND_PREFIX_RE = re.compile(r"(?is)^\s*(?:run|voer uit|execute|shell|command|commando)\s*:\s*(.+)$")
REMEMBER_RE = re.compile(r"(?is)\b(?:onthoud|remember|noteer)\b[:\s]*(.+)")
OPEN_BROWSER_RE = re.compile(r"(?i)\b(open|start|launch)\b.*\b(browser|url|website|site|tab)\b")
READ_BROWSER_RE = re.compile(r"(?i)\b(lees|read|onderzoek|research|scrape|haal)\b.*\b(browser|url|website|site|pagina|page)\b")
CODEX_RUNTIME_RE = re.compile(
    r"(?is)^\s*(?:codex\s*(?:run|exec|job|runtime)?\s*:|laat\s+codex\s+|gebruik\s+codex\s+(?:voor|om)\s+|delegate\s+to\s+codex\s*:?)\s*(.+)$"
)
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)


def _workspace_root() -> Path:
    return workspace_root()


def codex_agent_state_path() -> Path:
    return (_workspace_root() / ".secrets" / "codex_agent_state.json").resolve()


def codex_agent_log_path() -> Path:
    return (_workspace_root() / ".secrets" / "codex_agent_events.json").resolve()


def codex_agent_backlog_path() -> Path:
    return (_workspace_root() / ".secrets" / "codex_agent_capability_backlog.json").resolve()


def self_improvement_dir() -> Path:
    return (_workspace_root() / "out" / "codex_agent_self_improvements").resolve()


def get_codex_agent_status() -> dict[str, Any]:
    state = _load_state()
    log = _load_json(codex_agent_log_path(), {"events": []})
    backlog = _load_json(codex_agent_backlog_path(), {"gaps": []})
    return {
        "status": "online",
        "fake_success": False,
        "docker_first": True,
        "workspace": str(_workspace_root()),
        "state_path": str(codex_agent_state_path()),
        "event_log_path": str(codex_agent_log_path()),
        "backlog_path": str(codex_agent_backlog_path()),
        "memory_count": len(state.get("memory", [])),
        "conversation_count": len(state.get("conversation", [])),
        "capability_gap_count": len(backlog.get("gaps", [])),
        "recent_events": list(log.get("events") or [])[:10],
        "recent_memory": list(state.get("memory") or [])[:8],
        "recent_gaps": list(backlog.get("gaps") or [])[:8],
        "tools": [
            "remember",
            "recall_memory",
            "frontend_open_browser",
            "browser_research",
            "safe_shell",
            "codex_runtime",
            "capability_gap_backlog",
            "self_extension_plan",
        ],
    }


def get_codex_agent_memory(limit: int = 20) -> dict[str, Any]:
    state = _load_state()
    memory = list(state.get("memory") or [])[: max(1, min(int(limit), 100))]
    conversation = list(state.get("conversation") or [])[: max(1, min(int(limit), 100))]
    return {
        "status": "success",
        "state_path": str(codex_agent_state_path()),
        "memory": memory,
        "conversation": conversation,
        "memory_count": len(state.get("memory", [])),
        "conversation_count": len(state.get("conversation", [])),
    }


def codex_agent_chat(
    message: str,
    approval: str = "",
    auto_extend: bool = False,
    execute: bool = True,
) -> dict[str, Any]:
    """Handle one bounded Codex-agent message and return real action evidence."""
    started = time.time()
    clean_message = str(message or "").strip()
    action_id = str(uuid.uuid4())
    if not clean_message:
        result = _result(action_id, "error", "empty", "Bericht ontbreekt.", started)
        _record_event(result)
        return result

    _append_conversation("user", clean_message)
    memory_matches = _search_memory(clean_message)
    intent = _detect_intent(clean_message)

    if intent["name"] == "remember":
        result = _handle_remember(action_id, clean_message, intent, started)
    elif intent["name"] == "recall_memory":
        result = _result(
            action_id,
            "success",
            "recall_memory",
            "Geheugen opgehaald.",
            started,
            memory_matches=memory_matches,
        )
    elif intent["name"] == "frontend_open_browser":
        result = _handle_frontend_open_browser(action_id, clean_message, intent, approval, started)
    elif intent["name"] == "browser_research":
        result = _handle_browser_research(action_id, clean_message, intent, approval, execute, started)
    elif intent["name"] == "safe_shell":
        result = _handle_safe_shell(action_id, clean_message, intent, approval, execute, started)
    elif intent["name"] == "codex_runtime":
        result = _handle_codex_runtime(action_id, clean_message, intent, approval, execute, started)
    else:
        result = _handle_capability_gap(action_id, clean_message, intent, approval, auto_extend, started)

    result["memory_matches"] = memory_matches
    _append_conversation("assistant", _conversation_summary(result))
    _record_event(result)
    return result


def record_frontend_event(action_id: str, status: str, detail: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "action_id": action_id,
        "tool": "frontend_open_browser",
        "status": str(status or "unknown"),
        "detail": str(detail or ""),
        "payload": payload or {},
        "fake_success": False,
        "source": "ouroboros_cockpit_frontend",
    }
    _append_log_event(event)
    return {"status": "success", "event": event, "event_log_path": str(codex_agent_log_path())}


def _detect_intent(message: str) -> dict[str, Any]:
    text = message.strip()
    urls = URL_RE.findall(text)
    command_match = COMMAND_PREFIX_RE.match(text)
    remember_match = REMEMBER_RE.search(text)
    codex_match = CODEX_RUNTIME_RE.match(text)

    if remember_match:
        return {"name": "remember", "text": remember_match.group(1).strip()}
    if codex_match:
        return {"name": "codex_runtime", "task": codex_match.group(1).strip()}
    if command_match:
        return {"name": "safe_shell", "command": command_match.group(1).strip()}
    if urls and OPEN_BROWSER_RE.search(text):
        return {"name": "frontend_open_browser", "url": urls[0]}
    if urls and READ_BROWSER_RE.search(text):
        return {"name": "browser_research", "url": urls[0], "query": text}
    if any(word in text.lower() for word in ("herinner", "memory", "geheugen", "wat weet je nog")):
        return {"name": "recall_memory"}
    if urls:
        return {"name": "frontend_open_browser", "url": urls[0]}
    return {"name": "capability_gap", "requested_capability": _short_capability_name(text)}


def _handle_remember(action_id: str, message: str, intent: dict[str, Any], started: float) -> dict[str, Any]:
    text = intent.get("text") or message
    item = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "text": _redact(text)[:4000],
        "source": "codex_agent_chat",
    }
    state = _load_state()
    state["memory"] = [item, *list(state.get("memory") or [])][:500]
    _save_state(state)
    return _result(
        action_id,
        "success",
        "remember",
        "Opgeslagen in Codex Agent geheugen.",
        started,
        memory_item=item,
        state_path=str(codex_agent_state_path()),
    )


def _handle_frontend_open_browser(
    action_id: str,
    message: str,
    intent: dict[str, Any],
    approval: str,
    started: float,
) -> dict[str, Any]:
    url = _safe_http_url(intent.get("url") or "")
    if not url:
        return _result(action_id, "error", "frontend_open_browser", "Geen geldige http(s)-URL gevonden.", started)
    if approval != APPROVAL_PHRASE:
        return _result(
            action_id,
            "approval_required",
            "frontend_open_browser",
            "Browser openen vereist Akkoord.",
            started,
            approval_required=True,
            approval_phrase=APPROVAL_PHRASE,
            url=url,
        )
    return _result(
        action_id,
        "requires_frontend",
        "frontend_open_browser",
        "Frontend moet deze URL openen; backend heeft geen GUI-browser.",
        started,
        frontend_action={"type": "open_url", "url": url, "target": "_blank", "action_id": action_id},
        url=url,
        fake_success=False,
    )


def _handle_browser_research(
    action_id: str,
    message: str,
    intent: dict[str, Any],
    approval: str,
    execute: bool,
    started: float,
) -> dict[str, Any]:
    if not execute:
        return _result(action_id, "planned", "browser_research", "Browser research gepland maar niet uitgevoerd.", started)
    url = _safe_http_url(intent.get("url") or "")
    try:
        from controller.browser_research import browser_research

        observed = browser_research(query=intent.get("query") or message, url=url or None, approval=approval)
    except Exception as exc:
        observed = {"status": "error", "reason": f"Browser research faalde: {exc}", "browser_action_performed": False}
    status = "success" if observed.get("status") == "success" else str(observed.get("status") or "error")
    return _result(
        action_id,
        status,
        "browser_research",
        "Browser research uitgevoerd via backend Playwright perimeter.",
        started,
        browser_result=observed,
        fake_success=False,
    )


def _handle_safe_shell(
    action_id: str,
    message: str,
    intent: dict[str, Any],
    approval: str,
    execute: bool,
    started: float,
) -> dict[str, Any]:
    command = str(intent.get("command") or "").strip()
    if not execute:
        return _result(action_id, "planned", "safe_shell", "Shell commando gepland maar niet uitgevoerd.", started, command=command)
    shell_result = run_safe_shell(command, approval=approval, timeout=20)
    return _result(
        action_id,
        shell_result.get("status", "error"),
        "safe_shell",
        "Uitgevoerd via safe_shell in Docker workspace.",
        started,
        command=command,
        shell_result=shell_result,
        fake_success=False,
    )


def _handle_codex_runtime(
    action_id: str,
    message: str,
    intent: dict[str, Any],
    approval: str,
    execute: bool,
    started: float,
) -> dict[str, Any]:
    task = str(intent.get("task") or message or "").strip()
    if not task:
        return _result(action_id, "error", "codex_runtime", "Codex taak ontbreekt.", started)
    if not execute:
        return _result(
            action_id,
            "planned",
            "codex_runtime",
            "Codex runtime job gepland maar niet gestart.",
            started,
            task=_redact(task),
        )
    if approval != APPROVAL_PHRASE:
        return _result(
            action_id,
            "approval_required",
            "codex_runtime",
            "Codex runtime vereist Akkoord.",
            started,
            approval_required=True,
            approval_phrase=APPROVAL_PHRASE,
            task=_redact(task),
        )

    try:
        from controller.agent_runtime.orchestrator import get_orchestrator
        from controller.slash_agent_router import _agent_prompt

        record = get_orchestrator().submit(
            agent="codex",
            task=task,
            timeout_seconds=240,
            metadata={
                "source": "codex_agent",
                "action_id": action_id,
                "prompt": _agent_prompt("Codex", task),
            },
        )
    except Exception as exc:
        return _result(
            action_id,
            "error",
            "codex_runtime",
            f"Codex runtime kon niet starten: {exc}",
            started,
            task=_redact(task),
        )

    return _result(
        action_id,
        "running",
        "codex_runtime",
        "Codex job gestart in de agent runtime.",
        started,
        task=_redact(task),
        job=record.to_dict(),
    )


def _handle_capability_gap(
    action_id: str,
    message: str,
    intent: dict[str, Any],
    approval: str,
    auto_extend: bool,
    started: float,
) -> dict[str, Any]:
    gap = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "request": _redact(message),
        "requested_capability": intent.get("requested_capability") or "unknown_capability",
        "status": "pending_implementation",
        "docker_first": True,
        "approval_required_for_code_changes": True,
        "suggested_files": [
            "controller/codex_agent.py",
            "controller/api/trainer_pipeline_routes.py",
            "ouroboros_cockpit/src/App.tsx",
            "sandbox_tests/test_codex_agent.py",
        ],
        "test_command": "python -m unittest sandbox_tests.test_codex_agent",
    }
    backlog = _load_json(codex_agent_backlog_path(), {"gaps": []})
    backlog["gaps"] = [gap, *list(backlog.get("gaps") or [])][:100]
    _save_json(codex_agent_backlog_path(), backlog)

    extension_plan = None
    if auto_extend and approval == APPROVAL_PHRASE:
        extension_plan = _write_self_extension_plan(gap)

    return _result(
        action_id,
        "capability_gap",
        "capability_gap_backlog",
        "Deze opdracht heeft nog geen veilige tool. Gap is vastgelegd voor self-extension.",
        started,
        gap=gap,
        extension_plan=extension_plan,
        backlog_path=str(codex_agent_backlog_path()),
    )


def _write_self_extension_plan(gap: dict[str, Any]) -> dict[str, Any]:
    out_dir = self_improvement_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9_]+", "_", gap["requested_capability"].lower()).strip("_") or "capability"
    path = out_dir / f"{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{slug}.md"
    content = (
        f"# Codex Agent Self-Extension Plan\n\n"
        f"- Gap ID: `{gap['id']}`\n"
        f"- Requested capability: `{gap['requested_capability']}`\n"
        f"- Original request: {gap['request']}\n"
        f"- Docker first: yes\n"
        f"- Approval for code changes: required\n\n"
        f"## Proposed Edit Surface\n"
        + "\n".join(f"- `{item}`" for item in gap["suggested_files"])
        + f"\n\n## Validation\n\n```bash\n{gap['test_command']}\n```\n"
    )
    path.write_text(content, encoding="utf-8")
    return {"status": "written", "path": str(path)}


def _append_conversation(role: str, content: str) -> None:
    state = _load_state()
    item = {"timestamp": datetime.utcnow().isoformat(), "role": role, "content": _redact(content)[:4000]}
    state["conversation"] = [item, *list(state.get("conversation") or [])][:500]
    _save_state(state)


def _search_memory(query: str, limit: int = 5) -> list[dict[str, Any]]:
    words = {word.lower() for word in re.findall(r"[A-Za-z0-9_+-]{3,}", query)}
    if not words:
        return []
    matches = []
    for item in _load_state().get("memory", []):
        text = str(item.get("text") or "")
        score = sum(1 for word in words if word in text.lower())
        if score:
            matches.append({**item, "score": score})
    return sorted(matches, key=lambda item: item.get("score", 0), reverse=True)[:limit]


def _conversation_summary(result: dict[str, Any]) -> str:
    return f"{result.get('tool')}: {result.get('status')} - {result.get('message')}"


def _result(action_id: str, status: str, tool: str, message: str, started: float, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "tool": tool,
        "message": message,
        "action_id": action_id,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "timestamp": datetime.utcnow().isoformat(),
        "fake_success": False,
        "source": "controller.codex_agent",
        "workspace": str(_workspace_root()),
    }
    payload.update(extra)
    return payload


def _record_event(result: dict[str, Any]) -> None:
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "action_id": result.get("action_id"),
        "tool": result.get("tool"),
        "status": result.get("status"),
        "message": result.get("message"),
        "duration_ms": result.get("duration_ms"),
        "fake_success": False,
    }
    _append_log_event(event)


def _append_log_event(event: dict[str, Any]) -> None:
    log = _load_json(codex_agent_log_path(), {"events": []})
    log["events"] = [event, *list(log.get("events") or [])][:200]
    _save_json(codex_agent_log_path(), log)


def _load_state() -> dict[str, Any]:
    state = _load_json(codex_agent_state_path(), {"memory": [], "conversation": []})
    state.setdefault("memory", [])
    state.setdefault("conversation", [])
    return state


def _save_state(state: dict[str, Any]) -> None:
    _save_json(codex_agent_state_path(), state)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except Exception:
        return dict(default)


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _safe_http_url(url: str) -> str:
    candidate = str(url or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return candidate


def _redact(text: str) -> str:
    redacted = str(text or "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _short_capability_name(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9_+-]{3,}", text.lower())
    return "_".join(words[:6]) or "unknown_capability"
