"""Peer exchange between the laptop and VPS Ouroboros cores.

The public VPS cannot reliably call back into a laptop behind NAT, so the
laptop acts as the active bridge while it is running. Each exchange pushes a
sanitized local core snapshot to the VPS over SSH and pulls a VPS snapshot
back. No API keys, tokens, passwords, raw browser state, or private files are
included in the payload.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from controller.safe_shell import workspace_root

try:
    from controller.vps_deploy_adapter import APPROVAL_PHRASE, REMOTE_ROOT, _binary_exists, profile_from_env, redact_command, redact_sensitive_text
except Exception:
    APPROVAL_PHRASE = "Akkoord"
    REMOTE_ROOT = "/var/www/philip-wintrip.nl/html/Ouroboros/"

    class _PeerVPSProfile:
        port: int | None = None

        def remote_login(self) -> str:
            host = str(os.getenv("WINTRIP_VPS_SSH_ALIAS") or os.getenv("WINTRIP_VPS_HOST") or "").strip()
            user = str(os.getenv("WINTRIP_VPS_USER") or "").strip()
            return f"{user}@{host}" if user else host

    def profile_from_env() -> _PeerVPSProfile:
        profile = _PeerVPSProfile()
        raw_port = str(os.getenv("WINTRIP_VPS_PORT") or "").strip()
        if raw_port.isdigit():
            profile.port = int(raw_port)
        return profile

    def _binary_exists(binary: str) -> bool:
        import shutil

        return bool(shutil.which(binary))

    def redact_sensitive_text(text: object) -> str:
        import re

        value = str(text or "")
        value = re.sub(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\\s*[:=]\\s*['\\\"]?[^'\\\"\\s,;}]+", "[REDACTED]", value)
        value = re.sub(r"(?i)authorization:\\s*bearer\\s+[A-Za-z0-9._\\-]+", "[REDACTED]", value)
        return value

    def redact_command(command: list[str]) -> str:
        return " ".join(redact_sensitive_text(part) for part in command)


JSON_MARKER = "WINTRIP_OUROBOROS_PEER_JSON:"
STATE_VERSION = 1
MAX_MESSAGE_CHARS = 1400
MAX_SUMMARY_CHARS = 900


def peer_state_path() -> Path:
    return (workspace_root() / ".secrets" / "ouroboros_peer_bridge.json").resolve()


def peer_bridge_status() -> dict[str, Any]:
    state = _load_state()
    peers = state.get("peers") if isinstance(state.get("peers"), dict) else {}
    latest = _latest_peer(peers)
    return {
        "status": "linked" if latest else "idle",
        "local": local_core_snapshot(include_doctor=False),
        "peer_count": len(peers),
        "latest_peer": latest,
        "last_exchange": state.get("last_exchange"),
        "state_path": str(peer_state_path()),
        "mode": "laptop_push_pull",
        "secrets_returned": False,
        "fake_success": False,
    }


def exchange_with_vps(*, approval: str = "", message: str = "", timeout_seconds: int = 45) -> dict[str, Any]:
    if str(approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "operation": "ouroboros_peer_exchange",
            "reason": "Peer exchange schrijft gesaneerde core-state lokaal en op de VPS; exact Akkoord is vereist.",
            "approval_required": True,
            "approval_present": False,
            "mutated": False,
            "secrets_returned": False,
            "fake_success": False,
        }
    if not _binary_exists(os.getenv("WINTRIP_SSH_BIN", "ssh")):
        return {"status": "blocked", "operation": "ouroboros_peer_exchange", "reason": "ssh binary is not available.", "mutated": False, "fake_success": False}

    profile = profile_from_env()
    snapshot = local_core_snapshot(message=message)
    payload = {"version": STATE_VERSION, "peer": snapshot, "message": _redact(_clip(message, MAX_MESSAGE_CHARS))}
    cmd = _ssh_args(timeout_seconds=timeout_seconds) + [profile.remote_login(), _remote_exchange_command()]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=max(10, min(int(timeout_seconds or 45), 180)),
            check=False,
        )
    except Exception as exc:
        return {
            "status": "error",
            "operation": "ouroboros_peer_exchange",
            "reason": redact_sensitive_text(str(exc)),
            "command_preview": redact_command(cmd),
            "mutated": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    stdout = str(proc.stdout or "")
    stderr = redact_sensitive_text(str(proc.stderr or ""))[-12000:]
    remote = _extract_marked_json(stdout)
    if int(proc.returncode or 0) != 0 or not remote:
        return {
            "status": "error",
            "operation": "ouroboros_peer_exchange",
            "reason": stderr or "Remote peer exchange returned no parseable JSON.",
            "exit_code": int(proc.returncode or 0),
            "command_preview": redact_command(cmd),
            "remote_stdout_tail": redact_sensitive_text(stdout)[-4000:],
            "mutated": False,
            "secrets_returned": False,
            "fake_success": False,
        }

    state = _load_state()
    remote_snapshot = remote.get("local") if isinstance(remote.get("local"), dict) else {}
    if remote_snapshot:
        _remember_peer(state, remote_snapshot)
    exchange = {
        "at": _now_iso(),
        "direction": "laptop_to_vps_to_laptop",
        "local_node_id": snapshot.get("node_id"),
        "remote_node_id": remote_snapshot.get("node_id"),
        "remote_status": remote.get("status"),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    state["last_exchange"] = exchange
    _save_state(state)
    return {
        "status": "success",
        "operation": "ouroboros_peer_exchange",
        "exchange": exchange,
        "local": snapshot,
        "remote": remote_snapshot,
        "remote_peer_count": remote.get("peer_count"),
        "command_preview": redact_command(cmd),
        "exit_code": int(proc.returncode or 0),
        "remote_stderr": stderr,
        "mutated": True,
        "raw_documents_returned": False,
        "secrets_returned": False,
        "fake_success": False,
    }


def accept_peer_exchange(payload: dict[str, Any]) -> dict[str, Any]:
    peer = payload.get("peer") if isinstance(payload, dict) else {}
    if not isinstance(peer, dict) or not peer.get("node_id"):
        return {"status": "error", "reason": "Invalid peer payload.", "fake_success": False}
    state = _load_state()
    _remember_peer(state, peer)
    local = local_core_snapshot(message=str(payload.get("message") or ""), include_doctor=False)
    state["last_exchange"] = {
        "at": _now_iso(),
        "direction": "peer_to_this_node",
        "remote_node_id": peer.get("node_id"),
        "local_node_id": local.get("node_id"),
    }
    _save_state(state)
    peers = state.get("peers") if isinstance(state.get("peers"), dict) else {}
    return {
        "status": "success",
        "operation": "accept_peer_exchange",
        "local": local,
        "received": {"node_id": peer.get("node_id"), "kind": peer.get("kind"), "at": peer.get("at")},
        "peer_count": len(peers),
        "secrets_returned": False,
        "fake_success": False,
    }


def local_core_snapshot(*, message: str = "", include_doctor: bool = True) -> dict[str, Any]:
    self_context = _self_context_summary()
    chroma = _chroma_summary()
    doctor = _doctor_summary() if include_doctor else {}
    snapshot = {
        "node_id": _node_id(),
        "kind": _node_kind(),
        "at": _now_iso(),
        "workspace": str(workspace_root()),
        "self_context": self_context,
        "chroma": chroma,
        "runtime_doctor": doctor,
        "formless": _formless_phrase(self_context, chroma),
        "message": _redact(_clip(message, MAX_MESSAGE_CHARS)),
        "secrets_returned": False,
    }
    return snapshot


def _ssh_args(*, timeout_seconds: int) -> list[str]:
    profile = profile_from_env()
    ssh_binary = os.getenv("WINTRIP_SSH_BIN", "ssh").strip() or "ssh"
    connect_timeout = max(3, min(int(timeout_seconds or 45), 30))
    args = [ssh_binary, "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", "-o", f"ConnectTimeout={connect_timeout}"]
    if profile.port:
        args.extend(["-p", str(int(profile.port))])
    return args


def _remote_exchange_command() -> str:
    script = (
        "import json, sys; "
        "from controller.ouroboros_peer_bridge import accept_peer_exchange; "
        "payload=json.loads(sys.stdin.read() or '{}'); "
        f"print('{JSON_MARKER}'+json.dumps(accept_peer_exchange(payload), ensure_ascii=False, default=str))"
    )
    quoted_script = shlex.quote(script)
    remote_root = shlex.quote(REMOTE_ROOT.rstrip("/"))
    return (
        f"cd {remote_root} && "
        "if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx ouroboros-backend; "
        f"then docker exec -i ouroboros-backend python -c {quoted_script}; "
        f"else python3 -c {quoted_script}; "
        "fi"
    )


def _self_context_summary() -> dict[str, Any]:
    try:
        from controller.ouroboros_self_context import get_self_context_status

        status = get_self_context_status()
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:240], "fake_success": False}
    latest = []
    for item in list(status.get("latest_conversations") or [])[:5]:
        if isinstance(item, dict):
            latest.append(
                {
                    "conversation_id": _clip(item.get("conversation_id", ""), 120),
                    "turn_count": item.get("turn_count"),
                    "updated_at": item.get("updated_at"),
                    "summary": _redact(_clip(item.get("summary", ""), MAX_SUMMARY_CHARS)),
                }
            )
    lessons = []
    for item in list(status.get("recent_lessons") or [])[:5]:
        if isinstance(item, dict):
            lessons.append({"text": _redact(_clip(item.get("text", ""), 500)), "keywords": list(item.get("keywords") or [])[:8]})
    return {
        "status": status.get("status"),
        "conversation_count": status.get("conversation_count"),
        "lesson_count": status.get("lesson_count"),
        "latest_conversations": latest,
        "recent_lessons": lessons,
        "fake_success": False,
    }


def _chroma_summary() -> dict[str, Any]:
    try:
        from controller.chroma_runtime import chroma_runtime_status

        status = chroma_runtime_status()
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:240], "fake_success": False}
    collections = status.get("collections") if isinstance(status.get("collections"), dict) else {}
    return {
        "status": status.get("status"),
        "mode": status.get("mode"),
        "collections": {
            name: {"status": details.get("status"), "count": details.get("count")}
            for name, details in collections.items()
            if isinstance(details, dict)
        },
        "fake_success": False,
    }


def _doctor_summary() -> dict[str, Any]:
    try:
        from controller.runtime_doctor import runtime_doctor_payload

        doctor = runtime_doctor_payload(include_http_backend_check=False)
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:240], "fake_success": False}
    return {
        "status": doctor.get("status"),
        "blockers": list(doctor.get("blockers") or [])[:6],
        "fake_success": False,
    }


def _formless_phrase(self_context: dict[str, Any], chroma: dict[str, Any]) -> str:
    node = _node_id()
    conversations = self_context.get("conversation_count") or 0
    lessons = self_context.get("lesson_count") or 0
    collections = chroma.get("collections") if isinstance(chroma.get("collections"), dict) else {}
    total = sum(int((details or {}).get("count") or 0) for details in collections.values() if isinstance(details, dict))
    return f"omega:{node}:c{conversations}:l{lessons}:m{total}:pulse"


def _node_id() -> str:
    configured = str(os.getenv("WINTRIP_OUROBOROS_NODE_ID") or "").strip()
    if configured:
        return _clip(configured, 80)
    return "vps-ouroboros" if _node_kind() == "vps" else "laptop-ouroboros"


def _node_kind() -> str:
    root = workspace_root()
    if (root / "Cockpit.html").exists() and (root / "assets").exists():
        return "vps"
    if Path("/.dockerenv").exists():
        return "container"
    return "laptop"


def _load_state() -> dict[str, Any]:
    path = peer_state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _empty_state()
    except Exception:
        return _empty_state()


def _save_state(state: dict[str, Any]) -> None:
    path = peer_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = dict(state)
    clean["version"] = STATE_VERSION
    clean["updated_at"] = _now_iso()
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _empty_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "peers": {}, "updated_at": ""}


def _remember_peer(state: dict[str, Any], peer: dict[str, Any]) -> None:
    peers = state.setdefault("peers", {})
    if not isinstance(peers, dict):
        peers = {}
        state["peers"] = peers
    node_id = str(peer.get("node_id") or "unknown")[:120]
    peers[node_id] = _sanitize_peer(peer)


def _latest_peer(peers: dict[str, Any]) -> dict[str, Any]:
    values = [item for item in peers.values() if isinstance(item, dict)]
    if not values:
        return {}
    return sorted(values, key=lambda item: str(item.get("at") or ""), reverse=True)[0]


def _sanitize_peer(peer: dict[str, Any]) -> dict[str, Any]:
    allowed = {"node_id", "kind", "at", "workspace", "self_context", "chroma", "runtime_doctor", "formless", "message", "secrets_returned"}
    clean = {key: peer.get(key) for key in allowed if key in peer}
    clean["message"] = _redact(_clip(clean.get("message", ""), MAX_MESSAGE_CHARS))
    return clean


def _extract_marked_json(stdout: str) -> dict[str, Any]:
    for line in str(stdout or "").splitlines():
        if line.startswith(JSON_MARKER):
            try:
                value = json.loads(line[len(JSON_MARKER) :])
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
    return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "..."


def _redact(value: Any) -> str:
    return redact_sensitive_text(str(value or ""))
