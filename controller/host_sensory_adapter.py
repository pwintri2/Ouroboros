"""Read-only host sensory adapter for Ouroboros.

Purpose:
    Give Ouroboros real, bounded laptop context: active processes, window/app
    hints, network-flow metadata, interfaces and recent activity metadata.
Inputs:
    Exact Akkoord for snapshots. Inside Docker this adapter can use the host
    bridge, so host tools/config stay on the laptop side.
Outputs:
    Compact status, snapshot artifacts and 11D records. No packet payloads,
    keystrokes, passwords, cookies or browser sessions are collected.
Safety notes:
    Fixed read-only commands only. Network sensing is socket/flow metadata, not
    packet capture or LAN forwarding. Sensitive-looking command/path text is
    redacted.
Akkoord requirements:
    snapshot_host_sensory() requires approval == "Akkoord".

Why this change:
    The Mini Router should learn from the real laptop without hijacking the
    LAN. This adapter turns host activity into safe sensory signals that can
    accelerate the 11D pocket.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"


def host_sensory_state_path() -> Path:
    return (workspace_root() / ".secrets" / "host_sensory.json").resolve()


def host_sensory_output_dir() -> Path:
    return (workspace_root() / "artifacts" / "host_sensory").resolve()


def get_host_sensory_status() -> dict[str, Any]:
    bridge = _bridge_request("GET", "/sensory/status", {})
    if bridge:
        bridge["via_bridge"] = True
        return bridge
    state = _load_state()
    return {
        "status": state.get("status", "ready"),
        "scope": state.get("scope", _scope()),
        "last_snapshot_at": state.get("captured_at"),
        "process_count": state.get("process_count", 0),
        "window_count": state.get("window_count", 0),
        "active_flow_count": state.get("active_flow_count", 0),
        "listener_count": state.get("listener_count", 0),
        "interface_count": state.get("interface_count", 0),
        "recent_activity_count": state.get("recent_activity_count", 0),
        "sample_processes": state.get("sample_processes", []),
        "sample_flows": state.get("sample_flows", []),
        "sample_windows": state.get("sample_windows", []),
        "artifact_path": state.get("artifact_path", ""),
        "state_path": str(host_sensory_state_path()),
        "approval_required": True,
        "real_packet_capture": False,
        "real_forwarding": False,
        "fake_success": False,
    }


def snapshot_host_sensory(
    approval: str = "",
    max_processes: int = 80,
    max_flows: int = 120,
    max_windows: int = 80,
    max_recent: int = 60,
) -> dict[str, Any]:
    """Capture a bounded host sensory snapshot."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    bridge = _bridge_request(
        "POST",
        "/sensory/snapshot",
        {
            "approval": approval,
            "max_processes": max_processes,
            "max_flows": max_flows,
            "max_windows": max_windows,
            "max_recent": max_recent,
        },
    )
    if bridge:
        bridge["via_bridge"] = True
        return bridge

    started = time.time()
    processes = _processes(max_items=max_processes)
    flows = _network_flows(max_items=max_flows)
    listeners = _listeners(max_items=max_flows)
    interfaces = _interfaces()
    neighbors = _neighbors()
    windows = _windows(max_items=max_windows)
    recent = _recent_activity(max_items=max_recent)
    summary = {
        "scope": _scope(),
        "process_count": len(processes),
        "active_flow_count": len(flows),
        "listener_count": len(listeners),
        "interface_count": len(interfaces),
        "neighbor_count": len(neighbors),
        "window_count": len(windows),
        "recent_activity_count": len(recent),
    }
    record = build_11d_record(
        source="host_sensory_adapter",
        record_type="host_sensory_summary",
        title="Host sensory snapshot",
        summary=json.dumps(summary, sort_keys=True),
        signals={
            "network_pressure": min(1.0, len(flows) / 80.0),
            "driver_or_api_health": 0.75,
            "identity_or_auth_state": 0.25,
            "permission_complexity": min(1.0, len(listeners) / 50.0),
            "freshness": 1.0,
            "importance": 0.85,
            "safety_risk": 0.25,
        },
        metadata={"scope": _scope(), "real_packet_capture": False, "real_forwarding": False},
    )
    payload = {
        "status": "success",
        "captured_at": datetime.utcnow().isoformat(),
        "duration_seconds": round(time.time() - started, 3),
        "scope": _scope(),
        "summary": summary,
        "processes": processes,
        "network_flows": flows,
        "listeners": listeners,
        "interfaces": interfaces,
        "neighbors": neighbors,
        "windows": windows,
        "recent_activity": recent,
        "record": record,
        "real_packet_capture": False,
        "real_forwarding": False,
        "fake_success": False,
    }
    artifact = _write_artifact(payload)
    state = {
        "status": "success",
        "captured_at": payload["captured_at"],
        "duration_seconds": payload["duration_seconds"],
        "scope": payload["scope"],
        "process_count": len(processes),
        "active_flow_count": len(flows),
        "listener_count": len(listeners),
        "interface_count": len(interfaces),
        "neighbor_count": len(neighbors),
        "window_count": len(windows),
        "recent_activity_count": len(recent),
        "sample_processes": processes[:12],
        "sample_flows": flows[:24],
        "sample_windows": windows[:12],
        "artifact_path": str(artifact),
        "real_packet_capture": False,
        "real_forwarding": False,
        "fake_success": False,
    }
    _save_state(state)
    payload["artifact_path"] = str(artifact)
    return payload


def _processes(max_items: int) -> list[dict[str, Any]]:
    if shutil.which("ps") is None:
        return []
    result = _run(["ps", "-eo", "pid,ppid,comm,%cpu,%mem,etime,args", "--sort=-%cpu"], timeout=6, limit=300_000)
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(result.get("stdout", "").splitlines()):
        if index == 0 or len(rows) >= max_items:
            continue
        parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        rows.append(
            {
                "pid": _int(parts[0]),
                "ppid": _int(parts[1]),
                "comm": redact_sensitive_text(parts[2], max_chars=160),
                "cpu": _float(parts[3]),
                "mem": _float(parts[4]),
                "etime": parts[5],
                "args": _sanitize_args(parts[6]),
            }
        )
    return rows


def _network_flows(max_items: int) -> list[dict[str, Any]]:
    command = ["ss", "-tunp"] if shutil.which("ss") else []
    if not command:
        return []
    result = _run(command, timeout=6, limit=300_000)
    return _parse_ss(result.get("stdout", ""), max_items=max_items, include_listen=False)


def _listeners(max_items: int) -> list[dict[str, Any]]:
    command = ["ss", "-tulpen"] if shutil.which("ss") else []
    if not command:
        return []
    result = _run(command, timeout=6, limit=300_000)
    return _parse_ss(result.get("stdout", ""), max_items=max_items, include_listen=True)


def _parse_ss(text: str, max_items: int, include_listen: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if len(rows) >= max_items:
            break
        if not line or line.startswith("Netid") or line.startswith("State"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        proto = parts[0]
        state = parts[1] if proto in {"tcp", "udp"} else ""
        if not include_listen and state.upper() == "LISTEN":
            continue
        local = parts[4] if len(parts) > 4 else ""
        peer = parts[5] if len(parts) > 5 else ""
        proc = " ".join(part for part in parts[6:] if "users:" in part or "pid=" in part)
        rows.append(
            {
                "proto": proto,
                "state": state,
                "local": _safe_endpoint(local),
                "peer": _safe_endpoint(peer),
                "process": _sanitize_process_hint(proc),
            }
        )
    return rows


def _interfaces() -> list[dict[str, Any]]:
    interfaces: list[dict[str, Any]] = []
    path = Path("/proc/net/dev")
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[2:]:
            if ":" not in line:
                continue
            name, rest = line.split(":", 1)
            values = rest.split()
            interfaces.append(
                {
                    "name": name.strip(),
                    "rx_bytes": _int(values[0]) if values else 0,
                    "tx_bytes": _int(values[8]) if len(values) > 8 else 0,
                }
            )
    if shutil.which("nmcli"):
        result = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], timeout=5, limit=60_000)
        status_by_name = {}
        for line in result.get("stdout", "").splitlines():
            parts = line.split(":")
            if len(parts) >= 4:
                status_by_name[parts[0]] = {"type": parts[1], "state": parts[2], "connection": redact_sensitive_text(parts[3], max_chars=160)}
        for item in interfaces:
            item.update(status_by_name.get(item["name"], {}))
    return interfaces[:80]


def _neighbors() -> list[dict[str, str]]:
    if shutil.which("ip") is None:
        return []
    result = _run(["ip", "neigh"], timeout=5, limit=80_000)
    rows = []
    for line in result.get("stdout", "").splitlines()[:80]:
        rows.append({"summary": redact_sensitive_text(line, max_chars=300)})
    return rows


def _windows(max_items: int) -> list[dict[str, str]]:
    if shutil.which("wmctrl") is None:
        return []
    result = _run(["wmctrl", "-lx"], timeout=5, limit=100_000)
    rows: list[dict[str, str]] = []
    for line in result.get("stdout", "").splitlines():
        if len(rows) >= max_items:
            break
        parts = line.split(None, 4)
        if len(parts) >= 5:
            rows.append({"window_id": parts[0], "desktop": parts[1], "wm_class": parts[2], "title": redact_sensitive_text(parts[4], max_chars=300)})
    return rows


def _recent_activity(max_items: int) -> list[dict[str, str]]:
    path = Path.home() / ".local" / "share" / "recently-used.xbel"
    if not path.exists():
        return []
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace")[-2_000_000:])
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for bookmark in list(root.findall("{*}bookmark"))[-max_items:]:
        href = str(bookmark.get("href") or "")
        if _sensitive_text(href):
            continue
        rows.append(
            {
                "href": redact_sensitive_text(href, max_chars=500),
                "modified": str(bookmark.get("modified") or ""),
                "visited": str(bookmark.get("visited") or ""),
            }
        )
    return rows[-max_items:]


def _sanitize_args(value: str) -> str:
    text = redact_sensitive_text(value, max_chars=500)
    if _sensitive_text(text):
        return "<redacted-sensitive-command>"
    return text


def _sanitize_process_hint(value: str) -> str:
    return redact_sensitive_text(value, max_chars=300)


def _safe_endpoint(value: str) -> str:
    text = str(value or "")
    if text in {"*", "*:*", "0.0.0.0:*", "[::]:*"}:
        return text
    return redact_sensitive_text(text, max_chars=220)


def _sensitive_text(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(marker in lowered for marker in ("token", "secret", "password", "passwd", ".secrets", ".ssh", ".gnupg", "cookie", "credential"))


def _scope() -> str:
    return "docker_container" if Path("/.dockerenv").exists() else "host"


def _run(command: list[str], timeout: int, limit: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": redact_sensitive_text(proc.stdout or "", max_chars=limit),
            "stderr": redact_sensitive_text(proc.stderr or "", max_chars=8000),
        }
    except Exception as exc:
        return {"status": "error", "exit_code": None, "stdout": "", "stderr": redact_sensitive_text(str(exc))}


def _write_artifact(payload: dict[str, Any]) -> Path:
    out_dir = host_sensory_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"host_sensory_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _load_state() -> dict[str, Any]:
    path = host_sensory_state_path()
    if not path.exists():
        return {"status": "ready", "fake_success": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "error", "reason": "State is not an object.", "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


def _save_state(state: dict[str, Any]) -> None:
    path = host_sensory_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _bridge_request(method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").strip()
    if not base_url:
        return {}
    token = _bridge_token()
    if not token:
        return {}
    data = json.dumps(payload).encode("utf-8") if method == "POST" else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ouroboros-Bridge-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _bridge_token() -> str:
    configured = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else (workspace_root() / ".secrets" / "rclone_bridge_token").resolve()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0


def _float(value: Any) -> float:
    try:
        return round(float(str(value).strip()), 4)
    except Exception:
        return 0.0
