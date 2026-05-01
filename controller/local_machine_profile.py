"""Read-only local machine profiler for Ouroboros training memory."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"


def local_machine_profile_path() -> Path:
    return (workspace_root() / ".secrets" / "local_machine_profile.json").resolve()


def get_local_machine_status() -> dict[str, Any]:
    snapshot = load_latest_machine_snapshot()
    return {
        "status": "profiled" if snapshot.get("status") == "success" else "ready",
        "profile_path": str(local_machine_profile_path()),
        "last_snapshot_at": snapshot.get("captured_at"),
        "has_snapshot": snapshot.get("status") == "success",
        "environment": snapshot.get("environment", _environment_scope()),
        "os": snapshot.get("os", {}),
        "hardware": snapshot.get("hardware", {}),
        "toolchains": snapshot.get("toolchains", {}),
        "docker": snapshot.get("docker", {}),
        "ollama": snapshot.get("ollama", {}),
        "fake_success": False,
    }


def snapshot_local_machine(approval: str = "") -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}

    started = time.time()
    snapshot = {
        "status": "success",
        "captured_at": datetime.utcnow().isoformat(),
        "workspace": str(workspace_root()),
        "environment": _environment_scope(),
        "os": _os_info(),
        "hardware": _hardware_info(),
        "toolchains": _toolchain_info(),
        "docker": _docker_info(),
        "ollama": _ollama_info(),
        "ports": _ports_info(),
        "duration_seconds": 0.0,
        "fake_success": False,
    }
    snapshot["duration_seconds"] = round(time.time() - started, 3)
    _save_snapshot(snapshot)
    return snapshot


def load_latest_machine_snapshot() -> dict[str, Any]:
    path = local_machine_profile_path()
    if not path.exists():
        return {"status": "missing", "fake_success": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"status": "error", "reason": "Snapshot is not a JSON object.", "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": f"Cannot read local machine snapshot: {exc}", "fake_success": False}


def _os_info() -> dict[str, Any]:
    os_release = {}
    path = Path("/etc/os-release")
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_release[key] = value.strip().strip('"')
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "uname": _run(["uname", "-a"]),
        "os_release": os_release,
    }


def _environment_scope() -> dict[str, Any]:
    in_container = Path("/.dockerenv").exists()
    return {
        "scope": "docker_container" if in_container else "host",
        "note": (
            "Snapshot describes the Docker runtime. Mount host probes or run the backend on the host for full Pop!_OS software inventory."
            if in_container
            else "Snapshot describes the host runtime."
        ),
    }


def _hardware_info() -> dict[str, Any]:
    meminfo = _read_key_value_file(Path("/proc/meminfo"))
    cpuinfo = Path("/proc/cpuinfo")
    cpu_model = ""
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if "model name" in line and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    return {
        "cpu_count": os.cpu_count(),
        "cpu_model": cpu_model,
        "mem_total": meminfo.get("MemTotal", ""),
        "disk_root": _run(["df", "-h", "/"]),
        "disk_workspace": _run(["df", "-h", str(workspace_root())]),
        "lscpu": _run_if_available("lscpu", ["lscpu"]),
        "lspci_gpu": _run_if_available("lspci", ["lspci"]),
        "nvidia_smi": _run_if_available("nvidia-smi", ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]),
    }


def _toolchain_info() -> dict[str, Any]:
    commands = {
        "python3": ["python3", "--version"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "git": ["git", "--version"],
        "gcc": ["gcc", "--version"],
        "g++": ["g++", "--version"],
        "cmake": ["cmake", "--version"],
        "rustc": ["rustc", "--version"],
        "cargo": ["cargo", "--version"],
    }
    return {name: _run_if_available(name, command) for name, command in commands.items()}


def _docker_info() -> dict[str, Any]:
    return {
        "available": shutil.which("docker") is not None,
        "version": _run_if_available("docker", ["docker", "--version"]),
        "containers": _run_if_available("docker", ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"]),
        "images": _run_if_available("docker", ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}"]),
    }


def _ollama_info() -> dict[str, Any]:
    try:
        from controller.ollama_client import OllamaClient

        client = OllamaClient()
        models = client.list_models()
        return {"available": bool(models), "base_url": client.base_url, "models": models[:50]}
    except Exception as exc:
        return {"available": False, "reason": str(exc), "models": []}


def _ports_info() -> dict[str, Any]:
    ss = _run_if_available("ss", ["ss", "-tulpen"])
    if ss.get("status") == "missing":
        ss = _run_if_available("netstat", ["netstat", "-tulpen"])
    return {"listeners": ss}


def _run_if_available(binary: str, command: list[str]) -> dict[str, Any]:
    if shutil.which(binary) is None:
        return {"status": "missing", "command": command, "stdout": "", "stderr": ""}
    return _run(command)


def _run(command: list[str], timeout: int = 5) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "command": command,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        return {"status": "error", "command": command, "exit_code": None, "stdout": "", "stderr": str(exc)}


def _read_key_value_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _save_snapshot(snapshot: dict[str, Any]) -> None:
    path = local_machine_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
