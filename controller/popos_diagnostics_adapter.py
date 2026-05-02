"""Approval-gated Pop!_OS and Linux diagnostics adapter.

Purpose:
    Collect structured, read-only diagnostics for a Pop!_OS/Linux laptop and
    map the result into Ouroboros 11D ecosystem signals.
Inputs:
    An exact Akkoord approval phrase and an optional list of diagnostic command
    keys. Commands are fixed argument arrays; no shell strings are accepted.
Outputs:
    JSON diagnostics, command availability, redacted command output, a current
    thermal/power recommendation and a persisted artifact under artifacts/.
Safety notes:
    Commands are read-only, bounded by timeout and output limits, and common
    credential patterns are redacted. Commands that need root are attempted
    without sudo and may honestly report permission errors.
Akkoord requirements:
    run_popos_diagnostics() requires approval == "Akkoord".

Why this change:
    The deep ecosystem buildplan starts with Pop!_OS mastery. Ouroboros needs a
    safe host/container diagnostic surface before it can reason about thermal,
    power, memory, storage and driver health.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, clamp01, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"


@dataclass(frozen=True)
class DiagnosticCommand:
    key: str
    binary: str
    args: tuple[str, ...]
    timeout: int = 8
    output_limit: int = 16000
    description: str = ""


COMMAND_SPECS: dict[str, DiagnosticCommand] = {
    "inxi_full": DiagnosticCommand("inxi_full", "inxi", ("inxi", "-Fxxxz"), 10, 24000, "Full inxi hardware/software report."),
    "journal_errors": DiagnosticCommand(
        "journal_errors",
        "journalctl",
        ("journalctl", "-b", "-p", "err", "--no-pager", "-n", "200"),
        8,
        24000,
        "Current boot error journal.",
    ),
    "lshw_short": DiagnosticCommand("lshw_short", "lshw", ("lshw", "-short"), 10, 24000, "Hardware inventory."),
    "dmidecode_system": DiagnosticCommand("dmidecode_system", "dmidecode", ("dmidecode", "-t", "system"), 8, 12000, "DMI vendor/product data."),
    "tlp_stat": DiagnosticCommand("tlp_stat", "tlp-stat", ("tlp-stat", "-s"), 8, 12000, "TLP status."),
    "powertop": DiagnosticCommand("powertop", "powertop", ("powertop", "--time=1", "--html=/dev/stdout"), 12, 20000, "PowerTOP one-second report."),
    "nvidia_smi": DiagnosticCommand("nvidia_smi", "nvidia-smi", ("nvidia-smi",), 8, 20000, "NVIDIA GPU/driver state."),
    "lsblk": DiagnosticCommand("lsblk", "lsblk", ("lsblk", "-J", "-o", "NAME,TYPE,SIZE,FSTYPE,LABEL,MOUNTPOINTS"), 6, 16000, "Block device overview."),
    "df": DiagnosticCommand("df", "df", ("df", "-h"), 6, 12000, "Filesystem usage."),
    "uptime": DiagnosticCommand("uptime", "uptime", ("uptime",), 4, 4000, "Load average and uptime."),
    "free": DiagnosticCommand("free", "free", ("free", "-b"), 4, 4000, "Memory usage in bytes."),
    "powerprofilesctl": DiagnosticCommand("powerprofilesctl", "powerprofilesctl", ("powerprofilesctl", "get"), 4, 4000, "Active power profile."),
}

DEFAULT_COMMAND_KEYS: tuple[str, ...] = (
    "uptime",
    "free",
    "df",
    "lsblk",
    "journal_errors",
    "nvidia_smi",
    "powerprofilesctl",
    "inxi_full",
    "lshw_short",
    "dmidecode_system",
    "tlp_stat",
    "powertop",
)


def popos_diagnostics_state_path() -> Path:
    return (workspace_root() / ".secrets" / "popos_diagnostics.json").resolve()


def popos_diagnostics_output_dir() -> Path:
    return (workspace_root() / "artifacts" / "popos_diagnostics_output").resolve()


def get_popos_diagnostics_status() -> dict[str, Any]:
    """Return adapter readiness and the latest saved diagnostic summary."""
    latest = _load_latest()
    availability = {
        key: {
            "binary": spec.binary,
            "available": shutil.which(spec.binary) is not None,
            "description": spec.description,
        }
        for key, spec in COMMAND_SPECS.items()
    }
    return {
        "status": "ready",
        "adapter": "popos_diagnostics",
        "approval_required": True,
        "command_count": len(COMMAND_SPECS),
        "available_count": sum(1 for item in availability.values() if item["available"]),
        "commands": availability,
        "latest_summary": latest.get("summary", {}),
        "last_run_at": latest.get("captured_at"),
        "state_path": str(popos_diagnostics_state_path()),
        "output_dir": str(popos_diagnostics_output_dir()),
        "fake_success": False,
    }


def run_popos_diagnostics(approval: str = "", command_keys: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Run fixed read-only diagnostics after explicit Akkoord."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}

    started = time.time()
    selected = _normalize_command_keys(command_keys)
    results: dict[str, Any] = {}
    for key in selected:
        results[key] = _run_command(COMMAND_SPECS[key])

    system_context = _system_context()
    augmentation = _augment_11d(results=results, system_context=system_context)
    recommendation = current_thermal_recommendation(augmentation)
    summary = {
        "environment_scope": system_context["environment_scope"],
        "os_name": system_context["os_release"].get("PRETTY_NAME") or platform.platform(),
        "thermal_state": recommendation["thermal_state"],
        "recommended_power_profile": recommendation["recommended_power_profile"],
        "memory_pressure": augmentation["signals"]["memory_pressure"],
        "storage_pressure": augmentation["signals"]["storage_pressure"],
        "kernel_error_pressure": augmentation["signals"]["safety_risk"],
        "driver_or_api_health": augmentation["signals"]["driver_or_api_health"],
    }
    payload = {
        "status": "success",
        "adapter": "popos_diagnostics",
        "captured_at": datetime.utcnow().isoformat(),
        "duration_seconds": round(time.time() - started, 3),
        "workspace": str(workspace_root()),
        "system": system_context,
        "commands": results,
        "summary": summary,
        "recommendation": recommendation,
        "augmentation": augmentation,
        "record": build_11d_record(
            source="popos_diagnostics_adapter",
            record_type="os_diagnostics",
            title="Pop!_OS/Linux diagnostic snapshot",
            summary=json.dumps(summary, sort_keys=True),
            signals=augmentation["signals"],
            metadata={"selected_commands": selected, "environment_scope": system_context["environment_scope"]},
        ),
        "fake_success": False,
    }
    target = _write_artifact(payload)
    payload["artifact_path"] = str(target)
    _save_latest(payload)
    return payload


def current_thermal_recommendation(augmentation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize thermal/power state from the latest augmentation."""
    augmentation = augmentation or (_load_latest().get("augmentation") or {})
    signals = augmentation.get("signals") or {}
    thermal = clamp01(signals.get("thermal_load", 0.0))
    memory = clamp01(signals.get("memory_pressure", 0.0))
    storage = clamp01(signals.get("storage_pressure", 0.0))
    safety = clamp01(signals.get("safety_risk", 0.0))
    pressure = max(thermal, memory, storage, safety)
    if pressure >= 0.75:
        thermal_state = "hot_or_constrained"
        profile = "power-saver"
        next_step = "Reduce workload, inspect journal errors, and prefer power-saver until pressure drops."
    elif pressure >= 0.45:
        thermal_state = "warm_or_busy"
        profile = "balanced"
        next_step = "Keep balanced profile and inspect the highest-pressure subsystem."
    else:
        thermal_state = "cool_or_nominal"
        profile = "balanced"
        next_step = "System looks nominal from available read-only signals."
    return {
        "thermal_state": thermal_state,
        "recommended_power_profile": profile,
        "pressure_score": round(pressure, 6),
        "next_step": next_step,
        "fake_success": False,
    }


def _normalize_command_keys(command_keys: list[str] | tuple[str, ...] | None) -> list[str]:
    keys = list(command_keys or DEFAULT_COMMAND_KEYS)
    normalized: list[str] = []
    for key in keys:
        if key not in COMMAND_SPECS:
            continue
        if key not in normalized:
            normalized.append(key)
    return normalized or list(DEFAULT_COMMAND_KEYS)


def _run_command(spec: DiagnosticCommand) -> dict[str, Any]:
    if shutil.which(spec.binary) is None:
        return {
            "status": "missing",
            "binary": spec.binary,
            "command": list(spec.args),
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "description": spec.description,
        }
    try:
        proc = subprocess.run(
            list(spec.args),
            text=True,
            capture_output=True,
            timeout=max(1, min(spec.timeout, 30)),
        )
        stdout = redact_sensitive_text(proc.stdout or "", max_chars=spec.output_limit)
        stderr = redact_sensitive_text(proc.stderr or "", max_chars=min(spec.output_limit, 8000))
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "binary": spec.binary,
            "command": list(spec.args),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "description": spec.description,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "binary": spec.binary,
            "command": list(spec.args),
            "stdout": redact_sensitive_text(exc.stdout or "", max_chars=spec.output_limit) if isinstance(exc.stdout, str) else "",
            "stderr": redact_sensitive_text(exc.stderr or "", max_chars=8000) if isinstance(exc.stderr, str) else "",
            "exit_code": None,
            "description": spec.description,
        }
    except Exception as exc:
        return {
            "status": "error",
            "binary": spec.binary,
            "command": list(spec.args),
            "stdout": "",
            "stderr": redact_sensitive_text(str(exc)),
            "exit_code": None,
            "description": spec.description,
        }


def _system_context() -> dict[str, Any]:
    os_release = _read_os_release()
    return {
        "platform": platform.platform(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "os_release": os_release,
        "is_popos": (os_release.get("ID") == "pop") or ("pop!_os" in (os_release.get("NAME", "").lower())),
        "environment_scope": "docker_container" if Path("/.dockerenv").exists() else "host",
        "desktop": {
            "xdg_current_desktop": os.getenv("XDG_CURRENT_DESKTOP", ""),
            "desktop_session": os.getenv("DESKTOP_SESSION", ""),
            "cosmic_hint": _cosmic_hint(),
        },
        "system76": _system76_hint(),
        "recovery_partition": _recovery_partition_hint(),
    }


def _augment_11d(results: dict[str, Any], system_context: dict[str, Any]) -> dict[str, Any]:
    memory_pressure = _memory_pressure(results.get("free") or {})
    storage_pressure = _storage_pressure()
    journal_text = "\n".join(
        str((results.get("journal_errors") or {}).get(name) or "") for name in ("stdout", "stderr")
    )
    error_lines = [line for line in journal_text.splitlines() if line.strip()]
    nvidia = results.get("nvidia_smi") or {}
    driver_health = 1.0 if nvidia.get("status") == "success" else 0.45 if nvidia.get("status") == "missing" else 0.2
    thermal_load = _thermal_load_from_nvidia(nvidia)
    power_pressure = 0.25
    profile_stdout = str((results.get("powerprofilesctl") or {}).get("stdout") or "").lower()
    if "power-saver" in profile_stdout:
        power_pressure = 0.15
    elif "performance" in profile_stdout:
        power_pressure = 0.45
    signals = {
        "thermal_load": thermal_load,
        "power_pressure": power_pressure,
        "memory_pressure": memory_pressure,
        "storage_pressure": storage_pressure,
        "driver_or_api_health": driver_health,
        "network_pressure": 0.1,
        "identity_or_auth_state": 0.1,
        "permission_complexity": 0.2 if system_context["environment_scope"] == "host" else 0.35,
        "freshness": 1.0,
        "importance": 0.9,
        "safety_risk": clamp01(len(error_lines) / 50.0),
    }
    return {
        "dimensions": [
            "thermal_load",
            "power_pressure",
            "memory_pressure",
            "storage_pressure",
            "driver_or_api_health",
            "network_pressure",
            "identity_or_auth_state",
            "permission_complexity",
            "freshness",
            "importance",
            "safety_risk",
        ],
        "signals": {key: clamp01(value) for key, value in signals.items()},
        "evidence": {
            "journal_error_lines": len(error_lines),
            "nvidia_status": nvidia.get("status", "not_run"),
            "scope": system_context["environment_scope"],
        },
        "fake_success": False,
    }


def _memory_pressure(free_result: dict[str, Any]) -> float:
    stdout = str(free_result.get("stdout") or "")
    for line in stdout.splitlines():
        parts = line.split()
        if parts and parts[0].lower().startswith("mem:") and len(parts) >= 3:
            try:
                total = float(parts[1])
                used = float(parts[2])
                return clamp01(used / total if total else 0.0)
            except (TypeError, ValueError, ZeroDivisionError):
                return 0.0
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
        values: dict[str, float] = {}
        for line in meminfo.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key] = float(value.strip().split()[0]) * 1024.0
        total = values.get("MemTotal", 0.0)
        available = values.get("MemAvailable", 0.0)
        return clamp01((total - available) / total if total else 0.0)
    except Exception:
        return 0.0


def _storage_pressure() -> float:
    try:
        usage = shutil.disk_usage(str(workspace_root()))
        return clamp01(usage.used / usage.total if usage.total else 0.0)
    except Exception:
        return 0.0


def _thermal_load_from_nvidia(nvidia_result: dict[str, Any]) -> float:
    text = f"{nvidia_result.get('stdout', '')}\n{nvidia_result.get('stderr', '')}"
    for marker in (" C", "C "):
        if marker in text:
            break
    numbers: list[float] = []
    for token in text.replace("|", " ").replace(",", " ").split():
        cleaned = token.strip().removesuffix("C").removesuffix("c")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if 20 <= value <= 110:
            numbers.append(value)
    if numbers:
        return clamp01(max(numbers) / 95.0)
    return 0.2 if nvidia_result.get("status") == "success" else 0.0


def _read_os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip().strip('"')
    return result


def _cosmic_hint() -> dict[str, Any]:
    desktop_text = " ".join([os.getenv("XDG_CURRENT_DESKTOP", ""), os.getenv("DESKTOP_SESSION", "")]).lower()
    return {
        "session_mentions_cosmic": "cosmic" in desktop_text,
        "cosmic_session_binary": shutil.which("cosmic-session") is not None,
        "cosmic_settings_binary": shutil.which("cosmic-settings") is not None,
    }


def _system76_hint() -> dict[str, Any]:
    vendor = _read_first_existing(
        Path("/sys/class/dmi/id/sys_vendor"),
        Path("/sys/devices/virtual/dmi/id/sys_vendor"),
    )
    product = _read_first_existing(
        Path("/sys/class/dmi/id/product_name"),
        Path("/sys/devices/virtual/dmi/id/product_name"),
    )
    combined = f"{vendor} {product}".lower()
    return {
        "vendor": vendor,
        "product": product,
        "is_system76": "system76" in combined,
        "system76_power_binary": shutil.which("system76-power") is not None,
    }


def _recovery_partition_hint() -> dict[str, Any]:
    result = _run_command(COMMAND_SPECS["lsblk"])
    text = json.dumps(result, sort_keys=True).lower()
    return {
        "checked": True,
        "detected": "recovery" in text or "pop-recovery" in text,
        "source": "lsblk",
    }


def _read_first_existing(*paths: Path) -> str:
    for path in paths:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
    return ""


def _write_artifact(payload: dict[str, Any]) -> Path:
    out_dir = popos_diagnostics_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"popos_diagnostics_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _save_latest(payload: dict[str, Any]) -> None:
    path = popos_diagnostics_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_latest() -> dict[str, Any]:
    path = popos_diagnostics_state_path()
    if not path.exists():
        return {"status": "missing", "fake_success": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "error", "reason": "State is not an object.", "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}
