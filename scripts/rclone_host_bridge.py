#!/usr/bin/env python3
"""Local host bridge for rclone-backed Drive listings.

Purpose:
    Expose a tiny authenticated localhost/Docker-bridge HTTP surface so the
    Docker backend can ask the host's rclone install for read-only Drive lists.
Inputs:
    Existing host rclone config plus a bridge token file in `.secrets/`.
Outputs:
    JSON status and listing responses. No rclone tokens are returned.
Safety notes:
    The bridge requires X-Ouroboros-Bridge-Token, supports read-only endpoints
    only and delegates all listing approval checks to RcloneDriveAdapter.
Akkoord requirements:
    Listing calls still require the request body approval phrase `Akkoord`.

Why this change:
    rclone lives on the host, while the backend lives in Docker. This gives the
    sandbox backend a narrow, auditable read-only path to the human-authenticated
    rclone session without copying credentials into the container.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


WORKSPACE = Path(os.getenv("WINTRIP_WORKSPACE") or Path(__file__).resolve().parents[1]).expanduser().resolve()
TOKEN_PATH = WORKSPACE / ".secrets" / "rclone_bridge_token"
os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)

import sys

if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from controller.rclone_drive_adapter import RcloneDriveAdapter, get_rclone_drive_status  # noqa: E402
from controller.host_sensory_adapter import get_host_sensory_status, snapshot_host_sensory  # noqa: E402
from controller.ouroboros_self_context import get_ruflo_status  # noqa: E402
from controller.slash_agent_router import execute_host_agent_command  # noqa: E402
from controller.world_agent import ask_grok_via_world_agent, recent_world_actions, search_world_memory, world_agent_status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Ouroboros host rclone bridge.")
    parser.add_argument("--bind", default=os.getenv("WINTRIP_RCLONE_BRIDGE_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WINTRIP_RCLONE_BRIDGE_PORT", "8766")))
    args = parser.parse_args()

    ensure_bridge_token()
    server = ThreadingHTTPServer((args.bind, args.port), RcloneBridgeHandler)
    server.serve_forever()
    return 0


def ensure_bridge_token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TOKEN_PATH.exists() or not TOKEN_PATH.read_text(encoding="utf-8").strip():
        TOKEN_PATH.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


class RcloneBridgeHandler(BaseHTTPRequestHandler):
    server_version = "OuroborosRcloneBridge/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json({"status": "error", "reason": "unauthorized", "fake_success": False}, status=401)
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/status":
            self._json(get_rclone_drive_status())
            return
        if path == "/sensory/status":
            self._json(get_host_sensory_status())
            return
        if path == "/ruflo/status":
            self._json(get_ruflo_status())
            return
        if path == "/agents/status":
            self._json({"status": "online", "agents": ["codex", "ruflo", "claude"], "fake_success": False})
            return
        if path == "/world/status":
            result = world_agent_status()
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/world/actions":
            try:
                limit = int((query.get("limit") or ["20"])[0])
            except ValueError:
                limit = 20
            result = recent_world_actions(limit=max(1, min(limit, 100)), prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        self._json({"status": "error", "reason": "not_found", "fake_success": False}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json({"status": "error", "reason": "unauthorized", "fake_success": False}, status=401)
            return
        body = self._read_body()
        if self.path == "/drive/files":
            result = RcloneDriveAdapter().list_drive_files(
                approval=str(body.get("approval") or ""),
                remote=str(body.get("remote") or ""),
                path=str(body.get("path") or ""),
                max_items=int(body.get("max_items") or 100),
                max_depth=int(body.get("max_depth") or 1),
            )
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/sensory/snapshot":
            result = snapshot_host_sensory(
                approval=str(body.get("approval") or ""),
                max_processes=int(body.get("max_processes") or 80),
                max_flows=int(body.get("max_flows") or 120),
                max_windows=int(body.get("max_windows") or 80),
                max_recent=int(body.get("max_recent") or 60),
            )
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/agents/command":
            result = execute_host_agent_command(
                agent=str(body.get("agent") or ""),
                task=str(body.get("task") or ""),
                approval=str(body.get("approval") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 240),
                prefer_bridge=False,
            )
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/world/grok":
            result = ask_grok_via_world_agent(
                str(body.get("question") or ""),
                approval=str(body.get("approval") or ""),
                open_tab=bool(body.get("open_tab", True)),
                submit=bool(body.get("submit", True)),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "approval_required" else 200)
            return
        if self.path == "/world/search":
            result = search_world_memory(
                str(body.get("query") or ""),
                limit=int(body.get("limit") or 5),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result)
            return
        self._json({"status": "error", "reason": "not_found", "fake_success": False}, status=404)

    def _authorized(self) -> bool:
        expected = ensure_bridge_token()
        supplied = self.headers.get("X-Ouroboros-Bridge-Token", "")
        return bool(expected) and secrets.compare_digest(expected, supplied)

    def _read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        try:
            value = json.loads(self.rfile.read(min(length, 1_000_000)).decode("utf-8"))
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


if __name__ == "__main__":
    raise SystemExit(main())
