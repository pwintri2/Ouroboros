"""DeepSeek and Atlas CLI adapters for the agent runtime.

The neighbouring DeepSeek and Atlas repositories are useful as pattern books,
but the cockpit also needs truthful execution paths. This module locates their
CLIs, exposes conservative status probes, and runs approved jobs through the
shared Agent Runtime.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord
from controller.ouroboros_paths import atlas_path, deepseek_path
from controller.status_contracts import run_probe


DEFAULT_DEEPSEEK_ROOT = "/home/pwintri2/deepseek"
DEFAULT_ATLAS_ROOT = "/home/pwintri2/atlas"

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)
URLISH_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>()]+|\b[a-z0-9][a-z0-9.-]*\.(?:nl|com|org|net|io|dev|app)(?:/[^\s<>()]*)?")
FILE_PATH_RE = re.compile(r"(?i)(?:workspace/|wintripai/|out/|\.?/)?[A-Za-z0-9_.\-/]+\.(?:txt|md|json|csv|html|py|log)")
APPROVAL_PHRASE = "Akkoord"


def deepseek_root() -> Path:
    return deepseek_path()


def atlas_root() -> Path:
    return atlas_path()


def ecosystem_agent_status(agent: str, *, prefer_bridge: bool = True) -> dict[str, Any]:
    agent_key = str(agent or "").strip().lower()
    if agent_key == "deepseek":
        return deepseek_status(prefer_bridge=prefer_bridge)
    if agent_key == "atlas":
        return atlas_status(prefer_bridge=prefer_bridge)
    return {"status": "missing", "agent": agent_key, "reason": "Unknown ecosystem agent.", "fake_success": False}


def ecosystem_agent_doctor(agent: str, *, prefer_bridge: bool = True, timeout_seconds: int = 20) -> dict[str, Any]:
    agent_key = str(agent or "").strip().lower()
    if agent_key == "deepseek":
        return deepseek_doctor(prefer_bridge=prefer_bridge, timeout_seconds=timeout_seconds)
    if agent_key == "atlas":
        return atlas_doctor(prefer_bridge=prefer_bridge, timeout_seconds=timeout_seconds)
    return {"status": "missing", "agent": agent_key, "reason": "Unknown ecosystem agent.", "fake_success": False}


def ecosystem_agent_capabilities(agent: str, *, prefer_bridge: bool = True) -> dict[str, Any]:
    agent_key = str(agent or "").strip().lower()
    if prefer_bridge:
        bridge = _bridge_get(f"/{agent_key}/capabilities", timeout=5)
        if bridge:
            bridge["via_bridge"] = True
            bridge.setdefault("fake_success", False)
            return bridge
    if agent_key == "deepseek":
        return discover_deepseek_capabilities()
    if agent_key == "atlas":
        return discover_atlas_capabilities()
    return {"status": "missing", "agent": agent_key, "capabilities": [], "fake_success": False}


def discover_deepseek_capabilities(root: Path | None = None) -> dict[str, Any]:
    base = root or deepseek_root()
    capabilities: list[str] = []
    entrypoints: list[dict[str, str]] = []
    if base.exists():
        for path, label, kind in (
            (base / "README.md", "README", "doc"),
            (base / "docs", "docs", "directory"),
            (base / "npm" / "deepseek-tui" / "bin" / "deepseek-tui.js", "npm TUI wrapper", "script"),
            (base / "npm" / "deepseek-tui" / "bin" / "deepseek.js", "npm wrapper", "script"),
            (base / "npm" / "deepseek-tui" / "bin" / "downloads" / "deepseek-tui", "downloaded TUI binary", "binary"),
            (base / "crates" / "tui" / "Cargo.toml", "tui cargo crate", "manifest"),
            (base / "docs" / "SUBAGENTS.md", "sub-agent role docs", "doc"),
            (base / "docs" / "TOOL_SURFACE.md", "tool surface docs", "doc"),
            (base / "docs" / "deepseek-tui.md", "DeepSeek TUI guide", "doc"),
            (base / "docs" / "deepcode.md", "DeepCode guide", "doc"),
        ):
            if path.exists():
                entrypoints.append({"kind": kind, "label": label, "path": str(path)})
                capabilities.append(label)
    return {
        "status": "online" if base.exists() else "missing",
        "agent": "deepseek",
        "root": str(base),
        "root_exists": base.exists(),
        "capabilities": capabilities,
        "entrypoints": entrypoints,
        "commands": {
            "status": "deepseek-tui --version",
            "doctor": "deepseek-tui --workspace <WintripAI> doctor --json",
            "run": "deepseek-tui --workspace <WintripAI> exec <task> --auto --json",
            "models": "deepseek-tui models --json",
        },
        "fake_success": False,
    }


def discover_atlas_capabilities(root: Path | None = None) -> dict[str, Any]:
    base = root or atlas_root()
    capabilities: list[str] = []
    entrypoints: list[dict[str, str]] = []
    if base.exists():
        for path, label, kind in (
            (base / "packages" / "cli" / "dist" / "launcher.mjs", "built launcher", "script"),
            (base / "packages" / "cli" / "src" / "app.ts", "CLI source", "source"),
            (base / "packages" / "core" / "src" / "builtins" / "index.ts", "built-in agents", "source"),
            (base / "context" / "ai-workflow-rules.md", "AI workflow rules", "doc"),
        ):
            if path.exists():
                entrypoints.append({"kind": kind, "label": label, "path": str(path)})
                capabilities.append(label)
    return {
        "status": "online" if base.exists() else "missing",
        "agent": "atlas",
        "root": str(base),
        "root_exists": base.exists(),
        "capabilities": capabilities,
        "entrypoints": entrypoints,
        "commands": {
            "status": "atlas status --json",
            "doctor": "atlas doctor",
            "ask": "atlas ask <task>",
            "chat": "atlas chat",
        },
        "fake_success": False,
    }


def deepseek_status(*, prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge:
        bridge = _bridge_get("/deepseek/status", timeout=5)
        if bridge:
            bridge["via_bridge"] = True
            bridge.setdefault("fake_success", False)
            return bridge

    root = deepseek_root()
    capabilities = discover_deepseek_capabilities(root)
    env = runtime_env()
    node = node_status(min_major=18, env=env)
    cargo = executable_status("cargo", env=env)
    launcher = resolve_deepseek_launcher(root=root, env=env, allow_cargo=False)
    version_probe = _probe_launcher(launcher, ["--version"], cwd=root, env=env, timeout_seconds=8)
    cargo_manifest = root / "crates" / "tui" / "Cargo.toml"
    cargo_fallback = cargo_manifest.exists() and cargo.get("status") == "available"
    runtime_reachable = version_probe.get("status") == "available"
    if runtime_reachable:
        status = "available"
        reason = "DeepSeek CLI version probe exited cleanly."
    elif root.exists() and (launcher or cargo_fallback):
        status = "configured"
        reason = "DeepSeek source/runtime is present, but no launch probe completed in this backend."
    elif root.exists():
        status = "detected"
        reason = "DeepSeek source tree is mounted, but node/cargo/binary launchers are not available here."
    else:
        status = "missing"
        reason = "DeepSeek root is not visible to this runtime."
    return {
        "status": status,
        "agent": "deepseek",
        "root": str(root),
        "root_exists": root.exists(),
        "runtime_reachable": runtime_reachable,
        "launcher": public_launcher(launcher),
        "version_probe": version_probe,
        "node": node,
        "cargo": cargo,
        "cargo_fallback_available": cargo_fallback,
        "capabilities": capabilities.get("capabilities", []),
        "entrypoints": capabilities.get("entrypoints", []),
        "reason": reason,
        "fake_success": False,
    }


def atlas_status(*, prefer_bridge: bool = True) -> dict[str, Any]:
    if prefer_bridge:
        bridge = _bridge_get("/atlas/status", timeout=5)
        if bridge:
            bridge["via_bridge"] = True
            bridge.setdefault("fake_success", False)
            return bridge

    root = atlas_root()
    capabilities = discover_atlas_capabilities(root)
    env = runtime_env()
    node = node_status(min_major=20, env=env)
    corepack = executable_status("corepack", env=env)
    pnpm = executable_status("pnpm", env=env)
    launcher = resolve_atlas_launcher(root=root, env=env)
    version_probe = _probe_launcher(launcher, ["--version"], cwd=root, env=env, timeout_seconds=8)
    dist_exists = (root / "packages" / "cli" / "dist" / "launcher.mjs").exists()
    source_exists = (root / "packages" / "cli" / "src" / "app.ts").exists()
    runtime_reachable = version_probe.get("status") == "available"
    if runtime_reachable:
        status = "available"
        reason = "Atlas CLI version probe exited cleanly."
    elif root.exists() and source_exists and node.get("status") == "available":
        status = "configured"
        reason = "Atlas source and Node >=20 are present; build/install output is not launchable yet."
    elif root.exists():
        status = "detected"
        reason = "Atlas source tree is mounted, but the built CLI is not available in this runtime."
    else:
        status = "missing"
        reason = "Atlas root is not visible to this runtime."
    return {
        "status": status,
        "agent": "atlas",
        "root": str(root),
        "root_exists": root.exists(),
        "runtime_reachable": runtime_reachable,
        "launcher": public_launcher(launcher),
        "version_probe": version_probe,
        "node": node,
        "corepack": corepack,
        "pnpm": pnpm,
        "dist_exists": dist_exists,
        "source_exists": source_exists,
        "capabilities": capabilities.get("capabilities", []),
        "entrypoints": capabilities.get("entrypoints", []),
        "reason": reason,
        "fake_success": False,
    }


def deepseek_doctor(*, prefer_bridge: bool = True, timeout_seconds: int = 20) -> dict[str, Any]:
    if prefer_bridge:
        bridge = _bridge_get("/deepseek/doctor", timeout=max(5, min(int(timeout_seconds or 20), 30)))
        if bridge:
            bridge["via_bridge"] = True
            bridge.setdefault("fake_success", False)
            return bridge

    root = deepseek_root()
    env = runtime_env()
    launcher = resolve_deepseek_launcher(root=root, env=env, allow_cargo=False)
    if launcher is None:
        status = deepseek_status(prefer_bridge=False)
        return {
            "status": status.get("status") or "missing",
            "agent": "deepseek",
            "root": str(root),
            "reason": "DeepSeek doctor needs a launchable binary or npm wrapper.",
            "runtime_status": status,
            "fake_success": False,
        }
    command = [*launcher["command"], "--workspace", str(_workspace_root()), "doctor", "--json"]
    return _run_short_command("deepseek", "doctor", command, cwd=root, env={**env, **launcher.get("env", {})}, timeout_seconds=timeout_seconds)


def atlas_doctor(*, prefer_bridge: bool = True, timeout_seconds: int = 20) -> dict[str, Any]:
    if prefer_bridge:
        bridge = _bridge_get("/atlas/doctor", timeout=max(5, min(int(timeout_seconds or 20), 30)))
        if bridge:
            bridge["via_bridge"] = True
            bridge.setdefault("fake_success", False)
            return bridge

    root = atlas_root()
    env = runtime_env()
    launcher = resolve_atlas_launcher(root=root, env=env)
    if launcher is None:
        status = atlas_status(prefer_bridge=False)
        return {
            "status": status.get("status") or "missing",
            "agent": "atlas",
            "root": str(root),
            "reason": "Atlas doctor needs a launchable built CLI.",
            "runtime_status": status,
            "fake_success": False,
        }
    command = [*launcher["command"], "doctor"]
    return _run_short_command("atlas", "doctor", command, cwd=root, env={**env, **launcher.get("env", {})}, timeout_seconds=timeout_seconds)


def run_deepseek_job(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    root = deepseek_root()
    env = runtime_env()
    status = deepseek_status(prefer_bridge=False)
    log.append("deepseek_status", status)
    tool_loop = _execute_direct_tool_loop(agent="deepseek", job=job, log=log, on_progress=on_progress, runtime_status=status)
    if tool_loop is not None:
        return tool_loop
    launcher = resolve_deepseek_launcher(
        root=root,
        env=env,
        allow_cargo=True,
        cargo_target_dir=Path(job.output_dir) / "cargo-target" / "deepseek",
    )
    if launcher is None:
        return {
            "status": "failed",
            "exit_code": None,
            "reason": status.get("reason") or "DeepSeek CLI is not launchable.",
            "category": "binary_missing",
            "runtime_status": status,
        }
    prompt = _job_prompt_with_tool_protocol("deepseek", job)
    command = [
        *launcher["command"],
        "--workspace",
        job.workspace_root or str(_workspace_root()),
        "exec",
        prompt,
        "--auto",
        "--json",
    ]
    cli_result = _run_cli_job(
        agent="deepseek",
        job=job,
        log=log,
        on_progress=on_progress,
        command=command,
        cwd=job.workspace_root or str(_workspace_root()),
        env={**env, **launcher.get("env", {})},
        status_payload=status,
    )
    return _execute_cli_declared_tool_loop(agent="deepseek", job=job, log=log, on_progress=on_progress, cli_result=cli_result, runtime_status=status)


def run_atlas_job(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    root = atlas_root()
    env = runtime_env()
    status = atlas_status(prefer_bridge=False)
    log.append("atlas_status", status)
    tool_loop = _execute_direct_tool_loop(agent="atlas", job=job, log=log, on_progress=on_progress, runtime_status=status)
    if tool_loop is not None:
        return tool_loop
    launcher = resolve_atlas_launcher(root=root, env=env)
    if launcher is None:
        return {
            "status": "failed",
            "exit_code": None,
            "reason": status.get("reason") or "Atlas CLI is not launchable.",
            "category": "binary_missing",
            "runtime_status": status,
        }
    prompt = _job_prompt_with_tool_protocol("atlas", job)
    command = [*launcher["command"], "ask"]
    model = _metadata_value(job, "model")
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    cli_result = _run_cli_job(
        agent="atlas",
        job=job,
        log=log,
        on_progress=on_progress,
        command=command,
        cwd=job.workspace_root or str(_workspace_root()),
        env={**env, **launcher.get("env", {})},
        status_payload=status,
    )
    return _execute_cli_declared_tool_loop(agent="atlas", job=job, log=log, on_progress=on_progress, cli_result=cli_result, runtime_status=status)


def resolve_deepseek_launcher(
    *,
    root: Path | None = None,
    env: dict[str, str] | None = None,
    allow_cargo: bool = False,
    cargo_target_dir: Path | None = None,
) -> dict[str, Any] | None:
    base = root or deepseek_root()
    env_map = env or runtime_env()
    configured_tui = os.getenv("WINTRIP_DEEPSEEK_TUI_BINARY") or os.getenv("DEEPSEEK_TUI_BIN")
    if configured_tui and Path(configured_tui).expanduser().exists():
        return {"kind": "tui_binary", "path": str(Path(configured_tui).expanduser()), "command": [str(Path(configured_tui).expanduser())], "env": {}}

    configured = os.getenv("WINTRIP_DEEPSEEK_BINARY") or os.getenv("DEEPSEEK_BINARY")
    if configured and Path(configured).expanduser().exists():
        return {"kind": "binary", "path": str(Path(configured).expanduser()), "command": [str(Path(configured).expanduser())], "env": {}}

    tui_in_path = shutil.which("deepseek-tui", path=env_map.get("PATH"))
    if tui_in_path:
        return {"kind": "tui_path", "path": tui_in_path, "command": [tui_in_path], "env": {}}

    downloaded_tui = base / "npm" / "deepseek-tui" / "bin" / "downloads" / "deepseek-tui"
    if downloaded_tui.exists():
        return {"kind": "downloaded_tui", "path": str(downloaded_tui), "command": [str(downloaded_tui)], "env": {}}

    in_path = shutil.which("deepseek", path=env_map.get("PATH"))
    if in_path:
        return {"kind": "path", "path": in_path, "command": [in_path], "env": {}}

    wrapper = base / "npm" / "deepseek-tui" / "bin" / "deepseek-tui.js"
    node = shutil.which("node", path=env_map.get("PATH"))
    if wrapper.exists() and node:
        return {"kind": "npm_tui_wrapper", "path": str(wrapper), "command": [node, str(wrapper)], "env": {"DEEPSEEK_TUI_QUIET_INSTALL": "1"}}

    dispatcher_wrapper = base / "npm" / "deepseek-tui" / "bin" / "deepseek.js"
    if dispatcher_wrapper.exists() and node:
        return {"kind": "npm_dispatcher_wrapper", "path": str(dispatcher_wrapper), "command": [node, str(dispatcher_wrapper)], "env": {"DEEPSEEK_TUI_QUIET_INSTALL": "1"}}

    manifest = base / "crates" / "tui" / "Cargo.toml"
    cargo = shutil.which("cargo", path=env_map.get("PATH"))
    if allow_cargo and manifest.exists() and cargo:
        cargo_env: dict[str, str] = {}
        if cargo_target_dir:
            cargo_target_dir.mkdir(parents=True, exist_ok=True)
            cargo_env["CARGO_TARGET_DIR"] = str(cargo_target_dir)
        return {
            "kind": "cargo_fallback",
            "path": str(manifest),
            "command": [cargo, "run", "--quiet", "--manifest-path", str(manifest), "--"],
            "env": cargo_env,
        }
    return None


def resolve_atlas_launcher(*, root: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any] | None:
    base = root or atlas_root()
    env_map = env or runtime_env()
    configured = os.getenv("WINTRIP_ATLAS_BINARY") or os.getenv("ATLAS_BINARY")
    if configured and Path(configured).expanduser().exists():
        return {"kind": "binary", "path": str(Path(configured).expanduser()), "command": [str(Path(configured).expanduser())], "env": {}}

    in_path = shutil.which("atlas", path=env_map.get("PATH"))
    if in_path:
        return {"kind": "path", "path": in_path, "command": [in_path], "env": {}}

    node = shutil.which("node", path=env_map.get("PATH"))
    launcher = base / "packages" / "cli" / "dist" / "launcher.mjs"
    if launcher.exists() and node and _node_major(node, env=env_map) >= 20:
        return {"kind": "dist_launcher", "path": str(launcher), "command": [node, str(launcher)], "env": {}}

    bundle = base / "packages" / "cli" / "dist" / "bin" / "atlas.js"
    if bundle.exists() and node and _node_major(node, env=env_map) >= 20:
        return {"kind": "dist_bundle", "path": str(bundle), "command": [node, str(bundle)], "env": {}}
    return None


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    extras = [
        "/home/pwintri2/.nvm/versions/node/v22.22.2/bin",
        str(Path.home() / ".nvm" / "versions" / "node" / "v22.22.2" / "bin"),
        "/home/pwintri2/.cargo/bin",
        str(Path.home() / ".cargo" / "bin"),
        str(Path.home() / ".local" / "bin"),
    ]
    env["PATH"] = os.pathsep.join([item for item in [*extras, env.get("PATH", "")] if item])
    env.setdefault("WINTRIP_HOST_WORKSPACE", str(_workspace_root()))
    _inject_provider_api_keys(env)
    return env


def _inject_provider_api_keys(env: dict[str, str]) -> None:
    """Let ecosystem CLIs use Cockpit-saved API keys without exposing them."""

    if not env.get("DEEPSEEK_API_KEY"):
        deepseek_key = _stored_provider_api_key("deepseek")
        if deepseek_key:
            env["DEEPSEEK_API_KEY"] = deepseek_key


def _stored_provider_api_key(provider: str) -> str:
    try:
        from controller.api_key_store import load_provider_api_keys

        keys = load_provider_api_keys()
        value = str(keys.get(provider) or "")
        if value:
            return value
    except Exception:
        pass
    try:
        from controller.subscription_store import subscription_api_key_for_provider

        return str(subscription_api_key_for_provider(provider) or "")
    except Exception:
        return ""


def node_status(*, min_major: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    env_map = env or runtime_env()
    node = shutil.which("node", path=env_map.get("PATH"))
    if not node:
        return {"status": "missing", "path": None, "version": None, "min_major": min_major}
    probe = run_probe([node, "--version"], env=env_map, timeout_seconds=3)
    version = (probe.stdout or "").strip()
    major = _parse_node_major(version)
    status = "available" if probe.status == "available" and major >= min_major else "configured"
    return {
        "status": status,
        "path": node,
        "version": version,
        "major": major,
        "min_major": min_major,
        "probe": probe.to_dict(),
    }


def executable_status(name: str, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    env_map = env or runtime_env()
    path = shutil.which(name, path=env_map.get("PATH"))
    return {"status": "available" if path else "missing", "path": path, "fake_success": False}


def public_launcher(launcher: dict[str, Any] | None) -> dict[str, Any] | None:
    if not launcher:
        return None
    return {
        "kind": launcher.get("kind"),
        "path": launcher.get("path"),
        "command": [_clip(redact(part), 260) for part in list(launcher.get("command") or [])],
    }


def _run_short_command(
    agent: str,
    tool: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    probe = run_probe(command, cwd=cwd, env=env, timeout_seconds=max(1, min(int(timeout_seconds or 20), 120)))
    stdout = redact(probe.stdout)
    stderr = redact(probe.stderr)
    parsed_json: Any = None
    try:
        parsed_json = json.loads(stdout) if stdout.strip().startswith(("{", "[")) else None
    except Exception:
        parsed_json = None
    return {
        "status": "success" if probe.status == "available" else probe.status,
        "agent": agent,
        "tool": tool,
        "command": [_clip(redact(part), 500) for part in command],
        "cwd": str(cwd),
        "exit_code": probe.exit_code,
        "stdout": stdout[-12000:],
        "stderr": stderr[-12000:],
        "json": parsed_json,
        "duration_seconds": round(time.monotonic() - started, 3),
        "fake_success": False,
    }


def _run_cli_job(
    *,
    agent: str,
    job: JobRecord,
    log: EventLog,
    on_progress: Callable[[dict[str, Any]], None] | None,
    command: list[str],
    cwd: str,
    env: dict[str, str],
    status_payload: dict[str, Any],
) -> dict[str, Any]:
    public_command = [_clip(redact(part), 700) for part in command]
    command_text = " ".join(shlex.quote(part) for part in public_command)
    log.append("command", {"command": public_command, "cwd": cwd})

    workspace_before = read_workspace_status(cwd)
    if workspace_before is not None:
        log.append("workspace_before", {"dirty_count": len(workspace_before), "paths": [item.get("path", "") for item in workspace_before[:80]]})

    stdout_path = Path(job.stdout_file)
    stderr_path = Path(job.stderr_file)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    pid: int | None = None
    started = time.monotonic()
    cancelled = False
    timed_out = False
    return_code: int | None = None
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                env=env,
                start_new_session=True,
            )
            pid = getattr(proc, "pid", None)
            log.append("started", {"pid": pid})
            if on_progress:
                try:
                    on_progress({"pid": pid, "command": public_command})
                except Exception:
                    pass
            cancel_check = getattr(job, "_cancel_check", None)
            deadline = time.monotonic() + max(1, int(job.timeout_seconds or 240))
            while True:
                return_code = proc.poll()
                if return_code is not None:
                    break
                if cancel_check is not None and cancel_check():
                    cancelled = True
                    terminate_process(proc)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    terminate_process(proc)
                    break
                time.sleep(0.5)
            try:
                return_code = proc.wait(timeout=5)
            except Exception:
                return_code = proc.poll()
    except FileNotFoundError as exc:
        log.append("error", {"reason": str(exc), "category": "binary_missing"})
        return {"status": "failed", "exit_code": None, "reason": str(exc), "category": "binary_missing", "runtime_status": status_payload}
    except Exception as exc:
        log.append("error", {"reason": str(exc), "category": "spawn_failed"})
        return {"status": "failed", "exit_code": None, "reason": str(exc), "category": "spawn_failed", "runtime_status": status_payload}

    stdout_text = redact(_read_tail(stdout_path, 16000))
    stderr_text = redact(_read_tail(stderr_path, 16000))
    cli_payload = _parse_json_object(stdout_text)
    cli_error = _cli_error_text(cli_payload)
    cli_output = _cli_output_text(cli_payload)
    cli_reported_failed = str(cli_payload.get("status") or "").strip().lower() in {"failed", "error"} if cli_payload else False
    workspace_after = read_workspace_status(cwd)
    changed_files = changed_status_paths(workspace_before, workspace_after)
    dirty_files = [item.get("path", "") for item in (workspace_after or []) if item.get("path")]
    artifact_candidates = [stdout_path, stderr_path]
    if job.output_file:
        artifact_candidates.append(Path(job.output_file))
    artifacts = [str(path) for path in artifact_candidates if path.exists()]
    output_text = (cli_error or cli_output or stdout_text or stderr_text).strip()[-16000:]
    if job.output_file:
        try:
            Path(job.output_file).write_text(output_text, encoding="utf-8")
        except Exception:
            pass

    if workspace_after is not None:
        log.append("workspace_after", {"dirty_count": len(workspace_after), "changed_files": changed_files[:80], "dirty_files": dirty_files[:120]})
    log.append("artifacts", {"artifacts": artifacts})

    if cancelled:
        status = "cancelled"
    elif timed_out:
        status = "failed"
    elif return_code == 0 and not cli_reported_failed:
        status = "completed"
    else:
        status = "failed"
    category = classify_result(status, return_code, stdout_text, stderr_text, timed_out)
    if status == "completed" and category != "ok":
        status = "failed"
    log.append("finished", {"status": status, "exit_code": return_code, "timed_out": timed_out, "cancelled": cancelled, "category": category})
    return {
        "status": status,
        "exit_code": return_code,
        "command": public_command,
        "commands_run": [command_text],
        "changed_files": changed_files,
        "dirty_files": dirty_files,
        "artifacts": artifacts,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "output": output_text,
        "response_preview": output_text[-2000:],
        "timed_out": timed_out,
        "cancelled": cancelled,
        "pid": pid,
        "category": category,
        "reason": _result_reason(category, cli_error, timed_out, cancelled),
        "runtime_status": status_payload,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _execute_direct_tool_loop(
    *,
    agent: str,
    job: JobRecord,
    log: EventLog,
    on_progress: Callable[[dict[str, Any]], None] | None,
    runtime_status: dict[str, Any],
) -> dict[str, Any] | None:
    calls = _infer_tool_calls_from_task(agent=agent, job=job)
    if not calls:
        return None

    approval = _job_approval(job)
    if approval != APPROVAL_PHRASE:
        log.append("tool_loop_blocked", {"reason": "missing_approval", "call_count": len(calls)})
        text = f"{agent} herkende {len(calls)} echte toolactie(s), maar de job mist de Akkoord-gate."
        _write_job_output(job, text)
        return {
            "status": "failed",
            "exit_code": 1,
            "reason": "Tool loop requires exact approval phrase: Akkoord.",
            "category": "approval_missing",
            "response_preview": text,
            "runtime_status": runtime_status,
            "tool_calls": _public_tool_calls(calls),
            "fake_success": False,
        }

    log.append("tool_loop_planned", {"agent": agent, "call_count": len(calls), "tools": [call["tool"] for call in calls]})
    if on_progress:
        on_progress({"response_preview": f"{agent} voert {len(calls)} echte toolactie(s) uit via de tool_bridge."})

    started = time.monotonic()
    results: list[dict[str, Any]] = []
    changed_files: list[str] = []
    commands_run: list[str] = []
    for call in calls:
        tool = str(call.get("tool") or "")
        args = dict(call.get("args") or {})
        args.setdefault("approval", approval)
        commands_run.append(f"tool_bridge:{tool}")
        log.append("tool_call", {"tool": tool, "args": _public_tool_args(args), "reason": call.get("reason", "")})
        try:
            from controller.tool_bridge import run_tool_bridge

            result = run_tool_bridge(tool, args)
        except Exception as exc:
            result = {"status": "error", "tool": tool, "reason": str(exc), "fake_success": False}
        result_status = str(result.get("status") or "unknown")
        log.append("tool_result", {"tool": tool, "status": result_status, "reason": _clip(redact(result.get("reason", "")), 800)})
        results.append({"tool": tool, "args": _public_tool_args(args), "result": _public_tool_result(result)})
        changed_files.extend(_changed_files_from_tool_result(tool, result))
        if on_progress:
            on_progress({"response_preview": _tool_loop_summary(agent, results)[-1800:]})

    failed = [
        item
        for item in results
        if str(((item.get("result") or {}).get("status") or "")).lower()
        in {"error", "failed", "blocked", "rejected", "approval_required", "disabled", "unavailable"}
    ]
    status = "failed" if failed else "completed"
    output = _tool_loop_summary(agent, results)
    _write_job_output(job, output)
    return {
        "status": status,
        "exit_code": 0 if status == "completed" else 1,
        "reason": "" if status == "completed" else f"{len(failed)} toolactie(s) faalden; zie job-events/result.json.",
        "category": "tool_loop" if status == "completed" else "tool_loop_error",
        "commands_run": commands_run,
        "changed_files": sorted(set(changed_files)),
        "dirty_files": [],
        "artifacts": [path for path in [job.output_file, job.result_file, job.events_file] if path],
        "output": output,
        "stdout": output,
        "stderr": "" if status == "completed" else "\n".join(str((item.get("result") or {}).get("reason") or "") for item in failed),
        "response_preview": output[-2000:],
        "tool_calls": _public_tool_calls(calls),
        "tool_results": results,
        "runtime_status": runtime_status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "fake_success": False,
    }


def _execute_cli_declared_tool_loop(
    *,
    agent: str,
    job: JobRecord,
    log: EventLog,
    on_progress: Callable[[dict[str, Any]], None] | None,
    cli_result: dict[str, Any],
    runtime_status: dict[str, Any],
) -> dict[str, Any]:
    text = f"{cli_result.get('stdout', '')}\n{cli_result.get('output', '')}"
    calls = _dedupe_tool_calls(_explicit_tool_calls_from_text(text))
    if not calls:
        return cli_result
    approval = _job_approval(job)
    if approval != APPROVAL_PHRASE:
        log.append("cli_tool_loop_blocked", {"reason": "missing_approval", "call_count": len(calls)})
        cli_result["category"] = "approval_missing"
        cli_result["reason"] = "CLI declared tool calls, but job metadata is missing Akkoord approval."
        cli_result["tool_calls"] = _public_tool_calls(calls)
        cli_result["status"] = "failed"
        cli_result["exit_code"] = 1
        return cli_result

    log.append("cli_tool_loop_planned", {"agent": agent, "call_count": len(calls), "tools": [call["tool"] for call in calls]})
    results: list[dict[str, Any]] = []
    changed_files = list(cli_result.get("changed_files") or [])
    for call in calls:
        tool = str(call.get("tool") or "")
        args = dict(call.get("args") or {})
        args.setdefault("approval", approval)
        log.append("cli_tool_call", {"tool": tool, "args": _public_tool_args(args)})
        try:
            from controller.tool_bridge import run_tool_bridge

            result = run_tool_bridge(tool, args)
        except Exception as exc:
            result = {"status": "error", "tool": tool, "reason": str(exc), "fake_success": False}
        log.append("cli_tool_result", {"tool": tool, "status": result.get("status"), "reason": _clip(redact(result.get("reason", "")), 800)})
        results.append({"tool": tool, "args": _public_tool_args(args), "result": _public_tool_result(result)})
        changed_files.extend(_changed_files_from_tool_result(tool, result))
        if on_progress:
            on_progress({"response_preview": _tool_loop_summary(agent, results)[-1800:]})

    failed = [
        item
        for item in results
        if str(((item.get("result") or {}).get("status") or "")).lower()
        in {"error", "failed", "blocked", "rejected", "approval_required", "disabled", "unavailable"}
    ]
    summary = _tool_loop_summary(agent, results)
    combined_output = f"{str(cli_result.get('output') or '').strip()}\n\n{summary}".strip() + "\n"
    _write_job_output(job, combined_output)
    cli_result["tool_calls"] = _public_tool_calls(calls)
    cli_result["tool_results"] = results
    cli_result["changed_files"] = sorted(set(changed_files))
    cli_result["runtime_status"] = runtime_status
    cli_result["output"] = combined_output
    cli_result["stdout"] = f"{str(cli_result.get('stdout') or '').strip()}\n\n{summary}".strip()
    cli_result["response_preview"] = combined_output[-2000:]
    if failed:
        cli_result["status"] = "failed"
        cli_result["exit_code"] = 1
        cli_result["category"] = "cli_tool_loop_error"
        cli_result["reason"] = f"{len(failed)} declared tool call(s) failed."
    elif cli_result.get("status") == "failed":
        cli_result["status"] = "completed"
        cli_result["exit_code"] = 0
        cli_result["category"] = "cli_tool_loop_recovered"
        cli_result["reason"] = "Declared Ouroboros tool calls executed successfully."
    return cli_result


def _infer_tool_calls_from_task(*, agent: str, job: JobRecord) -> list[dict[str, Any]]:
    task = str(job.task or "")
    lowered = task.casefold()
    calls: list[dict[str, Any]] = []

    if _looks_like_browser_open_request(lowered):
        url = _extract_first_url(task)
        if url:
            calls.append(
                {
                    "tool": "browser_open_url",
                    "args": {"url": url},
                    "reason": "De opdracht vraagt om een zichtbare browser-tab/navigatie.",
                }
            )

    if _looks_like_gmail_request(lowered):
        calls.extend(_gmail_tool_calls(task, lowered))

    file_calls = _file_tool_calls(agent=agent, job=job, task=task, lowered=lowered)
    calls.extend(file_calls)

    calls.extend(_explicit_tool_calls_from_text(task))
    return _dedupe_tool_calls(calls)


def _looks_like_browser_open_request(lowered: str) -> bool:
    return any(word in lowered for word in ("browser", "tab", "open url", "open een", "navigeer", "navigate", "ga naar", "open ")) and bool(URLISH_RE.search(lowered))


def _looks_like_gmail_request(lowered: str) -> bool:
    return "gmail" in lowered or re.search(r"\bmail(?:box|s|berichten| inbox)?\b", lowered) is not None


def _gmail_tool_calls(task: str, lowered: str) -> list[dict[str, Any]]:
    query = _extract_gmail_query(task) or "in:inbox newer_than:30d"
    max_results = _extract_int_near(task, ("max", "limit", "aantal"), default=5 if any(word in lowered for word in ("organiseer", "organize", "sort", "sorteer")) else 10)
    label = _extract_label_name(task) or "Ouroboros/Organized"
    destructive = any(word in lowered for word in ("archive", "archiveer", "move", "verplaats"))
    labeling = destructive or any(word in lowered for word in ("label", "map", "folder", "organiseer", "organize", "sort", "sorteer"))
    mark_read = any(phrase in lowered for phrase in ("mark read", "markeer gelezen", "als gelezen"))

    if labeling:
        action = "move" if any(word in lowered for word in ("move", "verplaats")) else ("archive" if any(word in lowered for word in ("archive", "archiveer")) and not label else "label")
        args: dict[str, Any] = {
            "action": action,
            "query": query,
            "max_results": max_results,
            "mark_read": mark_read,
        }
        if label and action != "archive":
            args["label"] = label
        if destructive:
            args["archive"] = True
        return [{"tool": "gmail_manage", "args": args, "reason": "De opdracht vraagt om Gmail te sorteren/labelen/verplaatsen/archiveren."}]

    return [{"tool": "gmail_search", "args": {"query": query, "max_results": max_results}, "reason": "De opdracht vraagt om Gmail te lezen/zoeken."}]


def _file_tool_calls(*, agent: str, job: JobRecord, task: str, lowered: str) -> list[dict[str, Any]]:
    if not any(word in lowered for word in ("file", "bestand", "save", "sla op", "schrijf", "write", "create")):
        return []
    if "gmail" in lowered and not any(word in lowered for word in ("local", "disk", "drive", "bestand", "file")):
        return []

    path = _extract_file_path(task)
    explicit_file_action = bool(
        path
        or _extract_file_content(task)
        or "google drive" in lowered
        or re.search(r"(?i)\b(?:write|create|save|maak|schrijf|sla)\s+(?:een\s+|a\s+)?(?:file|bestand)\b", task)
    )
    if not explicit_file_action:
        return []

    content = _extract_file_content(task) or f"Created by {agent} for Ouroboros job {job.job_id}.\n\nTask:\n{task.strip()}\n"
    drive_requested = "google drive" in lowered or re.search(r"\bdrive\b", lowered) is not None
    calls: list[dict[str, Any]] = []

    if path or not drive_requested:
        target_path = path or f"out/agent_runtime/{agent}_{job.job_id[-8:]}_output.txt"
        calls.append(
            {
                "tool": "write_file",
                "args": {"path": target_path, "content": content},
                "reason": "De opdracht vraagt om een bestand lokaal te maken/schrijven.",
            }
        )
        if drive_requested:
            calls.append(
                {
                    "tool": "drive_upload_file",
                    "args": {"path": target_path},
                    "reason": "De opdracht vraagt om het bestand ook naar Google Drive te bewaren.",
                }
            )
    elif drive_requested:
        calls.append(
            {
                "tool": "drive_upload_text",
                "args": {"name": f"{agent}-{job.job_id[-8:]}-output.txt", "content": content},
                "reason": "De opdracht vraagt om tekst als Google Drive-bestand te bewaren.",
            }
        )
    return calls


def _extract_first_url(text: str) -> str:
    candidates = [match.group(0).strip(".,;:)]}\"'") for match in URLISH_RE.finditer(text)]
    for candidate in candidates:
        if not candidate or candidate.lower().endswith((".md", ".py", ".json")):
            continue
        if not re.match(r"(?i)^https?://", candidate):
            candidate = "https://" + candidate.lstrip("/")
        parsed = urllib.parse.urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return urllib.parse.urlunparse(parsed)
    return ""


def _extract_gmail_query(text: str) -> str:
    patterns = (
        r"(?i)\b(?:gmail\s+)?(?:query|q|zoekterm|search)\s*[:=]\s*([^\n;]+)",
        r"(?i)\b(?:zoek|search)\s+(?:gmail|mail)\s+(?:naar|for)\s+([^\n;]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_gmail_query(match.group(1))
    gmail_tokens = re.findall(r"\b(?:from|to|subject|label|in|category|newer_than|older_than):[^\s;]+", text, flags=re.IGNORECASE)
    if gmail_tokens:
        return " ".join(gmail_tokens)
    return ""


def _clean_gmail_query(value: str) -> str:
    text = str(value or "").strip().strip("\"'")
    text = re.split(r"(?i)\s+\b(?:label|archive|archiveer|move|verplaats|naar map|to folder|max|limit)\b", text, maxsplit=1)[0]
    return text.strip().strip("\"'")[:512]


def _extract_label_name(text: str) -> str:
    patterns = (
        r"(?i)\b(?:label|map|folder)\s*(?:as|als|naar|to|:)?\s*['\"]([^'\"]+)['\"]",
        r"(?i)\b(?:label|map|folder)\s*(?:as|als|naar|to|:)\s*([A-Za-z0-9 _./-]{2,80})",
        r"(?i)\b(?:organiseer|organize|sort|sorteer).{0,40}\b(?:als|as|naar|to)\s*['\"]([^'\"]+)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            label = str(match.group(1) or "").strip().strip("/").rstrip(".,;")
            if label:
                return label[:225]
    return ""


def _extract_int_near(text: str, names: tuple[str, ...], *, default: int) -> int:
    for name in names:
        match = re.search(rf"(?i)\b{name}\s*[:=]?\s*(\d{{1,2}})\b", text)
        if match:
            try:
                return max(1, min(int(match.group(1)), 50))
            except ValueError:
                pass
    return max(1, min(int(default), 50))


def _extract_file_path(text: str) -> str:
    quoted = re.search(r"['\"]([^'\"]+\.(?:txt|md|json|csv|html|py|log))['\"]", text, flags=re.IGNORECASE)
    if quoted:
        return quoted.group(1).strip()
    matches = [match.group(0).strip(".,;:)]}\"'") for match in FILE_PATH_RE.finditer(text)]
    for match in matches:
        if match and not match.startswith(("http://", "https://")):
            return match
    return ""


def _extract_file_content(text: str) -> str:
    patterns = (
        r"(?is)\b(?:content|inhoud)\s*[:=]\s*(.+)$",
        r"(?is)\b(?:with content|met inhoud)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return str(match.group(1) or "").strip().strip("\"'")
    return ""


def _explicit_tool_calls_from_text(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for line in str(text or "").splitlines():
        if "OUROBOROS_TOOL_CALL" not in line:
            continue
        _, _, raw = line.partition("OUROBOROS_TOOL_CALL")
        raw = raw.strip().lstrip(":").strip()
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("tool"):
            calls.append({"tool": str(payload.get("tool")), "args": dict(payload.get("args") or {}), "reason": "Expliciete OUROBOROS_TOOL_CALL uit agentoutput."})
    return calls


def _dedupe_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for call in calls:
        tool = str(call.get("tool") or "")
        args = dict(call.get("args") or {})
        key = json.dumps({"tool": tool, "args": args}, sort_keys=True, ensure_ascii=False)
        if not tool or key in seen:
            continue
        seen.add(key)
        out.append({"tool": tool, "args": args, "reason": str(call.get("reason") or "")})
    return out


def _job_approval(job: JobRecord) -> str:
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    approval = str(metadata.get("approval") or "").strip()
    if approval == APPROVAL_PHRASE or str(metadata.get("approval_status") or "").strip() == "approved":
        return APPROVAL_PHRASE
    return approval


def _public_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"tool": str(call.get("tool") or ""), "args": _public_tool_args(dict(call.get("args") or {})), "reason": _clip(redact(call.get("reason", "")), 500)} for call in calls]


def _public_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key, value in args.items():
        if str(key).lower() in {"approval"}:
            public[key] = "[APPROVED]" if str(value).strip() == APPROVAL_PHRASE else "[MISSING]"
        elif any(marker in str(key).lower() for marker in ("token", "secret", "password", "key")):
            public[key] = "[REDACTED]"
        elif isinstance(value, str):
            public[key] = _clip(redact(value), 1200)
        else:
            public[key] = value
    return public


def _public_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        decoded = json.loads(redact(encoded))
        return decoded if isinstance(decoded, dict) else {"value": decoded}
    except Exception:
        return {"status": str(result.get("status") or "unknown"), "reason": _clip(redact(result.get("reason", "")), 1000)}


def _changed_files_from_tool_result(tool: str, result: dict[str, Any]) -> list[str]:
    if tool != "write_file":
        return []
    raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    path = str((nested or raw.get("result") or {}).get("path") or "")
    return [path] if path else []


def _tool_loop_summary(agent: str, results: list[dict[str, Any]]) -> str:
    lines = [f"{agent} real-tool loop:"]
    for index, item in enumerate(results, start=1):
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        tool = item.get("tool")
        status = result.get("status")
        line = f"{index}. {tool}: {status}"
        reason = str(result.get("reason") or "").strip()
        if reason:
            line += f" - {_clip(reason, 260)}"
        lines.append(line)
        for key in ("url", "path", "operation", "modified_count", "count"):
            value = result.get(key)
            if value not in (None, "", []):
                lines.append(f"   {key}: {_clip(value, 500)}")
        if isinstance(result.get("result"), dict):
            nested = result["result"]
            for key in ("path", "bytes_written", "modified_count", "count"):
                value = nested.get(key)
                if value not in (None, "", []):
                    lines.append(f"   {key}: {_clip(value, 500)}")
    return "\n".join(lines).strip() + "\n"


def _write_job_output(job: JobRecord, text: str) -> None:
    if not job.output_file:
        return
    try:
        Path(job.output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(job.output_file).write_text(str(text or ""), encoding="utf-8")
    except Exception:
        pass


def read_workspace_status(cwd: str) -> list[dict[str, str]] | None:
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
    out: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or "modified"
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            out.append({"status": redact(status)[:20], "path": redact(path)[:500]})
    return out


def changed_status_paths(before: list[dict[str, str]] | None, after: list[dict[str, str]] | None) -> list[str]:
    if after is None:
        return []
    before_keys = {f"{item.get('status', '')}\0{item.get('path', '')}" for item in (before or [])}
    changed: list[str] = []
    seen: set[str] = set()
    for item in after:
        key = f"{item.get('status', '')}\0{item.get('path', '')}"
        path = str(item.get("path") or "")
        if not path or key in before_keys or path in seen:
            continue
        seen.add(path)
        changed.append(path)
    return changed[:200]


def terminate_process(proc: Any) -> None:
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


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw.startswith("{"):
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _cli_error_text(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    error = str(payload.get("error") or payload.get("message") or "").strip()
    if error:
        return error
    status = str(payload.get("status") or "").strip().lower()
    output = str(payload.get("output") or "").strip()
    if status in {"failed", "error"} and output:
        return output
    return ""


def _cli_output_text(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    output = payload.get("output")
    if isinstance(output, str):
        return output.strip()
    if output is not None:
        try:
            return json.dumps(output, ensure_ascii=False)
        except Exception:
            return str(output).strip()
    return ""


def _result_reason(category: str, cli_error: str, timed_out: bool, cancelled: bool) -> str:
    if cancelled:
        return "Job was cancelled."
    if timed_out:
        return "Job timed out."
    if category == "auth_missing":
        return cli_error or "Agent CLI authentication is missing."
    if category in {"binary_missing", "spawn_failed", "exec_error"}:
        return cli_error
    return ""


def classify_result(status: str, exit_code: int | None, stdout: str, stderr: str, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    blob = f"{stdout}\n{stderr}".lower()
    auth_markers = (
        "api key not found",
        "api key missing",
        "missing api key",
        "no api key",
        "invalid api key",
        "failed to send message",
        "auth set",
        "not authenticated",
        "authentication failed",
        "unauthorized",
    )
    if any(marker in blob for marker in auth_markers):
        return "auth_missing"
    if status == "completed":
        return "ok"
    if "command not found" in blob or "no such file" in blob:
        return "binary_missing"
    if exit_code is None:
        return "spawn_failed"
    return "exec_error"


def _probe_launcher(
    launcher: dict[str, Any] | None,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    if launcher is None:
        return {"status": "missing", "exit_code": None, "stdout": "", "stderr": "no launcher", "duration_ms": 0}
    command = [*launcher["command"], *args]
    probe = run_probe(command, cwd=cwd if cwd.exists() else None, env={**env, **launcher.get("env", {})}, timeout_seconds=timeout_seconds)
    return probe.to_dict()


def _bridge_get(path: str, *, timeout: float = 5.0) -> dict[str, Any]:
    base_url = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
    if not base_url or not token_path:
        return {}
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    request = urllib.request.Request(
        f"{base_url}{path}",
        method="GET",
        headers={"X-Ouroboros-Bridge-Token": token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_probe_output(command: list[str], *, env: dict[str, str]) -> str:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=3, env=env, check=False)
    except Exception:
        return ""
    return (proc.stdout or proc.stderr or "").strip()


def _node_major(node: str, *, env: dict[str, str]) -> int:
    return _parse_node_major(_run_probe_output([node, "--version"], env=env))


def _parse_node_major(version: str) -> int:
    match = re.search(r"v?(\d+)", str(version or ""))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _job_prompt(job: JobRecord) -> str:
    prompt = _metadata_value(job, "prompt")
    return prompt or job.task


def _job_prompt_with_tool_protocol(agent: str, job: JobRecord) -> str:
    base = _job_prompt(job)
    return (
        f"{base}\n\n"
        "Ouroboros real-tool protocol:\n"
        "- Als je echte side-effects nodig hebt, geef per regel exact dit formaat terug:\n"
        "  OUROBOROS_TOOL_CALL {\"tool\":\"browser_open_url\",\"args\":{\"url\":\"https://www.ns.nl/\"}}\n"
        "  OUROBOROS_TOOL_CALL {\"tool\":\"gmail_manage\",\"args\":{\"query\":\"in:inbox newer_than:30d\",\"label\":\"Ouroboros/Organized\",\"max_results\":5}}\n"
        "  OUROBOROS_TOOL_CALL {\"tool\":\"write_file\",\"args\":{\"path\":\"out/agent_runtime/note.txt\",\"content\":\"tekst\"}}\n"
        "- Beschikbare tools: browser_open_url, gmail_search, gmail_manage, write_file, drive_upload_file, drive_upload_text.\n"
        "- De host runtime voegt Akkoord alleen toe als de slash/API gate al goedgekeurd is.\n"
        f"- Agent label: {agent}.\n"
    )


def _metadata_value(job: JobRecord, key: str) -> str:
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    value = metadata.get(key)
    return str(value).strip() if value is not None else ""


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_HOST_WORKSPACE") or os.getenv("WINTRIP_PROJECT_ROOT") or os.getenv("WINTRIP_WORKSPACE")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path.resolve()
    fallback = Path("/home/pwintri2/WintripAI")
    return fallback.resolve() if fallback.exists() else Path.cwd().resolve()


def _read_tail(path: Path, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except Exception:
        return ""


def redact(text: Any) -> str:
    redacted = str(text or "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _clip(value: Any, limit: int = 4000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"
