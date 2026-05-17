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
    APPROVAL_PHRASE,
    ROO_FALLBACK_MODEL,
    ROO_FALLBACK_PROVIDER,
    map_cockpit_provider,
    redact,
    resolve_api_key_for_provider,
    roo_auth_login,
    roo_cli_status,
    roo_cloud_models,
    run_roo_cli_task,
)


ROO_EDITOR_EVENT_LIMIT = 120


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
    catalog = roo_models(prefer_bridge=prefer_bridge)
    catalog_status = str(catalog.get("status") or "").lower()
    catalog_reason = str(catalog.get("reason") or catalog.get("stderr") or "")
    catalog_ready = bool(catalog.get("available") or catalog.get("models"))
    catalog_rejected = catalog_status in {"error", "failed"} and any(
        marker in catalog_reason.lower()
        for marker in ("token is not valid", "authentication", "http 410", "hasapikey: false", "api key")
    )
    logged_in = bool(catalog_ready or (auth_probe.get("logged_in_hint") and not catalog_rejected))
    return {
        "status": "online" if logged_in else ("invalid" if auth_probe.get("logged_in_hint") else "missing"),
        "logged_in": logged_in,
        "via_bridge": bool(status.get("via_bridge")),
        "runtime_status": status.get("status"),
        "catalog_status": catalog.get("status"),
        "reason": (
            "Roo auth heeft lokaal een token, maar Roo Cloud accepteert het niet meer; voer `roo auth login` opnieuw uit."
            if auth_probe.get("logged_in_hint") and catalog_rejected
            else str(catalog.get("reason") or "")
        ),
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
    requested_provider = str(metadata.get("cockpit_provider") or metadata.get("provider") or "ollama")
    requested_model = str(metadata.get("cockpit_model") or metadata.get("model") or "")
    provider_map = map_cockpit_provider(requested_provider, requested_model)
    cockpit_provider = str(provider_map.get("cockpit_provider") or requested_provider)
    cockpit_model = str(provider_map.get("model_override") or provider_map.get("cockpit_model") or requested_model)
    if provider_map.get("api_key_env") and not resolve_api_key_for_provider(cockpit_provider, provider_map).get("usable"):
        provider_map = map_cockpit_provider(ROO_FALLBACK_PROVIDER, ROO_FALLBACK_MODEL)
        provider_map["fallback_reason"] = (
            f"Roo kan `{cockpit_model}` niet via ChatGPT/OpenAI starten zonder API key; "
            f"lokale fallback `{ROO_FALLBACK_MODEL}` wordt gebruikt."
        )
        cockpit_provider = str(provider_map.get("cockpit_provider") or ROO_FALLBACK_PROVIDER)
        cockpit_model = str(provider_map.get("model_override") or provider_map.get("cockpit_model") or ROO_FALLBACK_MODEL)
    approval = str(metadata.get("approval") or "")
    mode = str(metadata.get("roo_mode") or "code")
    editor_context = {
        "mode": mode,
        "provider": cockpit_provider,
        "model": cockpit_model,
        "requested_provider": requested_provider,
        "requested_model": requested_model,
        "forced_provider": provider_map.get("forced_provider"),
        "forced_model": provider_map.get("forced_model"),
        "model_policy": provider_map.get("model_policy") or "pinned",
        "workspace": job.workspace_root,
        "approval_status": "approved" if approval.strip() == APPROVAL_PHRASE else "missing",
    }
    log.append("roo_editor_started", editor_context)
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
                "service_actions": ["roo_editor_opened", "roo_cli_preflight", "roo_cli_dispatch"],
            }
        )

    api_key = _provider_api_key(cockpit_provider, cockpit_model)
    log.append(
        "roo_dispatch",
        {
            "provider": cockpit_provider,
            "model": cockpit_model,
            "mode": mode,
            "via_bridge_preferred": True,
            "api_key_source": "not_required_ollama" if cockpit_provider == "ollama" else "cockpit_secret_store",
        },
    )
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
    _emit_roo_editor_result(result, log, on_progress=on_progress)
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


def _emit_roo_editor_result(
    result: dict[str, Any],
    log: EventLog,
    *,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Expose Roo's CLI output as human-readable editor events.

    Roo's JSON stream shape can vary between CLI versions, so this function
    keeps the contract deliberately small: public event type, optional role/tool,
    a redacted summary, and whether the event looks like a permission prompt.
    """

    public_events = _public_roo_events(result)
    if public_events:
        log.append("roo_event_batch", {"count": len(public_events), "truncated": len(public_events) >= ROO_EDITOR_EVENT_LIMIT})
        for event in public_events:
            log.append("roo_cli_event", event)

    response_preview = str(result.get("response_preview") or "").strip()
    if response_preview:
        log.append("roo_response", {"summary": redact(response_preview)[:2000]})

    changed_files = _string_list(result.get("changed_files"))
    dirty_files = _string_list(result.get("dirty_files"))
    artifacts = _string_list(result.get("artifacts"))
    if changed_files or dirty_files:
        log.append(
            "roo_workspace_changes",
            {
                "changed_files": changed_files[:120],
                "dirty_files": dirty_files[:160],
                "changed_count": len(changed_files),
                "dirty_count": len(dirty_files),
            },
        )
    if artifacts:
        log.append("roo_artifacts", {"artifacts": artifacts[:80], "count": len(artifacts)})

    command = _command_label(result.get("command"))
    progress: dict[str, Any] = {
        "service_actions": _merge_actions(
            ["roo_editor_stream", "roo_cli_finished"],
            ["roo_permission_prompt"] if any(event.get("approval_required") for event in public_events) else [],
        ),
    }
    if command:
        progress["commands_run"] = [command]
    if changed_files:
        progress["changed_files"] = changed_files
    if dirty_files:
        progress["dirty_files"] = dirty_files
    if artifacts:
        progress["artifacts"] = artifacts
    if on_progress:
        try:
            on_progress(progress)
        except Exception:
            pass


def _public_roo_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_events = _extract_roo_events(result.get("parsed_output"))
    public: list[dict[str, Any]] = []
    start_index = max(0, len(raw_events) - ROO_EDITOR_EVENT_LIMIT)
    for index, item in enumerate(raw_events[start_index:], start=start_index):
        event = _public_roo_event(item, index=index)
        if event:
            public.append(event)
    return public


def _extract_roo_events(parsed_output: Any) -> list[Any]:
    if isinstance(parsed_output, dict):
        for key in ("events", "messages", "steps", "actions"):
            value = parsed_output.get(key)
            if isinstance(value, list):
                return value
        return [parsed_output]
    if isinstance(parsed_output, list):
        return parsed_output
    return []


def _public_roo_event(item: Any, *, index: int) -> dict[str, Any]:
    if isinstance(item, dict):
        event_type = str(item.get("type") or item.get("event") or item.get("kind") or item.get("role") or "event")
        role = str(item.get("role") or "")
        tool = str(item.get("tool") or item.get("tool_name") or item.get("name") or item.get("command") or "")
        summary = _event_summary(item)
        keys = sorted(str(key) for key in item.keys())[:16]
        text_for_policy = json.dumps(item, ensure_ascii=False, default=str)
    else:
        event_type = "message"
        role = ""
        tool = ""
        summary = str(item or "")
        keys = []
        text_for_policy = summary
    public = {
        "roo_index": index,
        "roo_type": redact(event_type)[:80] or "event",
        "role": redact(role)[:80],
        "tool": redact(tool)[:160],
        "summary": redact(summary)[:1600],
        "approval_required": _looks_like_permission_prompt(text_for_policy),
        "raw_keys": keys,
    }
    return {key: value for key, value in public.items() if value not in ("", [], None)}


def _event_summary(item: dict[str, Any]) -> str:
    for key in ("summary", "content", "text", "message", "reason", "result", "description"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value not in (None, "", [], {}):
            return json.dumps(value, ensure_ascii=False, default=str)
    compact = {key: value for key, value in item.items() if key not in {"token", "api_key", "secret"}}
    return json.dumps(compact, ensure_ascii=False, default=str)


def _looks_like_permission_prompt(text: str) -> bool:
    lowered = str(text or "").lower()
    markers = (
        "approval",
        "permission",
        "confirm",
        "consent",
        "allow",
        "authorize",
        "toestemming",
        "akkoord",
    )
    return any(marker in lowered for marker in markers)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = redact(str(item or "")).strip()
        if text:
            out.append(text[:1000])
    return out


def _command_label(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(redact(str(part or "")) for part in value if str(part or "").strip())[:2000]
    if isinstance(value, str):
        return redact(value)[:2000]
    return ""


def _merge_actions(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    actions: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                actions.append(item)
    return actions


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
    token_path = _bridge_token_path()
    if not token_path:
        return "", ""
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except Exception:
        token = ""
    if not token:
        return "", ""
    for base_url in _bridge_url_candidates():
        if _bridge_url_reachable(base_url, token):
            return base_url, token
    return "", ""


def _bridge_token_path() -> str:
    configured = str(os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH") or "").strip()
    candidates = [
        configured,
        "/workspace/.secrets/rclone_bridge_token",
        str(Path.cwd() / ".secrets" / "rclone_bridge_token"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return configured


def _bridge_url_candidates() -> list[str]:
    configured = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").strip().rstrip("/")
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    if _vps_static_runtime():
        candidates.extend(
            [
                "http://127.0.0.1:18766",
                "http://172.17.0.1:18766",
                "http://host.docker.internal:18766",
            ]
        )
    else:
        candidates.extend(
            [
                "http://127.0.0.1:8766",
                "http://127.0.0.1:8767",
                "http://host.docker.internal:8766",
            ]
        )
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = candidate.rstrip("/")
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _bridge_url_reachable(base_url: str, token: str) -> bool:
    try:
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/roo/status",
            headers={"X-Ouroboros-Bridge-Token": token},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return isinstance(payload, dict) and bool(payload.get("status"))
    except Exception:
        return False


def _vps_static_runtime() -> bool:
    root = Path("/workspace")
    return bool(Path("/.dockerenv").exists() and (root / "Cockpit.html").exists() and (root / "assets").exists())


__all__ = ["roo_cloud_auth_status", "roo_login", "roo_models", "roo_status", "run_roo_job"]
