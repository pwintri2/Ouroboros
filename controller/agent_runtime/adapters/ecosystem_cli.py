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
import urllib.request
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord
from controller.status_contracts import run_probe


DEFAULT_DEEPSEEK_ROOT = "/home/pwintri2/deepseek"
DEFAULT_ATLAS_ROOT = "/home/pwintri2/atlas"

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)


def deepseek_root() -> Path:
    return Path(os.getenv("WINTRIP_DEEPSEEK_PATH") or DEFAULT_DEEPSEEK_ROOT).expanduser().resolve()


def atlas_root() -> Path:
    return Path(os.getenv("WINTRIP_ATLAS_PATH") or DEFAULT_ATLAS_ROOT).expanduser().resolve()


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
            (base / "npm" / "deepseek-tui" / "bin" / "deepseek-tui.js", "npm TUI wrapper", "script"),
            (base / "npm" / "deepseek-tui" / "bin" / "deepseek.js", "npm wrapper", "script"),
            (base / "npm" / "deepseek-tui" / "bin" / "downloads" / "deepseek-tui", "downloaded TUI binary", "binary"),
            (base / "crates" / "tui" / "Cargo.toml", "tui cargo crate", "manifest"),
            (base / "docs" / "SUBAGENTS.md", "sub-agent role docs", "doc"),
            (base / "docs" / "TOOL_SURFACE.md", "tool surface docs", "doc"),
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
    prompt = _job_prompt(job)
    command = [
        *launcher["command"],
        "--workspace",
        job.workspace_root or str(_workspace_root()),
        "exec",
        "--auto",
        "--json",
        prompt,
    ]
    return _run_cli_job(
        agent="deepseek",
        job=job,
        log=log,
        on_progress=on_progress,
        command=command,
        cwd=job.workspace_root or str(_workspace_root()),
        env={**env, **launcher.get("env", {})},
        status_payload=status,
    )


def run_atlas_job(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    root = atlas_root()
    env = runtime_env()
    status = atlas_status(prefer_bridge=False)
    log.append("atlas_status", status)
    launcher = resolve_atlas_launcher(root=root, env=env)
    if launcher is None:
        return {
            "status": "failed",
            "exit_code": None,
            "reason": status.get("reason") or "Atlas CLI is not launchable.",
            "category": "binary_missing",
            "runtime_status": status,
        }
    prompt = _job_prompt(job)
    command = [*launcher["command"], "ask"]
    model = _metadata_value(job, "model")
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return _run_cli_job(
        agent="atlas",
        job=job,
        log=log,
        on_progress=on_progress,
        command=command,
        cwd=job.workspace_root or str(_workspace_root()),
        env={**env, **launcher.get("env", {})},
        status_payload=status,
    )


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
    return env


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
    workspace_after = read_workspace_status(cwd)
    changed_files = changed_status_paths(workspace_before, workspace_after)
    dirty_files = [item.get("path", "") for item in (workspace_after or []) if item.get("path")]
    artifact_candidates = [stdout_path, stderr_path]
    if job.output_file:
        artifact_candidates.append(Path(job.output_file))
    artifacts = [str(path) for path in artifact_candidates if path.exists()]
    output_text = (stdout_text or stderr_text).strip()[-16000:]
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
    elif return_code == 0:
        status = "completed"
    else:
        status = "failed"
    category = classify_result(status, return_code, stdout_text, stderr_text, timed_out)
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
        "runtime_status": status_payload,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


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


def classify_result(status: str, exit_code: int | None, stdout: str, stderr: str, timed_out: bool) -> str:
    if status == "completed":
        return "ok"
    if timed_out:
        return "timeout"
    blob = f"{stdout}\n{stderr}".lower()
    if "api key" in blob or "auth" in blob or "login" in blob or "unauthorized" in blob:
        return "auth_missing"
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
