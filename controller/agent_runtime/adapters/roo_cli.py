"""Agent-runtime adapter for Roo Code CLI.

The backend may run in Docker while Roo is installed on the host.  This adapter
therefore prefers the authenticated host bridge when configured, but can also
run Roo locally in tests or host-only deployments.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord
from controller.roo_cli_runtime import (
    map_cockpit_provider,
    redact,
    resolve_api_key_for_provider,
    roo_auth_login,
    roo_cli_status,
    roo_cloud_models,
    run_roo_cli_task,
)


def roo_status(prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge:
        bridged = _bridge_get("/roo/status")
        if bridged is not None:
            bridged["via_bridge"] = True
            return bridged
    status = roo_cli_status()
    status["via_bridge"] = False
    return status


def roo_models(prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge:
        bridged = _bridge_get("/roo/models")
        if bridged is not None:
            bridged["via_bridge"] = True
            return bridged
    result = roo_cloud_models()
    result["via_bridge"] = False
    return result


def roo_login(*, approval: str, prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge:
        bridged = _bridge_post("/roo/auth/login", {"approval": approval, "timeout_seconds": 12})
        if bridged is not None:
            bridged["via_bridge"] = True
            return bridged
    result = roo_auth_login(approval=approval)
    result["via_bridge"] = False
    return result


def roo_cloud_auth_status(prefer_bridge: bool = True) -> dict[str, Any]:
    status = roo_status(prefer_bridge=prefer_bridge)
    auth_probe = status.get("auth_probe") if isinstance(status.get("auth_probe"), dict) else {}
    return {
        "status": "online" if auth_probe.get("logged_in_hint") else "missing",
        "logged_in": bool(auth_probe.get("logged_in_hint")),
        "via_bridge": bool(status.get("via_bridge")),
        "runtime_status": status.get("status"),
        "source": "roo auth login",
        "secrets_returned": False,
        "fake_success": False,
    }


def run_roo_job(
    job: JobRecord,
    log: EventLog,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    metadata = dict(job.metadata or {})
    cockpit_provider = str(metadata.get("cockpit_provider") or metadata.get("provider") or "ollama")
    cockpit_model = str(metadata.get("cockpit_model") or metadata.get("model") or "")
    approval = str(metadata.get("approval") or "")
    mode = str(metadata.get("roo_mode") or "code")
    runtime_status = roo_status(prefer_bridge=True)
    log.append(
        "roo_status",
        {
            "status": runtime_status.get("status"),
            "available": runtime_status.get("available"),
            "root": runtime_status.get("root"),
            "binary": runtime_status.get("binary"),
            "via_bridge": runtime_status.get("via_bridge"),
            "ollama_cli_supported": runtime_status.get("ollama_cli_supported"),
        },
    )
    if on_progress:
        on_progress(
            {
                "commands_run": [f"roo provider={cockpit_provider} model={cockpit_model}"],
                "service_actions": ["roo_cli_dispatch"],
            }
        )

    api_key = _provider_api_key(cockpit_provider, cockpit_model)
    bridged = _bridge_run(
        {
            "task": job.task,
            "provider": cockpit_provider,
            "model": cockpit_model,
            "approval": approval,
            "workspace": job.workspace_root,
            "output_dir": job.output_dir,
            "timeout_seconds": int(job.timeout_seconds or 600),
            "mode": mode,
            "api_key": api_key,
        }
    )
    if bridged is not None and not bridged.get("transport_error"):
        result = bridged
        result["via_bridge"] = True
    elif bridged is not None and bridged.get("transport_error") and _running_in_container():
        result = _bridge_failure_result(bridged)
    else:
        result = run_roo_cli_task(
            task=job.task,
            provider=cockpit_provider,
            model=cockpit_model,
            approval=approval,
            workspace=job.workspace_root,
            output_dir=job.output_dir,
            timeout_seconds=int(job.timeout_seconds or 600),
            api_key=api_key,
            mode=mode,
        )
        result["via_bridge"] = False
        if bridged and bridged.get("transport_error"):
            result["bridge_fallback"] = {key: bridged.get(key) for key in ("status", "reason", "transport_error")}

    _write_artifacts(job, result)
    log.append(
        "roo_finished",
        {
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "category": result.get("category"),
            "via_bridge": result.get("via_bridge"),
        },
    )
    final_status = str(result.get("status") or "failed")
    if final_status in {"success"}:
        final_status = "completed"
    elif final_status == "blocked":
        final_status = "failed"
    elif final_status not in {"completed", "failed", "cancelled"}:
        final_status = "completed" if result.get("exit_code") == 0 else "failed"
    return {
        **result,
        "status": final_status,
        "response_preview": str(result.get("response_preview") or result.get("stdout") or result.get("stderr") or "")[:2000],
        "reason": str(result.get("reason") or result.get("category") or "")[:1000],
    }


def _bridge_failure_result(bridged: dict[str, Any]) -> dict[str, Any]:
    reason = str(bridged.get("reason") or "Host bridge Roo call failed.")
    return {
        "status": "failed",
        "exit_code": None,
        "category": "bridge_unavailable",
        "reason": reason,
        "response_preview": reason,
        "stdout": "",
        "stderr": reason,
        "via_bridge": False,
        "bridge_fallback": {key: bridged.get(key) for key in ("status", "reason", "transport_error")},
        "fake_success": False,
    }


def _running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def _provider_api_key(cockpit_provider: str, cockpit_model: str = "") -> str:
    """Load a Cockpit-managed API key transiently without storing it in jobs."""
    try:
        provider_map = map_cockpit_provider(cockpit_provider, cockpit_model)
        result = resolve_api_key_for_provider(cockpit_provider, provider_map)
        return str(result.get("key") or "")
    except Exception:
        return ""


def _write_artifacts(job: JobRecord, result: dict[str, Any]) -> None:
    try:
        Path(job.stdout_file).write_text(redact(result.get("stdout") or ""), encoding="utf-8")
    except Exception:
        pass
    try:
        Path(job.stderr_file).write_text(redact(result.get("stderr") or result.get("reason") or ""), encoding="utf-8")
    except Exception:
        pass
    try:
        Path(job.output_file).write_text(str(result.get("response_preview") or ""), encoding="utf-8")
    except Exception:
        pass


def _bridge_get(path: str) -> dict[str, Any] | None:
    base_url, token = _bridge_config()
    if not base_url or not token:
        return None
    try:
        request = urllib.request.Request(
            f"{base_url}{path}",
            headers={"X-Ouroboros-Bridge-Token": token},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _bridge_run(body: dict[str, Any]) -> dict[str, Any] | None:
    base_url, token = _bridge_config()
    if not base_url or not token:
        return None
    safe_body = {key: value for key, value in body.items() if key != "api_key" or value}
    data = json.dumps(safe_body).encode("utf-8")
    try:
        request = urllib.request.Request(
            f"{base_url}/roo/run",
            data=data,
            headers={"Content-Type": "application/json", "X-Ouroboros-Bridge-Token": token},
            method="POST",
        )
        timeout = max(10, min(int(body.get("timeout_seconds") or 600) + 10, 3700))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"status": "error", "reason": str(exc), "fake_success": False}
    except Exception as exc:
        return {
            "status": "bridge_unavailable",
            "reason": f"Host bridge Roo call failed: {exc}",
            "transport_error": True,
            "fake_success": False,
        }


def _bridge_post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    base_url, token = _bridge_config()
    if not base_url or not token:
        return None
    data = json.dumps(body).encode("utf-8")
    try:
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "X-Ouroboros-Bridge-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"status": "error", "reason": str(exc), "fake_success": False}
    except Exception as exc:
        return {"status": "bridge_unavailable", "reason": f"Host bridge Roo call failed: {exc}", "transport_error": True, "fake_success": False}


def _bridge_config() -> tuple[str, str]:
    base_url = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
    if not base_url or not token_path:
        return "", ""
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except Exception:
        token = ""
    return base_url, token


__all__ = ["roo_cloud_auth_status", "roo_login", "roo_models", "roo_status", "run_roo_job"]
