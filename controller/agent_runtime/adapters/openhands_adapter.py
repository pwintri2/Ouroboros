"""OpenHands adapter for the agent runtime.

OpenHands (https://github.com/All-Hands-AI/OpenHands) ships as a Poetry
project with a FastAPI server, a frontend, and a Docker-based runtime.
Direct in-process invocation is heavyweight, so this adapter:

  - inspects the local OpenHands repo for structural readiness
  - probes whether the OpenHands Python package can at least be imported
    via a short subprocess (no full server startup, no network)
  - probes whether an OpenHands HTTP server is reachable at the configured URL
  - exposes a JobRecord-friendly adapter that submits a `task` file via the
    HTTP server when reachable, otherwise produces a host handoff document

Approval phrase Akkoord is enforced upstream by /api/openhands/run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord
from controller.status_contracts import evidence_status


DEFAULT_OPENHANDS_ROOT = "/home/pwintri2/OpenHands"
DEFAULT_SERVER_URL = "http://localhost:3000"


def openhands_root() -> Path:
    raw = os.getenv("WINTRIP_OPENHANDS_PATH") or DEFAULT_OPENHANDS_ROOT
    return Path(raw).expanduser().resolve()


def openhands_server_url() -> str:
    return str(os.getenv("WINTRIP_OPENHANDS_SERVER_URL") or DEFAULT_SERVER_URL).rstrip("/")


def discover_capabilities(root: Path | None = None) -> dict[str, Any]:
    base = root or openhands_root()
    if not base.exists():
        return {"status": "missing", "root": str(base), "capabilities": [], "skills_count": 0}
    capabilities: list[str] = []
    for label in ("openhands", "frontend", "openhands-ui", "containers", "enterprise", "config.template.toml", "Makefile", "docker-compose.yml"):
        if (base / label).exists():
            capabilities.append(label)
    skills_dir = base / "openhands" / "agenthub"
    skills_count = 0
    if skills_dir.is_dir():
        try:
            skills_count = sum(1 for _ in skills_dir.iterdir() if _.is_dir())
        except Exception:
            skills_count = 0
    return {
        "status": "online" if capabilities else "missing",
        "root": str(base),
        "capabilities": capabilities,
        "skills_count": skills_count,
        "fake_success": False,
    }


def import_probe(*, timeout_seconds: int = 5) -> dict[str, Any]:
    """Verify OpenHands integration without depending on Poetry env.

    Probe ladder:
      1. syntactic AST parse of openhands/__init__.py
      2. dynamic `import openhands` (only succeeds with the full Poetry env)

    The strongest signal determines the status; we never claim `available`
    from disk presence alone.
    """

    import ast

    root = openhands_root()
    init_path = root / "openhands" / "__init__.py"
    if not init_path.exists():
        return {"status": "missing", "reason": "openhands python package not found", "exit_code": None, "duration_ms": 0}

    syntax_ok = False
    syntax_reason = ""
    try:
        ast.parse(init_path.read_text(encoding="utf-8"))
        syntax_ok = True
    except Exception as exc:
        syntax_reason = f"AST parse failed: {exc}"

    env = dict(os.environ)
    pythonpath = env.get("PYTHONPATH", "")
    addition = str(root)
    if addition not in pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = os.pathsep.join([addition, pythonpath]) if pythonpath else addition
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import openhands; print(getattr(openhands, '__file__', '?'))"],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_seconds)),
            env=env,
            check=False,
        )
        import_succeeded = proc.returncode == 0
        import_stdout = (proc.stdout or "").strip()[-300:]
        import_stderr = (proc.stderr or "").strip()[-500:]
        import_exit = proc.returncode
    except subprocess.TimeoutExpired:
        import_succeeded = False
        import_stdout = ""
        import_stderr = "import probe timed out"
        import_exit = None
    except Exception as exc:
        import_succeeded = False
        import_stdout = ""
        import_stderr = str(exc)[:500]
        import_exit = None
    duration_ms = int((time.monotonic() - started) * 1000)

    if import_succeeded:
        return {
            "status": "available",
            "reason": "openhands python package imports cleanly with full deps.",
            "exit_code": 0,
            "stdout": import_stdout,
            "duration_ms": duration_ms,
        }
    if syntax_ok:
        return {
            "status": "configured",
            "reason": "openhands package present and syntactically valid; full Poetry env not installed.",
            "exit_code": import_exit,
            "stderr": import_stderr,
            "duration_ms": duration_ms,
        }
    return {
        "status": "degraded",
        "reason": syntax_reason or "openhands package present but verification failed.",
        "exit_code": import_exit,
        "stderr": import_stderr,
        "duration_ms": duration_ms,
    }


def server_probe(*, timeout_seconds: float = 1.5) -> dict[str, Any]:
    """Try a HEAD/GET against the OpenHands server health URL."""

    base = openhands_server_url()
    candidates = (f"{base}/health", f"{base}/api/options/config", base)
    for url in candidates:
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=max(0.5, float(timeout_seconds))) as response:
                payload = response.read(2048).decode("utf-8", errors="replace")
                return {"status": "online", "url": url, "http_status": response.status, "preview": payload[:200], "fake_success": False}
        except urllib.error.HTTPError as exc:
            return {
                "status": "available" if 100 <= exc.code < 600 else "error",
                "url": url,
                "http_status": exc.code,
                "reason": str(exc)[:200],
                "fake_success": False,
            }
        except Exception:
            continue
    return {"status": "missing", "url": base, "reason": "OpenHands server not reachable.", "fake_success": False}


def openhands_status() -> dict[str, Any]:
    capabilities = discover_capabilities()
    root = openhands_root()
    if not root.exists():
        return {
            "status": "missing",
            "root": str(root),
            "root_exists": False,
            "server_reachable": False,
            "runtime_launch_test": "missing",
            "skills_count": 0,
            "frontend_present": False,
            "fake_success": False,
        }
    import_result = import_probe()
    server_result = server_probe()
    server_reachable = server_result.get("status") in {"online", "available"}
    runtime_status = import_result.get("status")
    frontend_present = (root / "frontend").is_dir() or (root / "openhands-ui").is_dir()
    if server_reachable and runtime_status == "available":
        status = "online"
    elif runtime_status == "available":
        status = "available"
    elif runtime_status == "configured":
        status = "configured"
    elif runtime_status == "degraded":
        status = "degraded"
    else:
        status = "detected"
    return {
        "status": status,
        "root": str(root),
        "root_exists": True,
        "server_reachable": server_reachable,
        "server_probe": server_result,
        "runtime_launch_test": runtime_status,
        "runtime_probe": import_result,
        "skills_count": capabilities.get("skills_count", 0),
        "frontend_present": frontend_present,
        "capabilities": capabilities.get("capabilities", []),
        "reason": (
            "OpenHands python package imports and server reachable." if status == "online"
            else "OpenHands python package imports cleanly; server not running." if status == "available"
            else "OpenHands repo present but runtime not reachable."
        ),
        "fake_success": False,
    }


def openhands_adapter(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Submit a task to OpenHands.

    Strategy:
      1. If the OpenHands HTTP server is reachable, POST the task as a new
         conversation request (best-effort; we do not assume API stability).
      2. Otherwise, write a structured handoff document so an operator can
         pick up the task in the local OpenHands UI.
    """

    server = server_probe()
    log.append("openhands_server_probe", server)
    if server.get("status") in {"online", "available"}:
        return _submit_to_server(job, log, server)
    return _write_handoff(job, log, server)


def _submit_to_server(job: JobRecord, log: EventLog, server: dict[str, Any]) -> dict[str, Any]:
    base = str(server.get("url") or openhands_server_url()).rsplit("/", 1)[0] or openhands_server_url()
    url = f"{base}/api/conversations"
    payload = json.dumps(
        {"initial_user_msg": job.task, "selected_repository": str(Path(job.workspace_root or "."))[:300]}
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            text = response.read(4096).decode("utf-8", errors="replace")
        log.append("openhands_submit", {"url": url, "http_status": response.status})
        return {
            "status": "completed",
            "exit_code": 0,
            "response_preview": text[-1500:],
            "command": ["POST", url],
            "category": "ok",
        }
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(2048).decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        log.append("openhands_submit_error", {"url": url, "http_status": exc.code, "body": body[-500:]})
        return {"status": "failed", "exit_code": exc.code, "reason": body[-500:], "category": "exec_error"}
    except Exception as exc:
        log.append("openhands_submit_error", {"url": url, "reason": str(exc)[:300]})
        return {"status": "failed", "exit_code": None, "reason": str(exc)[:300], "category": "spawn_failed"}


def _write_handoff(job: JobRecord, log: EventLog, server: dict[str, Any]) -> dict[str, Any]:
    out_path = Path(job.output_dir) / "openhands_handoff.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# OpenHands handoff: {job.job_id}\n\n"
        f"- Created: {datetime.now(timezone.utc).isoformat()}\n"
        f"- Workspace: `{job.workspace_root}`\n"
        f"- Server probe: {server.get('status')} ({server.get('reason') or server.get('url')})\n\n"
        f"## Task\n\n{job.task}\n\n"
        f"## How to pick this up\n\n"
        f"1. Start OpenHands locally (`make run` or docker-compose) at {openhands_server_url()}.\n"
        f"2. Paste the task above into a new conversation.\n"
        f"3. Coordinate via the agent-runtime job log if needed.\n"
    )
    try:
        out_path.write_text(body, encoding="utf-8")
        log.append("openhands_handoff", {"path": str(out_path)})
        return {
            "status": "completed",
            "exit_code": 0,
            "response_preview": body[:1500],
            "category": "ok",
            "handoff": {"path": str(out_path)},
        }
    except Exception as exc:
        log.append("openhands_handoff_error", {"reason": str(exc)[:300]})
        return {"status": "failed", "exit_code": None, "reason": str(exc)[:300], "category": "spawn_failed"}


__all__ = [
    "discover_capabilities",
    "import_probe",
    "openhands_adapter",
    "openhands_root",
    "openhands_server_url",
    "openhands_status",
    "server_probe",
]
