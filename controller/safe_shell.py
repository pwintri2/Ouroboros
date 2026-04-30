# controller/safe_shell.py
# Approval-gated shell execution inside the Docker-contained workspace.

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any


SAFE_COMMANDS = {
    "pwd",
    "ls",
    "find",
    "rg",
    "grep",
    "cat",
    "head",
    "tail",
    "wc",
    "du",
    "df",
    "stat",
    "file",
    "tree",
    "pytest",
    "ruff",
}

SAFE_GIT_SUBCOMMANDS = {"status", "diff", "log", "show", "branch", "rev-parse", "ls-files"}
SAFE_PYTHON_MODULES = {"compileall", "py_compile", "unittest"}
BLOCKED_TOKENS = {"|", "||", "&", "&&", ";", ">", ">>", "<", "`"}
BLOCKED_ARGS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "--fix"}


def workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
    root = Path(configured)
    if not root.exists():
        root = Path.cwd()
    return root.resolve()


def run_safe_shell(command: str, approval: str = "", timeout: int = 20) -> dict[str, Any]:
    started = time.time()
    if approval.strip().lower() != "akkoord":
        return {
            "status": "blocked",
            "approved": False,
            "reason": "Typ Akkoord om een veilig sandbox-commando uit te voeren.",
            "command": command,
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "duration_seconds": 0.0,
            "workspace": str(workspace_root()),
        }

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return _error(command, f"Kan commando niet parsen: {exc}", started)

    if not args:
        return _error(command, "Leeg commando.", started)
    if any(token in BLOCKED_TOKENS or "$(" in token or "${" in token for token in args):
        return _error(command, "Shell operators, redirection en substitutie zijn geblokkeerd.", started)

    root = workspace_root()
    validation_error = _validate_args(args, root)
    if validation_error:
        return _error(command, validation_error, started)

    try:
        proc = subprocess.run(
            args,
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=max(1, min(int(timeout), 30)),
        )
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "approved": True,
            "reason": "Uitgevoerd in Docker-contained workspace.",
            "command": command,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "exit_code": proc.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "workspace": str(root),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "approved": True,
            "reason": "Tijdslimiet overschreden.",
            "command": command,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            "exit_code": None,
            "duration_seconds": round(time.time() - started, 3),
            "workspace": str(root),
        }
    except FileNotFoundError:
        return _error(command, f"Commando niet gevonden: {args[0]}", started)
    except Exception as exc:
        return _error(command, f"Sandbox shell fout: {exc}", started)


def _validate_args(args: list[str], root: Path) -> str | None:
    command = args[0]
    if command in {"python", "python3"}:
        if len(args) < 3 or args[1] != "-m" or args[2] not in SAFE_PYTHON_MODULES:
            return "Python is alleen toegestaan als: python -m compileall|py_compile|unittest ..."
    elif command == "git":
        if len(args) < 2 or args[1] not in SAFE_GIT_SUBCOMMANDS:
            return "Git is alleen read-only toegestaan: status, diff, log, show, branch, rev-parse, ls-files."
    elif command not in SAFE_COMMANDS:
        return f"Commando niet op de whitelist: {command}"

    for token in args[1:]:
        if token in BLOCKED_ARGS:
            return f"Argument niet toegestaan: {token}"
        if token == "--":
            continue
        if token.startswith("-"):
            continue
        if _looks_like_path(token):
            path = (root / token).resolve() if not token.startswith("/") else Path(token).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                return f"Pad valt buiten /workspace: {token}"
    return None


def _looks_like_path(token: str) -> bool:
    return token.startswith(("/", ".", "~")) or "/" in token


def _error(command: str, reason: str, started: float) -> dict[str, Any]:
    return {
        "status": "error",
        "approved": False,
        "reason": reason,
        "command": command,
        "stdout": "",
        "stderr": reason,
        "exit_code": None,
        "duration_seconds": round(time.time() - started, 3),
        "workspace": str(workspace_root()),
    }
