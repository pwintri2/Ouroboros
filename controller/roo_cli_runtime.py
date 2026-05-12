"""Roo Code CLI runtime helpers for the Ouroboros cockpit.

The real Roo CLI lives on the host and normally chooses its own provider/API
key configuration.  This adapter keeps Ouroboros in charge: Cockpit supplies
the selected provider/model, this module maps that choice onto Roo CLI flags,
and all mutating Roo runs remain gated by the exact `Akkoord` phrase.

Authentication sources (checked in order):
1. Environment variable for the provider (e.g. OPENAI_API_KEY)
2. API key from the Cockpit api_key_store
3. API key from an AI subscription in subscription_store
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from controller.ouroboros_paths import roo_code_path
except Exception:
    def roo_code_path() -> Path:
        configured = os.getenv("WINTRIP_ROO_CODE_PATH") or os.getenv("WINTRIP_ROO_PATH") or DEFAULT_ROO_ROOT
        return Path(configured).expanduser().resolve()


APPROVAL_PHRASE = "Akkoord"
DEFAULT_ROO_ROOT = "/home/pwintri2/Roo-code"
DEFAULT_ROO_BINARY = "/home/pwintri2/.local/bin/roo"
DEFAULT_NODE_BIN = "/home/pwintri2/.nvm/versions/node/v22.22.2/bin"
MAX_CAPTURE_CHARS = 12000
MAX_PARSE_CHARS = 2_000_000
ROO_MODELS_CACHE_SECONDS = 60

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(ROO_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY)\s*=\s*[^ \n]+"),
    re.compile(r"\b(sk-[A-Za-z0-9._\-]{12,})\b"),
    re.compile(r"\b(AIza[0-9A-Za-z_\-]{12,})\b"),
)

COCKPIT_TO_ROO_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "gemini": "gemini",
    "google": "gemini",
    "ollama": "ollama",
    "openai": "openai-native",
    "openai-native": "openai-native",
    "chatgpt": "openai-native",
    "openrouter": "openrouter",
    "roo": "roo",
    "vercel-ai-gateway": "vercel-ai-gateway",
}

ROO_SUPPORTED_COCKPIT_PROVIDERS: tuple[str, ...] = (
    "ollama",
    "openai",
    "chatgpt",
    "anthropic",
    "claude",
    "google",
    "gemini",
    "openrouter",
    "roo",
)

ROO_API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openai-native": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "roo": "ROO_API_KEY",
    "vercel-ai-gateway": "VERCEL_AI_GATEWAY_API_KEY",
}

_ROO_MODELS_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}


def roo_root() -> Path:
    return roo_code_path()


def host_workspace_root() -> Path:
    configured = os.getenv("WINTRIP_HOST_WORKSPACE") or os.getenv("WINTRIP_PROJECT_ROOT") or os.getenv("WINTRIP_WORKSPACE")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.exists():
            return candidate.resolve()
    fallback = Path("/home/pwintri2/WintripAI")
    return fallback.resolve() if fallback.exists() else Path.cwd().resolve()


def runtime_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    extras = [
        str(Path(os.getenv("WINTRIP_NODE_BIN") or DEFAULT_NODE_BIN).expanduser()),
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".cargo" / "bin"),
    ]
    env["PATH"] = os.pathsep.join([item for item in [*extras, env.get("PATH", "")] if item])
    env.setdefault("WINTRIP_ROO_CODE_PATH", str(roo_root()))
    env.setdefault("WINTRIP_HOST_WORKSPACE", str(host_workspace_root()))
    if extra:
        env.update({key: str(value) for key, value in extra.items() if value is not None})
    return env


def resolve_roo_binary(env: dict[str, str] | None = None) -> Path | None:
    env_map = env or runtime_env()
    configured = os.getenv("WINTRIP_ROO_BINARY") or os.getenv("ROO_BINARY")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path.resolve()
    in_path = shutil.which("roo", path=env_map.get("PATH"))
    if in_path:
        return Path(in_path).resolve()
    fallback = Path(DEFAULT_ROO_BINARY).expanduser()
    return fallback.resolve() if fallback.exists() else None


def map_cockpit_provider(provider: object, model: object = "") -> dict[str, Any]:
    clean_provider = str(provider or "").strip().lower() or "ollama"
    clean_model = str(model or "").strip()
    if clean_provider == "roo-agent":
        clean_provider = "roo"
    if clean_provider == "roo" and clean_model:
        clean_provider = "roo" if _looks_like_roo_cloud_model_id(clean_model) else infer_provider_from_model(clean_model)
    roo_provider = COCKPIT_TO_ROO_PROVIDER.get(clean_provider)
    if not roo_provider:
        return {
            "status": "unsupported",
            "cockpit_provider": clean_provider,
            "cockpit_model": clean_model,
            "reason": f"Roo CLI provider mapping ontbreekt voor Cockpit-provider `{clean_provider}`.",
            "fake_success": False,
        }
    return {
        "status": "mapped",
        "cockpit_provider": clean_provider,
        "cockpit_model": clean_model,
        "roo_provider": roo_provider,
        "api_key_env": ROO_API_KEY_ENV.get(roo_provider, ""),
        "fake_success": False,
    }


def infer_provider_from_model(model: object) -> str:
    text = str(model or "").strip().lower()
    if not text:
        return "ollama"
    if text.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if "claude" in text:
        return "anthropic"
    if "gemini" in text:
        return "google"
    if text.startswith("grok") or "grok-" in text:
        return "xai"
    if text.startswith("mistral"):
        return "mistral"
    if "/" in text and ":" not in text:
        return "openrouter"
    return "ollama"


def cockpit_provider_for_roo_selection(provider: object, model: object = "") -> str:
    clean_provider = str(provider or "").strip().lower()
    if clean_provider in {"", "roo", "roo-agent", "roo_agent", "roo-code"}:
        if _looks_like_roo_cloud_model_id(model):
            return "roo"
        return infer_provider_from_model(model)
    return clean_provider


def roo_api_key_env_for_cockpit_provider(provider: object, model: object = "") -> str:
    provider_map = map_cockpit_provider(cockpit_provider_for_roo_selection(provider, model), model)
    return str(provider_map.get("api_key_env") or "")


def installed_supported_providers(root: Path | None = None) -> list[str]:
    """Read the installed CLI bundle's supported provider list if present."""
    candidates = [
        Path.home() / ".roo" / "cli" / "lib" / "chunk-WNBBLSKE.js",
        (root or roo_root()) / "apps" / "cli" / "src" / "types" / "types.ts",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        found = re.findall(r'"([a-z0-9-]+)"', text)
        providers = [item for item in found if item in set(COCKPIT_TO_ROO_PROVIDER.values()) | {"openai-native"}]
        if providers:
            out: list[str] = []
            seen: set[str] = set()
            for provider in providers:
                if provider not in seen:
                    seen.add(provider)
                    out.append(provider)
            return out
    return []


def roo_cli_status() -> dict[str, Any]:
    env = runtime_env()
    root = roo_root()
    binary = resolve_roo_binary(env)
    node = shutil.which("node", path=env.get("PATH"))
    supported = installed_supported_providers(root)
    version_probe = _run_probe([str(binary), "--version"], env=env, timeout_seconds=8) if binary else _missing_probe("roo binary missing")
    auth_probe = _run_probe([str(binary), "auth", "status"], env=env, timeout_seconds=8) if binary else _missing_probe("roo binary missing")
    node_probe = _run_probe([node, "--version"], env=env, timeout_seconds=4) if node else _missing_probe("node missing")
    runtime_reachable = bool(binary and node and version_probe.get("exit_code") == 0)
    if runtime_reachable:
        status = "available"
    elif binary and not node:
        status = "node_missing"
    elif root.exists():
        status = "configured"
    else:
        status = "missing"
    return {
        "status": status,
        "available": runtime_reachable,
        "runtime_reachable": runtime_reachable,
        "root": str(root),
        "root_exists": root.exists(),
        "binary": str(binary) if binary else "",
        "binary_exists": bool(binary),
        "node": node or "",
        "node_probe": node_probe,
        "version_probe": version_probe,
        "auth_probe": _public_auth_probe(auth_probe),
        "supported_cli_providers": supported,
        "ollama_cli_supported": "ollama" in supported,
        "default_workspace": str(host_workspace_root()),
        "approval_required": True,
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


def roo_cloud_models(*, timeout_seconds: int = 12, max_models: int = 120) -> dict[str, Any]:
    """Return the Roo Cloud model catalog from the authenticated Roo CLI.

    This is intentionally metadata-only: no auth token or full CLI stdout is
    returned to the backend/Cockpit.
    """

    now = time.time()
    cached = _ROO_MODELS_CACHE.get("payload")
    if isinstance(cached, dict) and now - float(_ROO_MODELS_CACHE.get("ts") or 0.0) < ROO_MODELS_CACHE_SECONDS:
        payload = dict(cached)
        payload["models"] = list(cached.get("models") or [])
        payload["cached"] = True
        return payload

    env = runtime_env()
    binary = resolve_roo_binary(env)
    if not binary:
        return {
            "status": "missing",
            "available": False,
            "models": [],
            "model_count": 0,
            "reason": "Roo CLI binary niet gevonden.",
            "secrets_returned": False,
            "fake_success": False,
        }

    started = time.time()
    try:
        proc = subprocess.run(
            [str(binary), "list", "models", "--format", "json"],
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_seconds or 12)),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "available": False,
            "models": [],
            "model_count": 0,
            "reason": "Roo CLI modelcatalogus gaf geen antwoord binnen de timeout.",
            "duration_seconds": round(time.time() - started, 3),
            "secrets_returned": False,
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "error",
            "available": False,
            "models": [],
            "model_count": 0,
            "reason": redact(str(exc))[:1000],
            "duration_seconds": round(time.time() - started, 3),
            "secrets_returned": False,
            "fake_success": False,
        }

    parsed = _parse_json(proc.stdout)
    models = _extract_roo_model_ids(parsed, max_models=max_models)
    status = "online" if proc.returncode == 0 and models else "error"
    reason = "" if status == "online" else (redact(proc.stderr or proc.stdout)[-1000:] or "Roo CLI gaf geen modelcatalogus terug.")
    payload = {
        "status": status,
        "available": status == "online",
        "models": models,
        "model_count": len(models),
        "exit_code": proc.returncode,
        "stderr": redact(proc.stderr[-1000:]),
        "reason": reason,
        "duration_seconds": round(time.time() - started, 3),
        "secrets_returned": False,
        "fake_success": False,
    }
    if status == "online":
        _ROO_MODELS_CACHE["ts"] = time.time()
        _ROO_MODELS_CACHE["payload"] = dict(payload)
    return payload


def build_roo_command(
    *,
    prompt_file: Path,
    workspace: Path,
    cockpit_provider: str,
    model: str,
    mode: str = "code",
    output_format: str = "json",
) -> dict[str, Any]:
    env = runtime_env()
    binary = resolve_roo_binary(env)
    provider_map = map_cockpit_provider(cockpit_provider, model)
    if not binary:
        return {"status": "error", "reason": "Roo CLI binary niet gevonden.", "category": "binary_missing", "fake_success": False}
    if provider_map.get("status") != "mapped":
        return {**provider_map, "status": "error", "category": "provider_unsupported"}
    roo_provider = str(provider_map["roo_provider"])
    command = [
        str(binary),
        "--print",
        "--prompt-file",
        str(prompt_file),
        "--workspace",
        str(workspace),
        "--provider",
        roo_provider,
        "--model",
        str(model or ""),
        "--mode",
        str(mode or "code"),
        "--oneshot",
        "--output-format",
        output_format,
        "--exit-on-error",
    ]
    reasoning_effort = _roo_reasoning_effort(roo_provider, model)
    if reasoning_effort:
        command.extend(["--reasoning-effort", reasoning_effort])
    return {
        "status": "success",
        "command": command,
        "public_command": public_command(command),
        "provider_map": provider_map,
        "fake_success": False,
    }


def run_roo_cli_task(
    *,
    task: str,
    provider: str,
    model: str,
    approval: str,
    workspace: str | Path | None = None,
    output_dir: str | Path | None = None,
    timeout_seconds: int = 600,
    api_key: str = "",
    mode: str = "code",
) -> dict[str, Any]:
    started = time.time()
    if str(approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "reason": "Roo Code CLI mag pas host-/bestandshandelingen uitvoeren na exact Akkoord.",
            "fake_success": False,
        }
    clean_task = str(task or "").strip()
    if not clean_task:
        return {"status": "failed", "reason": "Task is empty.", "category": "empty_task", "fake_success": False}
    workspace_path = _safe_workspace(workspace)
    out_dir = _safe_output_dir(output_dir, workspace_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = out_dir / "roo_prompt.md"
    stdout_file = out_dir / "roo_stdout.log"
    stderr_file = out_dir / "roo_stderr.log"
    output_file = out_dir / "roo_output.json"
    prompt_file.write_text(clean_task, encoding="utf-8")

    command_payload = build_roo_command(
        prompt_file=prompt_file,
        workspace=workspace_path,
        cockpit_provider=provider,
        model=model,
        mode=mode,
    )
    if command_payload.get("status") != "success":
        return {
            **command_payload,
            "duration_seconds": round(time.time() - started, 3),
            "runtime_status": roo_cli_status(),
            "stdout": "",
            "stderr": str(command_payload.get("reason") or ""),
            "fake_success": False,
        }

    provider_map = command_payload.get("provider_map") if isinstance(command_payload.get("provider_map"), dict) else {}
    env_extra: dict[str, str] = {}
    api_key_env = str(provider_map.get("api_key_env") or "")
    key_resolution = resolve_api_key_for_provider(provider, provider_map, explicit_key=api_key)
    resolved_api_key = str(key_resolution.get("key") or "")
    if api_key_env and resolved_api_key:
        env_extra[api_key_env] = resolved_api_key
    env = runtime_env(env_extra)
    command = list(command_payload["command"])
    before = _read_workspace_status(workspace_path)
    try:
        with stdout_file.open("w", encoding="utf-8") as stdout_handle, stderr_file.open("w", encoding="utf-8") as stderr_handle:
            proc = subprocess.Popen(
                command,
                cwd=str(workspace_path),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                env=env,
                start_new_session=True,
            )
            timed_out = False
            try:
                return_code = proc.wait(timeout=max(1, int(timeout_seconds or 600)))
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate(proc)
                return_code = proc.poll()
    except FileNotFoundError as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "reason": str(exc),
            "category": "binary_missing",
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "reason": str(exc),
            "category": "spawn_failed",
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }

    stdout_for_parse = _read_text_for_parse(stdout_file)
    stdout_text = redact(_read_tail(stdout_file))
    stderr_text = redact(_read_tail(stderr_file))
    parsed_output = _parse_json(redact(stdout_for_parse)) or _parse_json(stdout_text)
    try:
        output_file.write_text(json.dumps(parsed_output if parsed_output is not None else {"stdout": stdout_text}, indent=2), encoding="utf-8")
    except Exception:
        pass
    after = _read_workspace_status(workspace_path)
    changed_files = _changed_status_paths(before, after)
    status = "failed" if timed_out or return_code else "completed"
    response_preview = _response_preview(parsed_output, stdout_for_parse or stdout_text, stderr_text)
    category = _classify_result(
        status=status,
        exit_code=return_code,
        stderr=stderr_text,
        details=f"{stdout_text}\n{response_preview}",
    )
    return {
        "status": status,
        "exit_code": return_code,
        "category": category,
        "timed_out": timed_out,
        "duration_seconds": round(time.time() - started, 3),
        "command": command_payload["public_command"],
        "provider_map": provider_map,
        "api_key_available": bool(key_resolution.get("usable")),
        "api_key_source": str(key_resolution.get("source") or "none"),
        "secrets_returned": False,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "parsed_output": parsed_output,
        "response_preview": response_preview,
        "changed_files": changed_files,
        "dirty_files": [item.get("path", "") for item in (after or []) if item.get("path")],
        "artifacts": [str(path) for path in (prompt_file, stdout_file, stderr_file, output_file) if path.exists()],
        "runtime_status": roo_cli_status(),
        "fake_success": False,
    }


def roo_auth_login(*, approval: str, timeout_seconds: int = 10) -> dict[str, Any]:
    """Launch the Roo Code Cloud auth flow on the host.

    The command is intentionally started detached because the CLI may keep
    waiting for the browser callback.  The follow-up status check is
    `roo auth status` via `roo_cli_status()`.
    """

    if str(approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "reason": "Roo Cloud login wijzigt host-authenticatie en vereist exact Akkoord.",
            "fake_success": False,
        }
    env = runtime_env()
    binary = resolve_roo_binary(env)
    if not binary:
        return {"status": "failed", "reason": "Roo CLI binary niet gevonden.", "category": "binary_missing", "fake_success": False}

    preflight_status = roo_cli_status()
    preflight_auth = preflight_status.get("auth_probe") if isinstance(preflight_status.get("auth_probe"), dict) else {}
    if preflight_auth.get("logged_in_hint"):
        return {
            "status": "completed",
            "exit_code": 0,
            "logged_in": True,
            "reason": "Roo Cloud is al ingelogd; geen nieuwe browserflow nodig.",
            "auth_url": "",
            "frontend_action": None,
            "stdout_summary": str(preflight_auth.get("stdout") or "")[:500],
            "stderr_summary": "",
            "command": [str(binary), "auth", "status"],
            "duration_seconds": 0.0,
            "runtime_status": preflight_status,
            "artifacts": [],
            "secrets_returned": False,
            "fake_success": False,
        }

    out_dir = host_workspace_root() / "out" / "roo_auth"
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_file = out_dir / "roo_auth_login_stdout.log"
    stderr_file = out_dir / "roo_auth_login_stderr.log"
    command = [str(binary), "auth", "login"]
    started = time.time()
    try:
        with stdout_file.open("w", encoding="utf-8") as stdout_handle, stderr_file.open("w", encoding="utf-8") as stderr_handle:
            proc = subprocess.Popen(
                command,
                cwd=str(host_workspace_root()),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                env=env,
                start_new_session=True,
            )
        try:
            return_code = proc.wait(timeout=max(1, int(timeout_seconds or 10)))
        except subprocess.TimeoutExpired:
            return_code = None
    except Exception as exc:
        return {
            "status": "failed",
            "reason": redact(str(exc))[:1000],
            "category": "spawn_failed",
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }

    status_payload = roo_cli_status()
    auth_probe = status_payload.get("auth_probe") if isinstance(status_payload.get("auth_probe"), dict) else {}
    logged_in = bool(auth_probe.get("logged_in_hint"))
    stdout_text = redact(_read_tail(stdout_file, limit=8000))
    stderr_text = redact(_read_tail(stderr_file, limit=4000))
    auth_url = _extract_auth_url(f"{stdout_text}\n{stderr_text}")
    frontend_action = (
        {"type": "open_url", "url": auth_url, "target": "_blank", "source": "roo_auth_login"}
        if auth_url
        else None
    )
    return {
        "status": "completed" if return_code == 0 or logged_in else "launched",
        "exit_code": return_code,
        "logged_in": logged_in,
        "reason": "Roo Cloud login gestart; rond de browserflow af en refresh daarna de modelcatalogus." if return_code is None and not logged_in else "",
        "auth_url": auth_url,
        "frontend_action": frontend_action,
        "stdout_summary": _summarize_auth_output(stdout_text),
        "stderr_summary": _summarize_auth_output(stderr_text),
        "command": public_command(command),
        "duration_seconds": round(time.time() - started, 3),
        "runtime_status": status_payload,
        "artifacts": [str(stdout_file), str(stderr_file)],
        "secrets_returned": False,
        "fake_success": False,
    }


def redact(text: object) -> str:
    redacted = str(text or "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def public_command(command: list[str]) -> list[str]:
    public: list[str] = []
    replacement_for_next = ""
    for item in command:
        if replacement_for_next:
            public.append(replacement_for_next)
            replacement_for_next = ""
            continue
        text = str(item)
        if text == "--prompt-file":
            public.append(text)
            replacement_for_next = "[REDACTED_PATH]"
        elif text in {"--api-key", "-k"}:
            public.append(text)
            replacement_for_next = "[REDACTED]"
        else:
            public.append(redact(text)[:260])
    return public


def _safe_workspace(workspace: str | Path | None) -> Path:
    path = Path(workspace).expanduser() if workspace else host_workspace_root()
    if str(path) == "/workspace":
        return host_workspace_root()
    if str(path).startswith("/workspace/"):
        candidate = host_workspace_root() / str(path).removeprefix("/workspace/")
        if candidate.exists():
            return candidate.resolve()
    if not path.exists():
        return host_workspace_root()
    resolved = path.resolve()
    allowed = [host_workspace_root(), roo_root(), Path("/home/pwintri2").resolve()]
    if not any(str(resolved).startswith(str(root)) for root in allowed if root.exists()):
        return host_workspace_root()
    return resolved


def _safe_output_dir(output_dir: str | Path | None, workspace_path: Path) -> Path:
    if not output_dir:
        return workspace_path / "out" / "roo_cli_runtime"
    raw = Path(output_dir).expanduser()
    raw_text = str(raw)
    if raw_text == "/workspace" or raw_text.startswith("/workspace/"):
        raw = host_workspace_root() / raw_text.removeprefix("/workspace/").lstrip("/")
    resolved = raw.resolve()
    allowed = [workspace_path.resolve(), host_workspace_root(), Path("/home/pwintri2").resolve()]
    if not any(str(resolved).startswith(str(root)) for root in allowed if root.exists()):
        return workspace_path / "out" / "roo_cli_runtime"
    return resolved


def _run_probe(command: list[str], *, env: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds, env=env, check=False)
        return {
            "status": "available" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": redact(proc.stdout[-2000:]),
            "stderr": redact(proc.stderr[-2000:]),
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "missing",
            "exit_code": None,
            "stdout": "",
            "stderr": redact(str(exc)),
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }


def _missing_probe(reason: str) -> dict[str, Any]:
    return {"status": "missing", "exit_code": None, "stdout": "", "stderr": reason, "fake_success": False}


def _public_auth_probe(probe: dict[str, Any]) -> dict[str, Any]:
    stdout = str(probe.get("stdout") or "")
    stderr = str(probe.get("stderr") or "")
    text = f"{stdout}\n{stderr}".lower()
    negative = re.search(r"\b(not\s+authenticated|unauthenticated|not\s+logged\s+in|logged\s+out|invalid|expired|missing)\b", text)
    positive = re.search(r"\b(authenticated|logged\s+in|valid)\b", text)
    logged_in = bool(positive and not negative)
    return {
        "status": probe.get("status"),
        "exit_code": probe.get("exit_code"),
        "logged_in_hint": logged_in,
        "stdout": redact(stdout[-800:]),
        "stderr": redact(stderr[-800:]),
        "fake_success": False,
    }


def _read_tail(path: Path, limit: int = MAX_CAPTURE_CHARS) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return data[-limit:]


def _extract_auth_url(text: str) -> str:
    for match in re.finditer(r"https?://[^\s\"'<>]+", str(text or "")):
        url = match.group(0).rstrip(").,;")
        if "app.roocode.com/cli/sign-in" in url:
            return url
    return ""


def _summarize_auth_output(text: str) -> str:
    clean = re.sub(r"https?://[^\s\"'<>]+", "[AUTH_URL]", str(text or ""))
    return redact(clean)[-1200:]


def _read_text_for_parse(path: Path, limit: int = MAX_PARSE_CHARS) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(data) > limit:
        return data[:limit]
    return data


def _parse_json(text: str) -> Any:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        return None


def _extract_roo_model_ids(parsed: Any, *, max_models: int = 120) -> list[str]:
    raw_models: Any = []
    if isinstance(parsed, dict):
        raw_models = parsed.get("models") or parsed.get("data") or []
    elif isinstance(parsed, list):
        raw_models = parsed

    candidates: list[str] = []
    if isinstance(raw_models, dict):
        candidates = [str(key) for key in raw_models.keys()]
    elif isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                value = item.get("id") or item.get("name") or item.get("model")
                if value:
                    candidates.append(str(value))

    out: list[str] = []
    seen: set[str] = set()
    for model_id in candidates:
        clean = " ".join(str(model_id or "").strip().split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= max(1, int(max_models or 120)):
            break
    return out


def _response_preview(parsed_output: Any, stdout: str, stderr: str) -> str:
    extracted = _extract_roo_response_text(parsed_output)
    if extracted:
        return redact(extracted)[-2000:]
    raw_extracted = _extract_roo_response_text_from_raw(stdout)
    if raw_extracted:
        return redact(raw_extracted)[-2000:]
    if isinstance(parsed_output, dict):
        for key in ("result", "response", "text", "message", "content"):
            value = parsed_output.get(key)
            if value:
                return redact(str(value))[-2000:]
        return redact(json.dumps(parsed_output, ensure_ascii=False))[-2000:]
    return redact(stdout or stderr)[-2000:]


def _extract_roo_response_text_from_raw(text: str) -> str:
    raw = str(text or "")
    match = re.search(r'"type"\s*:\s*"result".{0,400}?"content"\s*:\s*"((?:\\.|[^"\\])*)"', raw, flags=re.S)
    if match:
        try:
            return json.loads(f'"{match.group(1)}"').strip()
        except Exception:
            return match.group(1).strip()
    matches = re.findall(r'"type"\s*:\s*"assistant".{0,1200}?"content"\s*:\s*"((?:\\.|[^"\\])*)"', raw, flags=re.S)
    if matches:
        try:
            return json.loads(f'"{matches[-1]}"').strip()
        except Exception:
            return matches[-1].strip()
    return ""


def _extract_roo_response_text(parsed_output: Any) -> str:
    if isinstance(parsed_output, dict):
        content = parsed_output.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        events = parsed_output.get("events")
        if isinstance(events, list):
            return _extract_last_assistant_content(events)
    if isinstance(parsed_output, list):
        return _extract_last_assistant_content(parsed_output)
    return ""


def _extract_last_assistant_content(events: list[Any]) -> str:
    for item in reversed(events):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "assistant":
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""


def _classify_result(*, status: str, exit_code: int | None, stderr: str, details: str = "") -> str:
    text = f"{stderr or ''}\n{details or ''}".lower()
    if status == "completed":
        return "ok"
    if exit_code is not None and exit_code < 0:
        return "timeout_or_cancelled"
    if "encrypted content is not supported" in text:
        return "model_encrypted_content_unsupported"
    if "invalid provider" in text or "must be one of" in text:
        return "provider_unsupported"
    if "does not support tools" in text:
        return "model_lacks_tool_support"
    if "no api key" in text or "api key" in text or "auth login" in text or "authentication" in text:
        return "auth_or_api_key_missing"
    if exit_code is None:
        return "timeout_or_cancelled"
    return "cli_failed"


def _roo_reasoning_effort(roo_provider: str, model: object) -> str:
    """Return a Roo CLI reasoning flag for provider/model quirks.

    The CLI defaults reasoning effort to medium.  OpenAI's non-reasoning GPT
    models can reject the Responses API request when Roo asks for encrypted
    reasoning content, so disable reasoning explicitly for that family.
    """

    clean_provider = str(roo_provider or "").strip().lower()
    clean_model = str(model or "").strip().lower()
    if clean_provider == "openai-native" and clean_model.startswith(("gpt-4.1", "gpt-4o", "gpt-3.5")):
        return "disabled"
    return ""


def _looks_like_roo_cloud_model_id(model: object) -> bool:
    text = str(model or "").strip().lower()
    if ":" in text or "/" not in text:
        return False
    provider_prefix = text.split("/", 1)[0]
    return provider_prefix in {
        "anthropic",
        "openai",
        "google",
        "meta-llama",
        "x-ai",
        "mistralai",
        "qwen",
        "deepseek",
        "moonshotai",
        "minimax",
        "roo",
        "xai",
        "zai",
    }


def _read_workspace_status(cwd: Path) -> list[dict[str, str]] | None:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    rows: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        rows.append({"status": line[:2].strip(), "path": line[3:].strip()})
    return rows


def _changed_status_paths(before: list[dict[str, str]] | None, after: list[dict[str, str]] | None) -> list[str]:
    if after is None:
        return []
    before_map = {item.get("path", ""): item.get("status", "") for item in before or []}
    changed: list[str] = []
    for item in after:
        path = item.get("path", "")
        if path and before_map.get(path) != item.get("status", ""):
            changed.append(path)
    return changed


def _terminate(proc: Any) -> None:
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Subscription-aware API key resolution
# ---------------------------------------------------------------------------

# Map from Roo CLI provider names to subscription store provider ids
_ROO_PROVIDER_TO_SUBSCRIPTION: dict[str, str] = {
    "anthropic": "anthropic",
    "gemini": "google",
    "openai-native": "openai",
    "openrouter": "openrouter",
}


def resolve_api_key_for_provider(
    cockpit_provider: str,
    provider_map: dict[str, Any] | None = None,
    *,
    explicit_key: str = "",
) -> dict[str, Any]:
    """Resolve the API key for a provider from all available sources.

    Priority order:
    1. Explicitly passed key (from cockpit form)
    2. Environment variable
    3. API key store (cockpit saved keys)
    4. Subscription store (AI subscription credentials)

    Returns a dict with:
    - ``key``: the resolved API key (empty if none found)
    - ``source``: where the key was found
    - ``usable``: bool indicating whether we have a usable key
    """
    if explicit_key and len(explicit_key.strip()) >= 8:
        return {"key": explicit_key.strip(), "source": "explicit", "usable": True}

    if provider_map is None:
        provider_map = map_cockpit_provider(cockpit_provider)
    if provider_map.get("status") != "mapped":
        return {"key": "", "source": "unmapped", "usable": False, "reason": provider_map.get("reason", "")}

    roo_provider = str(provider_map.get("roo_provider") or "")
    api_key_env = str(provider_map.get("api_key_env") or "")
    if roo_provider == "roo":
        if api_key_env:
            env_value = os.getenv(api_key_env, "")
            if env_value:
                return {"key": env_value, "source": "env", "usable": True}
        try:
            status = roo_cli_status()
            auth_probe = status.get("auth_probe") if isinstance(status.get("auth_probe"), dict) else {}
            if auth_probe.get("logged_in_hint"):
                return {"key": "", "source": "roo_auth_login", "usable": True}
        except Exception:
            pass

    # 1. Environment variable
    if api_key_env:
        env_value = os.getenv(api_key_env, "")
        if env_value:
            return {"key": env_value, "source": "env", "usable": True}

    # 2. API key store
    try:
        from controller.api_key_store import load_provider_api_keys

        aliases = {
            "chatgpt": "openai",
            "openai-native": "openai",
            "openai": "openai",
            "claude": "anthropic",
            "anthropic": "anthropic",
            "gemini": "google",
            "google": "google",
        }
        keys = load_provider_api_keys()
        store_provider = aliases.get(str(cockpit_provider or "").strip().lower(), str(cockpit_provider or "").strip().lower())
        store_key = keys.get(store_provider, "")
        if store_key:
            return {"key": store_key, "source": "api_key_store", "usable": True}
    except Exception:
        pass

    # 3. Subscription store
    subscription_provider = _ROO_PROVIDER_TO_SUBSCRIPTION.get(roo_provider, "")
    if not subscription_provider:
        # Try cockpit provider name directly
        subscription_provider = str(cockpit_provider or "").strip().lower()
    try:
        from controller.subscription_store import subscription_api_key_for_provider

        sub_key = subscription_api_key_for_provider(subscription_provider)
        if sub_key:
            return {"key": sub_key, "source": "subscription", "usable": True}
    except Exception:
        pass

    return {"key": "", "source": "none", "usable": False}


def api_key_available_for_provider(cockpit_provider: str, provider_map: dict[str, Any] | None = None) -> bool:
    """Check if an API key is available from any source for the given provider."""
    result = resolve_api_key_for_provider(cockpit_provider, provider_map)
    return result.get("usable", False)


__all__ = [
    "APPROVAL_PHRASE",
    "api_key_available_for_provider",
    "build_roo_command",
    "cockpit_provider_for_roo_selection",
    "infer_provider_from_model",
    "installed_supported_providers",
    "map_cockpit_provider",
    "redact",
    "resolve_api_key_for_provider",
    "resolve_roo_binary",
    "roo_api_key_env_for_cockpit_provider",
    "roo_auth_login",
    "roo_cli_status",
    "roo_cloud_models",
    "roo_root",
    "run_roo_cli_task",
]
