"""Typed computer-action registry for local and host-bridge operations.

The registry is intentionally small and auditable.  It wraps existing Roo,
safe-shell, world-agent, and host-bridge primitives with one typed action
surface that can be used by ToolBridge and by the authenticated host bridge.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller.safe_shell import run_safe_shell, workspace_root


APPROVAL_PHRASE = "Akkoord"

_SAFE_SECRET_STATUS_KEYS = {
    "fake_success",
    "secret_redaction",
    "secrets_returned",
    "token_configured",
    "tokens_returned",
}
_SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "bearer",
    "password",
    "passwd",
    "token",
    "secret",
)
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|secret|password|passwd|bearer|authorization)\b\s*[:=]\s*['\"]?[^'\"\s,;}]+"
    ),
    re.compile(r"(?i)(Authorization:\s*)[^\r\n]+"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
)

ActionHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ComputerActionSpec:
    """Public metadata plus the private handler for one action."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ActionHandler
    approval_required: bool = False
    side_effect: bool = False
    aliases: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "description": self.description,
            "approval_required": self.approval_required,
            "side_effect": self.side_effect,
            "parameters": dict(self.parameters),
        }


class ComputerActionRegistry:
    """Typed action registry with exact approval and output redaction."""

    def __init__(self, actions: tuple[ComputerActionSpec, ...]) -> None:
        self._actions = actions
        self._by_name: dict[str, ComputerActionSpec] = {}
        for action in actions:
            self._by_name[action.name] = action
            for alias in action.aliases:
                self._by_name[alias] = action

    def has(self, name: str) -> bool:
        return str(name or "").strip() in self._by_name

    def get(self, name: str) -> ComputerActionSpec | None:
        return self._by_name.get(str(name or "").strip())

    def tool_names(self, *, include_aliases: bool = True) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for action in self._actions:
            candidates = (action.name, *action.aliases) if include_aliases else (action.name,)
            for candidate in candidates:
                if candidate not in seen:
                    names.append(candidate)
                    seen.add(candidate)
        return names

    def approval_tool_names(self, *, include_aliases: bool = True) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for action in self._actions:
            if not action.approval_required:
                continue
            candidates = (action.name, *action.aliases) if include_aliases else (action.name,)
            for candidate in candidates:
                if candidate not in seen:
                    names.append(candidate)
                    seen.add(candidate)
        return names

    def side_effect_tool_names(self, *, include_aliases: bool = True) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for action in self._actions:
            if not action.side_effect:
                continue
            candidates = (action.name, *action.aliases) if include_aliases else (action.name,)
            for candidate in candidates:
                if candidate not in seen:
                    names.append(candidate)
                    seen.add(candidate)
        return names

    def status(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "status": "online",
                "actions": [action.public_dict() for action in self._actions],
                "tools": self.tool_names(include_aliases=True),
                "canonical_tools": self.tool_names(include_aliases=False),
                "approval_required_for": self.approval_tool_names(include_aliases=True),
                "side_effect_tools": self.side_effect_tool_names(include_aliases=True),
                "workspace": str(workspace_root()),
                "host_bridge": {
                    "configured": bool(os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").strip()),
                    "token_configured": bool(_bridge_token()),
                },
                "approval_phrase": APPROVAL_PHRASE,
                "secret_redaction": "enabled",
                "secrets_returned": False,
                "fake_success": False,
            }
        )

    def run(self, action_name: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        started = time.time()
        requested = str(action_name or "").strip()
        action = self.get(requested)
        payload = dict(args or {})
        if action is None:
            return _action_result(
                action=requested or "unknown",
                requested_action=requested or "unknown",
                status="rejected",
                reason=f"Computer action not allowed: {requested}",
                started=started,
            )

        if action.approval_required and not _approved(payload.get("approval")):
            return _action_result(
                action=action.name,
                requested_action=requested,
                status="blocked",
                reason="Computer action requires exact approval phrase: Akkoord.",
                result={"approval_required": True, "approval_phrase": APPROVAL_PHRASE},
                started=started,
            )

        try:
            result = action.handler(payload)
        except Exception as exc:
            result = {"status": "error", "reason": str(exc), "stdout": "", "stderr": str(exc), "result": {}}
        return _normalize_action_result(action, requested, result, started)


def get_computer_action_registry() -> ComputerActionRegistry:
    return _REGISTRY


def computer_actions_status() -> dict[str, Any]:
    return get_computer_action_registry().status()


def run_computer_action(action: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return get_computer_action_registry().run(action, args)


def is_computer_action(action: str) -> bool:
    return get_computer_action_registry().has(action)


def redact_secrets(value: Any) -> Any:
    """Redact obvious credential material from nested payloads."""

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            clean_key = str(key)
            if _is_secret_key(clean_key):
                out[clean_key] = "[REDACTED]"
            else:
                out[clean_key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _read_file(args: dict[str, Any]) -> dict[str, Any]:
    from controller import roo_tools

    return roo_tools.read_file(
        path=str(args.get("path") or ""),
        offset=_int_or_none(args.get("offset")),
        limit=_int_or_none(args.get("limit")),
    )


def _list_files(args: dict[str, Any]) -> dict[str, Any]:
    from controller import roo_tools

    return roo_tools.list_files(
        path=str(args.get("path") or "."),
        recursive=_bool(args.get("recursive"), default=False),
        limit=_bounded_int(args.get("limit"), default=200, minimum=1, maximum=1000),
    )


def _search_files(args: dict[str, Any]) -> dict[str, Any]:
    from controller import roo_tools

    regex = str(args.get("regex") or args.get("query") or "").strip()
    if not regex:
        return {"status": "error", "reason": "regex or query is required.", "stdout": "", "stderr": "regex or query is required.", "result": {}}
    return roo_tools.search_files(
        path=str(args.get("path") or "."),
        regex=regex,
        file_pattern=str(args.get("file_pattern") or "") or None,
        limit=_bounded_int(args.get("limit"), default=100, minimum=1, maximum=500),
    )


def _write_file(args: dict[str, Any]) -> dict[str, Any]:
    from controller import roo_tools

    return roo_tools.write_file(
        path=str(args.get("path") or ""),
        content=str(args.get("content") or ""),
        approval=str(args.get("approval") or ""),
    )


def _apply_patch(args: dict[str, Any]) -> dict[str, Any]:
    from controller import roo_tools

    return roo_tools.apply_patch(
        patch=str(args.get("patch") or ""),
        approval=str(args.get("approval") or ""),
    )


def _run_command(args: dict[str, Any]) -> dict[str, Any]:
    return run_safe_shell(
        str(args.get("command") or ""),
        approval=str(args.get("approval") or ""),
        timeout=_bounded_int(args.get("timeout"), default=20, minimum=1, maximum=30),
    )


def _run_tests(args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if command:
        if not _is_test_command(command):
            return {
                "status": "error",
                "reason": "run_tests only accepts pytest or python -m unittest commands.",
                "stdout": "",
                "stderr": "run_tests only accepts pytest or python -m unittest commands.",
                "result": {"command": command},
            }
    else:
        runner = str(args.get("runner") or "unittest").strip().lower()
        selector = str(args.get("selector") or "").strip()
        if selector and not _safe_test_selector(selector):
            return {
                "status": "error",
                "reason": "Test selector contains unsupported characters.",
                "stdout": "",
                "stderr": "Test selector contains unsupported characters.",
                "result": {"selector": selector},
            }
        if runner == "pytest":
            command = "pytest"
            if selector:
                command = f"{command} {shlex.quote(selector)}"
        elif runner in {"unittest", "python-unittest"}:
            command = "python3 -m unittest"
            command = f"{command} {shlex.quote(selector)}" if selector else f"{command} discover -s sandbox_tests"
        else:
            return {
                "status": "error",
                "reason": "Test runner must be unittest or pytest.",
                "stdout": "",
                "stderr": "Test runner must be unittest or pytest.",
                "result": {"runner": runner},
            }

    result = run_safe_shell(
        command,
        approval=str(args.get("approval") or ""),
        timeout=_bounded_int(args.get("timeout"), default=30, minimum=1, maximum=30),
    )
    result.setdefault("result", {})
    if isinstance(result.get("result"), dict):
        result["result"]["test_command"] = command
    return result


def _browser_open_url(args: dict[str, Any]) -> dict[str, Any]:
    from controller.world_agent import open_url_via_world_agent

    return open_url_via_world_agent(
        str(args.get("url") or ""),
        approval=str(args.get("approval") or ""),
        prefer_bridge=_bool(args.get("prefer_bridge"), default=True),
    )


def _host_status(_args: dict[str, Any]) -> dict[str, Any]:
    result = _host_bridge_request("GET", "/computer/status", None, timeout=5)
    if result:
        result["via_bridge"] = True
        return result
    return {
        "status": "unavailable",
        "reason": "Host bridge is not configured or unreachable.",
        "stdout": "",
        "stderr": "",
        "result": {"host_bridge": {"configured": bool(os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").strip())}},
        "fake_success": False,
    }


def _host_open_url(args: dict[str, Any]) -> dict[str, Any]:
    bridge_args = {
        "url": str(args.get("url") or ""),
        "approval": str(args.get("approval") or ""),
        "prefer_bridge": False,
    }
    result = _host_bridge_request(
        "POST",
        "/computer/action",
        {"action": "browser_open_url", "args": bridge_args},
        timeout=10,
    )
    if result:
        result["via_bridge"] = True
        result["host_action"] = "browser_open_url"
        return result
    return {
        "status": "unavailable",
        "reason": "Host bridge is not configured or unreachable.",
        "stdout": "",
        "stderr": "",
        "result": {"url": bridge_args["url"], "tab_opened": False},
        "fake_success": False,
    }


def _host_bridge_request(method: str, path: str, payload: Mapping[str, Any] | None, *, timeout: float) -> dict[str, Any]:
    base_url = os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").strip().rstrip("/")
    token = _bridge_token()
    if not base_url or not token:
        return {}
    data = json.dumps(dict(payload or {})).encode("utf-8") if method == "POST" else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ouroboros-Bridge-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except Exception:
            value = {"status": "error", "reason": str(exc), "fake_success": False}
        if isinstance(value, dict):
            value.setdefault("http_status", exc.code)
            return value
        return {"status": "error", "reason": str(exc), "http_status": exc.code, "fake_success": False}
    except (OSError, TimeoutError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _bridge_token() -> str:
    configured = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "rclone_bridge_token").resolve()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _normalize_action_result(
    action: ComputerActionSpec,
    requested_action: str,
    result: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    raw = result if isinstance(result, dict) else {"status": "success", "stdout": str(result), "stderr": "", "result": {}}
    status = str(raw.get("status") or "unknown")
    stdout = str(raw.get("stdout", ""))
    stderr = str(raw.get("stderr", ""))
    reason = str(raw.get("reason") or stderr or "")
    public_result = raw.get("result")
    if not isinstance(public_result, dict):
        if public_result is not None:
            public_result = {"value": public_result}
        else:
            public_result = {key: value for key, value in raw.items() if key not in {"status", "stdout", "stderr", "reason"}}
    normalized = {
        "status": status,
        "action": action.name,
        "requested_action": requested_action,
        "approval_required": action.approval_required,
        "side_effect": action.side_effect,
        "stdout": stdout,
        "stderr": stderr,
        "reason": reason,
        "result": public_result,
        "raw": raw,
        "duration_seconds": round(time.time() - started, 3),
        "fake_success": False,
        "secrets_returned": False,
    }
    return redact_secrets(normalized)


def _action_result(
    *,
    action: str,
    requested_action: str,
    status: str,
    reason: str = "",
    stdout: str = "",
    stderr: str = "",
    result: dict[str, Any] | None = None,
    started: float,
) -> dict[str, Any]:
    return redact_secrets(
        {
            "status": status,
            "action": action,
            "requested_action": requested_action,
            "approval_required": status == "blocked",
            "stdout": stdout,
            "stderr": stderr or reason,
            "reason": reason or stderr,
            "result": result or {},
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
            "secrets_returned": False,
        }
    )


def _approved(approval: Any) -> bool:
    return str(approval or "").strip() == APPROVAL_PHRASE


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _is_test_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    if parts[0] == "pytest":
        return True
    return len(parts) >= 3 and parts[0] in {"python", "python3"} and parts[1] == "-m" and parts[2] == "unittest"


def _safe_test_selector(selector: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_./:-]+", selector))


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _SAFE_SECRET_STATUS_KEYS:
        return False
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def _redact_text(text: str) -> str:
    redacted = str(text or "")
    redacted = _SECRET_PATTERNS[0].sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[1].sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[2].sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    return redacted


_REGISTRY = ComputerActionRegistry(
    (
        ComputerActionSpec(
            name="read_file",
            aliases=("file_read",),
            description="Read a UTF-8 text file inside the workspace or known agent roots.",
            parameters={"path": "string", "offset": "integer?", "limit": "integer?"},
            handler=_read_file,
        ),
        ComputerActionSpec(
            name="list_files",
            aliases=("file_list",),
            description="List files inside the workspace or known agent roots.",
            parameters={"path": "string?", "recursive": "boolean?", "limit": "integer?"},
            handler=_list_files,
        ),
        ComputerActionSpec(
            name="search_files",
            aliases=("file_search",),
            description="Regex-search text files inside the workspace or known agent roots.",
            parameters={"path": "string?", "regex": "string", "file_pattern": "string?", "limit": "integer?"},
            handler=_search_files,
        ),
        ComputerActionSpec(
            name="write_file",
            aliases=("file_write",),
            description="Write a complete file after exact Akkoord approval.",
            parameters={"path": "string", "content": "string", "approval": "string"},
            handler=_write_file,
            approval_required=True,
            side_effect=True,
        ),
        ComputerActionSpec(
            name="apply_patch",
            aliases=("file_patch",),
            description="Apply a Roo-style patch after exact Akkoord approval.",
            parameters={"patch": "string", "approval": "string"},
            handler=_apply_patch,
            approval_required=True,
            side_effect=True,
        ),
        ComputerActionSpec(
            name="run_command",
            aliases=("safe_shell",),
            description="Run a safe-shell allowlisted command after exact Akkoord approval.",
            parameters={"command": "string", "approval": "string", "timeout": "integer?"},
            handler=_run_command,
            approval_required=True,
            side_effect=True,
        ),
        ComputerActionSpec(
            name="run_tests",
            aliases=("tests_run",),
            description="Run pytest or python -m unittest after exact Akkoord approval.",
            parameters={"selector": "string?", "runner": "unittest|pytest?", "command": "string?", "approval": "string", "timeout": "integer?"},
            handler=_run_tests,
            approval_required=True,
            side_effect=True,
        ),
        ComputerActionSpec(
            name="browser_open_url",
            aliases=("open_browser", "browser_open"),
            description="Open an http(s) URL in the visible browser after exact Akkoord approval.",
            parameters={"url": "string", "approval": "string", "prefer_bridge": "boolean?"},
            handler=_browser_open_url,
            approval_required=True,
            side_effect=True,
        ),
        ComputerActionSpec(
            name="host_status",
            aliases=("host_basic_status",),
            description="Read host computer-action status through the authenticated host bridge.",
            parameters={},
            handler=_host_status,
        ),
        ComputerActionSpec(
            name="host_open_url",
            aliases=("host_browser_open_url",),
            description="Ask the host bridge to open an approved URL in the host browser.",
            parameters={"url": "string", "approval": "string"},
            handler=_host_open_url,
            approval_required=True,
            side_effect=True,
        ),
    )
)

COMPUTER_ACTION_TOOLS: tuple[str, ...] = tuple(_REGISTRY.tool_names(include_aliases=True))
COMPUTER_ACTION_APPROVAL_TOOLS: frozenset[str] = frozenset(_REGISTRY.approval_tool_names(include_aliases=True))
COMPUTER_ACTION_SIDE_EFFECT_TOOLS: frozenset[str] = frozenset(_REGISTRY.side_effect_tool_names(include_aliases=True))
