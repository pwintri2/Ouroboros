"""Runtime doctor for the Ouroboros cockpit harness.

The doctor is intentionally boring: it proves the currently loaded backend,
web preview, host bridge, Chroma runtime, tool registry and canonical router are
reachable before higher agentic promises are treated as ready.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping


DOCTOR_VERSION = "2026-05-09.runtime-harness.v2-docker"
APPROVAL_PHRASE = "Akkoord"
CRITICAL_CHECKS = (
    "backend_http",
    "source_loaded",
    "web_preview",
    "host_bridge",
    "chroma",
    "tool_registry",
    "agentic_router",
    "pending_approval_store",
    "docker_runner",
)


def runtime_doctor_payload(
    *,
    backend_url: str | None = None,
    preview_url: str | None = None,
    bridge_url: str | None = None,
    include_http_backend_check: bool = True,
) -> dict[str, Any]:
    defaults = runtime_defaults(backend_url=backend_url, preview_url=preview_url, bridge_url=bridge_url)
    checks: dict[str, dict[str, Any]] = {
        "source_loaded": _check_source_loaded(),
        "tool_registry": _check_tool_registry(),
        "agentic_router": _check_agentic_router(),
        "chroma": _check_chroma(),
        "pending_approval_store": _check_pending_approval_store(),
        "docker_runner": _check_docker_runner(),
        "codex_gemini": _check_codex_gemini(),
        "last_smoke_test": _check_last_smoke_test(),
    }
    if include_http_backend_check:
        checks["backend_http"] = _check_http_json(f"{defaults['backend_url']}/health", expected_statuses={200})
    else:
        checks["backend_http"] = {"status": "online", "reason": "current FastAPI process is serving this endpoint", "fake_success": False}
    checks["web_preview"] = _check_web_preview(defaults["preview_url"])
    checks["host_bridge"] = _check_host_bridge(defaults["bridge_url"])

    blockers = _runtime_blockers(checks)
    if not blockers and _self_build_runtime_available(checks.get("codex_gemini", {})):
        status = "ready"
    elif any(checks.get(name, {}).get("status") == "failed" for name in ("source_loaded", "tool_registry", "agentic_router", "backend_http")):
        status = "failed"
    elif blockers:
        status = "degraded"
    else:
        status = "degraded"

    return {
        "status": status,
        "version": DOCTOR_VERSION,
        "blockers": blockers,
        "checks": checks,
        "defaults": defaults,
        "ready_requires": list(CRITICAL_CHECKS),
        "approval_phrase": APPROVAL_PHRASE,
        "secrets_returned": False,
        "fake_success": False,
        "ts": time.time(),
    }


def runtime_defaults(*, backend_url: str | None = None, preview_url: str | None = None, bridge_url: str | None = None) -> dict[str, str]:
    in_docker = Path("/.dockerenv").exists()
    return {
        "backend_url": _strip_slash(backend_url or os.getenv("WINTRIP_BACKEND_URL") or "http://127.0.0.1:8010"),
        "preview_url": _strip_slash(preview_url or os.getenv("WINTRIP_WEB_PREVIEW_URL") or ("http://host.docker.internal:1420" if in_docker else "http://127.0.0.1:1420")),
        "bridge_url": _strip_slash(bridge_url or os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or ("http://host.docker.internal:8766" if in_docker else "http://127.0.0.1:8766")),
        "workspace": str(_workspace_root()),
    }


def smoke_result_path() -> Path:
    configured = os.getenv("WINTRIP_RUNTIME_SMOKE_RESULT_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _workspace_root() / ".secrets" / "runtime_smoke_last.json"


def save_smoke_result(result: Mapping[str, Any]) -> dict[str, Any]:
    path = smoke_result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _redact(
        {
            "status": str(result.get("status") or "unknown"),
            "route": str(result.get("route") or ""),
            "tool": str(result.get("tool") or result.get("action") or ""),
            "reason": str(result.get("reason") or result.get("error") or "")[:500],
            "ts": time.time(),
            "fake_success": False,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return {"status": "stored", "path": str(path), "fake_success": False}


def load_last_smoke_result() -> dict[str, Any]:
    path = smoke_result_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "missing", "path": str(path), "reason": str(exc), "fake_success": False}
    if not isinstance(data, dict):
        return {"status": "failed", "path": str(path), "reason": "smoke payload is not an object", "fake_success": False}
    data.setdefault("path", str(path))
    data.setdefault("fake_success", False)
    return _redact(data)


def _check_source_loaded() -> dict[str, Any]:
    try:
        from controller.agentic_intent import classify_agentic_intent

        intent = classify_agentic_intent("toon bestanden in controller")
        module_file = Path(__file__).resolve()
        classifier_file = Path(classify_agentic_intent.__code__.co_filename).resolve()
        git = _git_head(_workspace_root())
        ok = bool(intent.is_agentic and intent.route == "agentic_processor")
        return {
            "status": "online" if ok else "failed",
            "reason": "canonical classifier loaded" if ok else "canonical classifier did not route file action",
            "module_file": str(module_file),
            "classifier_file": str(classifier_file),
            "classifier_mtime": classifier_file.stat().st_mtime if classifier_file.exists() else None,
            "git_head": git.get("head", ""),
            "git_dirty": git.get("dirty", None),
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc), "fake_success": False}


def _check_tool_registry() -> dict[str, Any]:
    required = {"list_files", "search_files", "read_file", "run_command", "run_tests", "browser_open_url", "host_status"}
    try:
        from controller.tool_bridge import TOOL_BRIDGE_TOOLS, tool_bridge_status

        status = tool_bridge_status()
        tools = set(str(item) for item in (status.get("tools") or TOOL_BRIDGE_TOOLS))
        missing = sorted(required - tools)
        return {
            "status": "online" if not missing and status.get("status") == "online" else "failed",
            "reason": "tool registry loaded" if not missing else f"missing tools: {', '.join(missing)}",
            "tool_count": len(tools),
            "missing": missing,
            "write_tools_require_approval": list(status.get("write_tools_require_approval") or []),
            "secret_redaction": status.get("secret_redaction", "unknown"),
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc), "fake_success": False}


def _check_agentic_router() -> dict[str, Any]:
    try:
        from controller.agentic_intent import classify_agentic_intent

        samples = {
            "toon bestanden in controller": "agentic_processor",
            "/codex doe iets": "slash_agent",
            "vertel kort wat Ouroboros is": "normal_chat",
            "Akkoord open https://example.com": "agentic_processor",
        }
        outcomes: dict[str, str] = {}
        blockers: list[str] = []
        for prompt, expected in samples.items():
            intent = classify_agentic_intent(prompt)
            outcomes[prompt] = intent.route
            if intent.route != expected:
                blockers.append(f"{prompt!r} -> {intent.route}, expected {expected}")
        return {
            "status": "online" if not blockers else "failed",
            "reason": "canonical router active" if not blockers else "; ".join(blockers),
            "outcomes": outcomes,
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc), "fake_success": False}


def _check_chroma() -> dict[str, Any]:
    try:
        from controller.chroma_runtime import chroma_runtime_status

        result = chroma_runtime_status(["wintrip_trigger_actions_11d", "wintrip_agentic_sessions_11d"])
        status = "online" if result.get("status") == "online" and result.get("available") else "failed"
        return {
            "status": status,
            "reason": result.get("reason") or ("Chroma reachable" if status == "online" else "Chroma unavailable"),
            "mode": result.get("mode"),
            "remote_url": result.get("remote_url"),
            "persist_dir": result.get("persist_dir"),
            "collections": result.get("collections") or {},
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc), "fake_success": False}


def _check_pending_approval_store() -> dict[str, Any]:
    try:
        from controller.approval_resume import pending_approval_overview, pending_approval_state_path

        overview = pending_approval_overview(limit=5)
        path = pending_approval_state_path()
        return {
            "status": "online" if overview.get("status") == "online" else "failed",
            "reason": "persistent approval store available",
            "path": str(path),
            "count": int(overview.get("count") or 0),
            "records": overview.get("records") or [],
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc), "fake_success": False}


def _check_docker_runner() -> dict[str, Any]:
    """Check Docker daemon availability and safety.

    Docker socket access is equivalent to root on the host. This check ensures:
    - Docker is reachable through CLI or Python SDK
    - a safe read-only container listing can be prepared
    - fails closed if Docker is unavailable
    """
    try:
        from controller.docker_runner import docker_runner_status

        status = docker_runner_status()
        if status.get("status") != "online":
            return {
                "status": "failed",
                "reason": status.get("reason") or "Docker runner unavailable",
                "mode": status.get("metadata", {}).get("mode"),
                "docker_path": status.get("docker_path", ""),
                "docker_client": status.get("docker_client", "unknown"),
                "docker_version": status.get("docker_version", ""),
                "metadata": status.get("metadata") or {"host_root_equivalent": True, "approval_required": True},
                "fake_success": False,
            }

        return {
            "status": "online",
            "reason": "Docker daemon reachable and ready for job dispatch",
            "mode": status.get("metadata", {}).get("mode", "direct_socket"),
            "docker_path": status.get("docker_path", ""),
            "docker_client": status.get("docker_client", "unknown"),
            "docker_version": status.get("docker_version", ""),
            "metadata": {
                "host_root_equivalent": True,
                "approval_required": True,
                "mount_point": "/var/run/docker.sock",
                "security_level": "root_privilege_equivalent",
                "note": "Docker socket access grants host root privileges; all mutating docker actions must be Akkoord-gated.",
            },
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"docker check error: {str(exc)[:200]}",
            "mode": None,
            "metadata": {"host_root_equivalent": True, "approval_required": True},
            "fake_success": False,
        }


def _check_codex_gemini() -> dict[str, Any]:
    codex_candidates = [
        os.getenv("WINTRIP_CODEX_BINARY", ""),
        os.getenv("CODEX_BINARY", ""),
        shutil.which("codex") or "",
    ]
    gemini_candidates = [
        os.getenv("WINTRIP_GEMINI_CLI", ""),
        shutil.which("gemini") or "",
    ]
    codex_path = next((item for item in codex_candidates if item and Path(item).exists()), "")
    gemini_path = next((item for item in gemini_candidates if item and Path(item).exists()), "")
    if codex_path or gemini_path:
        status = "online"
        reason = "self-build executor available"
    else:
        status = "degraded"
        reason = "Codex/Gemini CLI not found; missing-capability build jobs will fail closed"
    return {
        "status": status,
        "reason": reason,
        "codex_available": bool(codex_path),
        "gemini_available": bool(gemini_path),
        "codex_path": codex_path or "",
        "gemini_path": gemini_path or "",
        "fake_success": False,
    }


def _check_last_smoke_test() -> dict[str, Any]:
    result = load_last_smoke_result()
    smoke_status = str(result.get("status") or "")
    if smoke_status in {"success", "completed", "stored"}:
        status = "online"
    elif smoke_status == "missing":
        status = "degraded"
    else:
        status = "failed"
    return {
        "status": status,
        "reason": result.get("reason") or ("latest smoke result loaded" if status == "online" else "no successful smoke test yet"),
        "result": result,
        "fake_success": False,
    }


def _check_web_preview(url: str) -> dict[str, Any]:
    result = _http_request(url, timeout=2.5)
    if result.get("status") != "online":
        reason = str(result.get("reason") or f"{url} unreachable")
        if "403" in reason:
            reason = "preview reachable but Vite rejected the host; restart via scripts/start_ouroboros_preview.sh"
        return {"status": "failed", "reason": reason, "url": url, "fake_success": False}
    body = str(result.get("body") or "")
    current_source_hint = "Ouroboros" in body and ("/src/main.tsx" in body or "/@vite/client" in body or "/assets/" in body)
    return {
        "status": "online" if current_source_hint else "failed",
        "reason": "Vite preview reachable and serving cockpit source" if current_source_hint else "preview route reachable but source hint missing or stale",
        "url": url,
        "http_status": result.get("http_status"),
        "source_hint": current_source_hint,
        "fake_success": False,
    }


def _check_host_bridge(url: str) -> dict[str, Any]:
    token_path = Path(os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH") or (_workspace_root() / ".secrets" / "rclone_bridge_token")).expanduser()
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        return {"status": "failed", "reason": f"host bridge token unavailable: {exc}", "url": url, "token_path": str(token_path), "secrets_returned": False, "fake_success": False}
    if not token:
        return {"status": "failed", "reason": "host bridge token is empty", "url": url, "token_path": str(token_path), "secrets_returned": False, "fake_success": False}
    result = _http_request(f"{url}/computer/status", timeout=2.5, headers={"X-Ouroboros-Bridge-Token": token})
    if result.get("status") != "online":
        reason = str(result.get("reason") or "host bridge unreachable")
        if "404" in reason:
            reason = "stale host bridge: /computer/status ontbreekt; herstart scripts/rclone_host_bridge.py"
        return {"status": "failed", "reason": reason, "url": url, "token_path": str(token_path), "secrets_returned": False, "fake_success": False}
    body = result.get("json") if isinstance(result.get("json"), dict) else {}
    online = body.get("status") == "online"
    return {
        "status": "online" if online else "failed",
        "reason": "host bridge token accepted" if online else str(body.get("reason") or "host bridge returned non-online status"),
        "url": url,
        "token_path": str(token_path),
        "tool_count": len(body.get("tools") or []),
        "host_bridge_runtime": body.get("host_bridge_runtime") or {},
        "secrets_returned": False,
        "fake_success": False,
    }


def _check_http_json(url: str, *, expected_statuses: set[int]) -> dict[str, Any]:
    result = _http_request(url, timeout=2.0)
    status_code = int(result.get("http_status") or 0)
    ok = result.get("status") == "online" and status_code in expected_statuses
    return {
        "status": "online" if ok else "failed",
        "reason": "HTTP route reachable" if ok else result.get("reason") or f"{url} returned {status_code}",
        "url": url,
        "http_status": status_code,
        "json": result.get("json") if isinstance(result.get("json"), dict) else {},
        "fake_success": False,
    }


def _http_request(url: str, *, timeout: float, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(512_000)
            body = raw.decode("utf-8", errors="replace")
            parsed: Any = {}
            try:
                parsed = json.loads(body) if body else {}
            except Exception:
                parsed = {}
            return {
                "status": "online",
                "http_status": response.status,
                "body": body[:2000],
                "json": _redact(parsed) if isinstance(parsed, dict) else {},
                "fake_success": False,
            }
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "http_status": exc.code, "reason": str(exc), "fake_success": False}
    except Exception as exc:
        return {"status": "failed", "http_status": 0, "reason": str(exc), "fake_success": False}


def _runtime_blockers(checks: Mapping[str, Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for name in CRITICAL_CHECKS:
        check = checks.get(name) or {}
        if check.get("status") != "online":
            reason = str(check.get("reason") or "not online")
            blockers.append(f"{name}: {reason}")
    return blockers


def _self_build_runtime_available(check: Mapping[str, Any]) -> bool:
    return bool(check.get("codex_available") or check.get("gemini_available"))


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _strip_slash(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _git_head(root: Path) -> dict[str, Any]:
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root), text=True, capture_output=True, timeout=2, check=False)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), text=True, capture_output=True, timeout=2, check=False)
        return {"head": head.stdout.strip(), "dirty": bool(dirty.stdout.strip())}
    except Exception:
        return {"head": "", "dirty": None}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("token", "secret", "password", "bearer", "api_key", "apikey", "oauth", "session")):
                output[str(key)] = "[REDACTED]"
            else:
                output[str(key)] = _redact(item)
        return output
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    return value
