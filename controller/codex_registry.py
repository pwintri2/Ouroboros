"""Safe Codex utility registry.

The registry discovers Python functions in ``/home/pwintri2/Codex`` without
importing modules during listing. Calls are lazy, JSON-only, and run in a short
subprocess so the trainer API is not a generic arbitrary-code execution pipe.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CODEX_PATH = "/home/pwintri2/Codex"
DEFAULT_ALLOWED_SUBDIRS = ("scripts",)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "target",
}
UNSAFE_CALL_NAMES = {"eval", "exec", "compile", "__import__", "open", "input"}
UNSAFE_ATTR_NAMES = {
    "call",
    "check_call",
    "check_output",
    "chmod",
    "chown",
    "kill",
    "mkdir",
    "popen",
    "Popen",
    "remove",
    "rename",
    "rmdir",
    "rmtree",
    "run",
    "system",
    "unlink",
    "write_bytes",
    "write_text",
}
UNSAFE_IMPORTS = {"subprocess", "socket", "http.server", "shutil"}


def codex_root() -> Path:
    return Path(os.getenv("WINTRIP_CODEX_PATH") or DEFAULT_CODEX_PATH).expanduser().resolve()


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
    root = Path(configured)
    if not root.exists():
        root = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return root.resolve()


def codex_monitor_path() -> Path:
    return (_workspace_root() / ".secrets" / "codex_registry_calls.json").resolve()


def list_codex_functions() -> dict[str, Any]:
    """List JSON-callable Codex functions discovered by static AST analysis."""
    root = codex_root()
    if not root.exists():
        return {
            "status": "missing",
            "path": str(root),
            "functions": [],
            "count": 0,
            "callable_count": 0,
            "mount_hint": "Mount the Codex repo read-only and set WINTRIP_CODEX_PATH inside Docker.",
            "skipped": [{"reason": "Codex path does not exist", "path": str(root)}],
        }

    functions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in _candidate_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            skipped.append({"path": str(path), "reason": f"parse_error: {exc}"})
            continue

        module_blocked_reason = _module_blocked_reason(tree)
        module_name = _module_name(root, path)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            record = _function_record(root, path, module_name, node, module_blocked_reason)
            if record:
                if record["callable"]:
                    functions.append(record)
                else:
                    skipped.append(
                        {
                            "path": record["path"],
                            "function": record["function"],
                            "reason": record["blocked_reason"],
                        }
                    )

    functions.sort(key=lambda item: item["name"])
    return {
        "status": "success",
        "path": str(root),
        "allowed_subdirs": list(_allowed_subdirs()),
        "functions": functions,
        "count": len(functions),
        "callable_count": len(functions),
        "skipped": skipped[-100:],
    }


def get_codex_registry_status() -> dict[str, Any]:
    listing = list_codex_functions()
    monitor = get_codex_monitor()
    return {
        "status": listing["status"],
        "path": listing["path"],
        "count": listing["count"],
        "callable_count": listing["callable_count"],
        "allowed_subdirs": listing.get("allowed_subdirs", []),
        "mount_hint": listing.get("mount_hint"),
        "monitor": {
            "total_calls": monitor["total_calls"],
            "success_calls": monitor["success_calls"],
            "error_calls": monitor["error_calls"],
            "last_call_at": monitor["last_call_at"],
            "recent_calls": monitor["recent_calls"][:5],
        },
    }


def get_codex_capability_inventory() -> dict[str, Any]:
    """Return a layered Codex capability inventory.

    The Codex repo is more than a Python function pile: most of it is Rust
    crates plus a Node CLI shim. This inventory honestly distinguishes
    callable Python helpers (handled by `list_codex_functions`) from
    discoverable subsystems that are only invokable via the Codex CLI/MCP/HTTP
    interfaces or that are cloud-only.
    """

    listing = list_codex_functions()
    callable_functions = listing.get("functions", [])
    try:
        from controller.codex_status import discover_codex_capabilities

        repo_inventory = discover_codex_capabilities()
    except Exception as exc:
        repo_inventory = {
            "status": "error",
            "repo_path": str(codex_root()),
            "capabilities": [],
            "summary": {"detected": 0, "total": 0},
            "reason": f"Failed to discover Codex capabilities: {exc}",
        }
    return {
        "status": repo_inventory.get("status") or listing.get("status") or "unknown",
        "repo_path": repo_inventory.get("repo_path") or listing.get("path"),
        "callable_python": {
            "status": listing.get("status"),
            "count": listing.get("count", 0),
            "callable_count": listing.get("callable_count", 0),
            "functions": [
                {
                    "name": item.get("name"),
                    "module": item.get("module"),
                    "function": item.get("function"),
                    "signature": item.get("signature"),
                    "doc": item.get("doc"),
                    "relative_path": item.get("relative_path"),
                }
                for item in callable_functions[:200]
            ],
        },
        "subsystems": repo_inventory.get("capabilities", []),
        "subsystems_summary": repo_inventory.get("summary", {}),
        "rust_workspace": repo_inventory.get("rust_workspace"),
        "fake_success": False,
    }


def call_codex_function(
    name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """Call a registered Codex function in a short JSON-only subprocess."""
    started = time.time()
    args = list(args or [])
    kwargs = dict(kwargs or {})
    timeout_seconds = max(1, min(int(timeout_seconds), 30))
    record: dict[str, Any] | None = None

    try:
        json.dumps({"args": args, "kwargs": kwargs})
    except TypeError as exc:
        response = {"status": "error", "reason": f"Arguments must be JSON serializable: {exc}"}
        _record_call_event(name, args, kwargs, response, started, record)
        return response

    record = _resolve_function(name)
    if not record:
        response = {"status": "error", "reason": f"Codex function not found or not callable: {name}"}
        _record_call_event(name, args, kwargs, response, started, record)
        return response

    payload = {"function": record["name"], "args": args, "kwargs": kwargs}
    env = dict(os.environ)
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or Path.cwd()).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{workspace}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "controller.codex_registry", "--call-worker"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
            cwd=str(workspace),
            check=False,
        )
    except subprocess.TimeoutExpired:
        response = {"status": "timeout", "reason": f"Codex function exceeded {timeout_seconds}s", "function": record["name"]}
        _record_call_event(name, args, kwargs, response, started, record)
        return response

    stdout_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    response_line = stdout_lines[-1] if stdout_lines else "{}"
    try:
        response = json.loads(response_line)
    except json.JSONDecodeError:
        response = {
            "status": "error",
            "reason": "Codex function returned non-JSON output",
            "stdout": proc.stdout[-1000:],
            "stderr": proc.stderr[-1000:],
            "exit_code": proc.returncode,
        }
        _record_call_event(name, args, kwargs, response, started, record)
        return response
    response["duration_ms"] = round((time.time() - started) * 1000, 2)
    if proc.returncode != 0 and response.get("status") == "success":
        response["status"] = "error"
    if proc.stderr:
        response["stderr"] = proc.stderr[-1000:]
    _record_call_event(name, args, kwargs, response, started, record)
    return response


def get_codex_monitor() -> dict[str, Any]:
    path = codex_monitor_path()
    if not path.exists():
        return {
            "status": "empty",
            "path": str(path),
            "total_calls": 0,
            "success_calls": 0,
            "error_calls": 0,
            "last_call_at": None,
            "recent_calls": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "error",
            "path": str(path),
            "total_calls": 0,
            "success_calls": 0,
            "error_calls": 0,
            "last_call_at": None,
            "recent_calls": [],
        }
    recent_calls = list(data.get("recent_calls") or [])
    return {
        "status": "online",
        "path": str(path),
        "total_calls": int(data.get("total_calls") or 0),
        "success_calls": int(data.get("success_calls") or 0),
        "error_calls": int(data.get("error_calls") or 0),
        "last_call_at": data.get("last_call_at"),
        "recent_calls": recent_calls[:50],
    }


def _save_codex_monitor(data: dict[str, Any]) -> None:
    path = codex_monitor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _record_call_event(
    requested_name: str,
    args: list[Any],
    kwargs: dict[str, Any],
    response: dict[str, Any],
    started: float,
    record: dict[str, Any] | None,
) -> None:
    monitor = get_codex_monitor()
    status = str(response.get("status") or "unknown")
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "requested_function": requested_name,
        "function": response.get("function") or (record or {}).get("name") or requested_name,
        "module": (record or {}).get("module"),
        "path": (record or {}).get("path"),
        "status": status,
        "duration_ms": response.get("duration_ms", round((time.time() - started) * 1000, 2)),
        "args_preview": _preview(args),
        "kwargs_keys": sorted(kwargs.keys()),
        "result_preview": _preview(response.get("result")),
        "reason": response.get("reason"),
    }
    recent_calls = [event, *list(monitor.get("recent_calls") or [])][:50]
    total_calls = int(monitor.get("total_calls") or 0) + 1
    success_calls = int(monitor.get("success_calls") or 0) + (1 if status == "success" else 0)
    error_calls = int(monitor.get("error_calls") or 0) + (0 if status == "success" else 1)
    _save_codex_monitor(
        {
            "status": "online",
            "total_calls": total_calls,
            "success_calls": success_calls,
            "error_calls": error_calls,
            "last_call_at": event["timestamp"],
            "recent_calls": recent_calls,
        }
    )


def _preview(value: Any, limit: int = 240) -> Any:
    try:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except TypeError:
        text = repr(value)
    if len(text) <= limit:
        try:
            return json.loads(text)
        except Exception:
            return text
    return text[: limit - 3] + "..."


def _call_codex_function_in_process(name: str, args: list[Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    record = _resolve_function(name)
    if not record:
        return {"status": "error", "reason": f"Codex function not found or not callable: {name}"}

    try:
        spec = importlib.util.spec_from_file_location(f"wintrip_codex_{record['module'].replace('.', '_')}", record["path"])
        if spec is None or spec.loader is None:
            return {"status": "error", "reason": f"Could not load module for {record['name']}"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        func = getattr(module, record["function"])
        result = func(*args, **kwargs)
        json.dumps(result)
        return {"status": "success", "function": record["name"], "result": result}
    except TypeError as exc:
        return {"status": "error", "reason": f"Codex function result/arguments are invalid: {exc}", "function": record["name"]}
    except Exception as exc:
        return {"status": "error", "reason": f"Codex function failed: {exc}", "function": record["name"]}


def _resolve_function(name: str) -> dict[str, Any] | None:
    listing = list_codex_functions()
    functions = listing.get("functions", [])
    by_full_name = {item["name"]: item for item in functions}
    if name in by_full_name:
        return by_full_name[name]
    matches = [item for item in functions if item["function"] == name]
    if len(matches) == 1:
        return matches[0]
    return None


def _candidate_files(root: Path) -> list[Path]:
    files = [path for path in root.glob("*.py") if _is_allowed_file(root, path)]
    for subdir in _allowed_subdirs():
        subdir_path = (root / subdir).resolve()
        if not _is_safe_child(root, subdir_path) or not subdir_path.exists():
            continue
        for path in subdir_path.rglob("*.py"):
            if _is_allowed_file(root, path):
                files.append(path)
    return sorted(set(files))


def _allowed_subdirs() -> tuple[str, ...]:
    configured = os.getenv("WINTRIP_CODEX_ALLOWED_SUBDIRS")
    if configured is None:
        return DEFAULT_ALLOWED_SUBDIRS
    return tuple(part.strip().strip("/") for part in configured.split(",") if part.strip().strip("/"))


def _is_allowed_file(root: Path, path: Path) -> bool:
    if not path.name.endswith(".py") or path.name.startswith("."):
        return False
    if any(part in EXCLUDED_DIR_NAMES or part.startswith(".") for part in path.relative_to(root).parts[:-1]):
        return False
    return _is_safe_child(root, path.resolve())


def _is_safe_child(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _function_record(
    root: Path,
    path: Path,
    module_name: str,
    node: ast.FunctionDef,
    module_blocked_reason: str | None,
) -> dict[str, Any] | None:
    if node.name.startswith("_"):
        return None
    blocked_reason = module_blocked_reason or _function_blocked_reason(node)
    doc = ast.get_docstring(node) or ""
    return {
        "name": f"{module_name}.{node.name}",
        "module": module_name,
        "function": node.name,
        "path": str(path.resolve()),
        "relative_path": str(path.relative_to(root)),
        "signature": _signature(node),
        "doc": doc.splitlines()[0] if doc else "",
        "callable": blocked_reason is None,
        "blocked_reason": blocked_reason,
    }


def _module_blocked_reason(tree: ast.Module) -> str | None:
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in UNSAFE_IMPORTS:
                    return f"module imports unsafe package: {alias.name}"
        if isinstance(node, ast.ImportFrom) and node.module in UNSAFE_IMPORTS:
            return f"module imports unsafe package: {node.module}"
    return None


def _function_blocked_reason(node: ast.FunctionDef) -> str | None:
    if node.name == "main":
        return "entrypoint functions are not exposed"
    if not (ast.get_docstring(node) or _has_type_hints(node)):
        return "function lacks docstring/type hints"
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name) and child.func.id in UNSAFE_CALL_NAMES:
                return f"function calls unsafe builtin: {child.func.id}"
            if isinstance(child.func, ast.Attribute) and child.func.attr in UNSAFE_ATTR_NAMES:
                return f"function calls unsafe operation: {child.func.attr}"
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            return "function performs dynamic import"
    return None


def _has_type_hints(node: ast.FunctionDef) -> bool:
    if node.returns is not None:
        return True
    return any(arg.annotation is not None for arg in [*node.args.args, *node.args.kwonlyargs])


def _signature(node: ast.FunctionDef) -> str:
    parts = []
    defaults_start = len(node.args.args) - len(node.args.defaults)
    for index, arg in enumerate(node.args.args):
        text = arg.arg
        if arg.annotation is not None:
            text += f": {ast.unparse(arg.annotation)}"
        if index >= defaults_start:
            default = node.args.defaults[index - defaults_start]
            text += f" = {ast.unparse(default)}"
        parts.append(text)
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        text = arg.arg
        if arg.annotation is not None:
            text += f": {ast.unparse(arg.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        parts.append(text)
    result = f"{node.name}({', '.join(parts)})"
    if node.returns is not None:
        result += f" -> {ast.unparse(node.returns)}"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex registry worker")
    parser.add_argument("--call-worker", action="store_true")
    args = parser.parse_args(argv)
    if not args.call_worker:
        print(json.dumps(list_codex_functions(), indent=2, sort_keys=True))
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        response = _call_codex_function_in_process(
            str(payload.get("function") or ""),
            list(payload.get("args") or []),
            dict(payload.get("kwargs") or {}),
        )
    except Exception as exc:
        response = {"status": "error", "reason": f"Codex worker failed: {exc}"}
    print(json.dumps(response, sort_keys=True))
    return 0 if response.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
