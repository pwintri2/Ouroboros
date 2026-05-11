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
    The bridge requires X-Ouroboros-Bridge-Token. Read-only status endpoints
    never return credentials; mutating/agent command endpoints keep their own
    approval checks.
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
import socketserver
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
from controller.computer_actions import computer_actions_status, run_computer_action  # noqa: E402
from controller.host_sensory_adapter import get_host_sensory_status, snapshot_host_sensory  # noqa: E402
from controller.ouroboros_self_context import get_ruflo_status  # noqa: E402
from controller.vps_deploy_adapter import VPSDeployAdapter  # noqa: E402
from controller.chroma_sync_adapter import ChromaSyncAdapter  # noqa: E402
from controller.roo_cli_runtime import roo_auth_login, roo_cli_status, roo_cloud_models, run_roo_cli_task  # noqa: E402
from controller.slash_agent_router import execute_host_agent_command  # noqa: E402
from controller.world_agent import ask_grok_via_world_agent, recent_world_actions, search_world_memory, world_agent_status  # noqa: E402
from controller.world_agent import open_url_via_world_agent  # noqa: E402
from controller.external_capabilities import external_capabilities_status  # noqa: E402
from controller.project_context import (  # noqa: E402
    get_changed_files,
    get_context_summary,
    get_file_tree,
    get_project_structure_summary,
    get_test_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Ouroboros host rclone bridge.")
    parser.add_argument("--bind", default=os.getenv("WINTRIP_RCLONE_BRIDGE_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WINTRIP_RCLONE_BRIDGE_PORT", "8766")))
    args = parser.parse_args()

    ensure_bridge_token()
    server = FastThreadingHTTPServer((args.bind, args.port), RcloneBridgeHandler)
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
        if path == "/computer/status":
            result = computer_actions_status()
            result["via_bridge"] = False
            result["host_bridge_runtime"] = {
                "status": "online",
                "server": self.server_version,
                "workspace": str(WORKSPACE),
                "fake_success": False,
            }
            self._json(result)
            return
        if path == "/sensory/status":
            self._json(get_host_sensory_status())
            return
        if path == "/ruflo/status":
            self._json(get_ruflo_status())
            return
        if path == "/vps/status":
            result = VPSDeployAdapter(workspace=WORKSPACE).status(prefer_bridge=False)
            result["via_bridge"] = False
            result["host_bridge_runtime"] = {"status": "online", "server": self.server_version, "fake_success": False}
            self._json(result)
            return
        if path == "/chroma-sync/status":
            result = ChromaSyncAdapter(workspace=WORKSPACE).status(
                timeout_seconds=self._query_int(query, "timeout_seconds", 45, minimum=10, maximum=300),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            result["host_bridge_runtime"] = {"status": "online", "server": self.server_version, "fake_success": False}
            self._json(result)
            return
        if path == "/agents/status":
            self._json({"status": "online", "agents": ["codex", "deepseek", "atlas", "ruflo", "claude", "roo"], "fake_success": False})
            return
        if path == "/roo/status":
            result = roo_cli_status()
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/roo/models":
            result = roo_cloud_models()
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/deepseek/status":
            from controller.agent_runtime.adapters.ecosystem_cli import deepseek_status

            result = deepseek_status(prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/deepseek/capabilities":
            from controller.agent_runtime.adapters.ecosystem_cli import discover_deepseek_capabilities

            result = discover_deepseek_capabilities()
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/deepseek/doctor":
            from controller.agent_runtime.adapters.ecosystem_cli import deepseek_doctor

            result = deepseek_doctor(prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/atlas/status":
            from controller.agent_runtime.adapters.ecosystem_cli import atlas_status

            result = atlas_status(prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/atlas/capabilities":
            from controller.agent_runtime.adapters.ecosystem_cli import discover_atlas_capabilities

            result = discover_atlas_capabilities()
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/atlas/doctor":
            from controller.agent_runtime.adapters.ecosystem_cli import atlas_doctor

            result = atlas_doctor(prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/agents/agents-status":
            from controller.agent_runtime.adapters.agents_cli import agents_status

            self._json(agents_status())
            return
        if path == "/agents/agents-capabilities":
            from controller.agent_runtime.adapters.agents_cli import discover_capabilities as agents_capabilities

            self._json(agents_capabilities())
            return
        if path == "/openhands/status":
            from controller.agent_runtime.adapters.openhands_adapter import openhands_status

            self._json(openhands_status())
            return
        if path == "/openhands/capabilities":
            from controller.agent_runtime.adapters.openhands_adapter import discover_capabilities as openhands_capabilities

            self._json(openhands_capabilities())
            return
        if path == "/world/status":
            result = world_agent_status()
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/external/capabilities":
            result = external_capabilities_status(prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/context/summary":
            result = get_context_summary(prefer_bridge=False)
            result["via_bridge"] = False
            self._json(result)
            return
        if path in {"/context/file_tree", "/context/file-tree"}:
            result = get_file_tree(
                max_depth=self._query_int(query, "max_depth", 3, minimum=1, maximum=8),
                limit=self._query_int(query, "limit", 500, minimum=1, maximum=2000),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result)
            return
        if path in {"/context/changed_files", "/context/changed-files"}:
            result = get_changed_files(
                limit=self._query_int(query, "limit", 50, minimum=1, maximum=500),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/context/test_files":
            result = get_test_files(
                limit=self._query_int(query, "limit", 100, minimum=1, maximum=500),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result)
            return
        if path == "/context/structure":
            result = get_project_structure_summary(prefer_bridge=False)
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
        if self.path == "/computer/action":
            raw_args = body.get("args")
            action_args = dict(raw_args) if isinstance(raw_args, dict) else {}
            if not action_args:
                action_args = {str(key): value for key, value in body.items() if key not in {"action", "tool", "name", "args"}}
            elif "approval" in body and "approval" not in action_args:
                action_args["approval"] = body.get("approval")
            action_name = str(body.get("action") or body.get("tool") or body.get("name") or "")
            if action_name in {"host_open_url", "host_browser_open_url"}:
                action_name = "browser_open_url"
            result = run_computer_action(action_name, action_args)
            result["via_bridge"] = False
            result["host_bridge_runtime"] = {"status": "online", "server": self.server_version, "fake_success": False}
            self._json(result, status=403 if result.get("status") in {"blocked", "approval_required"} else 200)
            return
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
        if self.path == "/vps/login-check":
            result = VPSDeployAdapter(workspace=WORKSPACE).login_check(
                timeout_seconds=int(body.get("timeout_seconds") or 120),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/vps/sync-preview":
            result = VPSDeployAdapter(workspace=WORKSPACE).sync_preview(
                remote_path=str(body.get("remote_path") or body.get("remote_target") or ""),
                source_path=str(body.get("source_path") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 120),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/vps/sync-execute":
            result = VPSDeployAdapter(workspace=WORKSPACE).sync_execute(
                approval=str(body.get("approval") or ""),
                remote_path=str(body.get("remote_path") or body.get("remote_target") or ""),
                source_path=str(body.get("source_path") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 120),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/vps/ui-sync-preview":
            result = VPSDeployAdapter(workspace=WORKSPACE).ui_sync_preview(
                remote_path=str(body.get("remote_path") or body.get("remote_target") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 120),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/vps/ui-sync-execute":
            result = VPSDeployAdapter(workspace=WORKSPACE).ui_sync_execute(
                approval=str(body.get("approval") or ""),
                remote_path=str(body.get("remote_path") or body.get("remote_target") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 120),
                build_first=bool(body.get("build_first", True)),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/chroma-sync/preview":
            result = ChromaSyncAdapter(workspace=WORKSPACE).preview(
                timeout_seconds=int(body.get("timeout_seconds") or 120),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/chroma-sync/execute":
            result = ChromaSyncAdapter(workspace=WORKSPACE).execute(
                approval=str(body.get("approval") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 300),
                prefer_bridge=False,
            )
            result["via_bridge"] = False
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
        if self.path == "/roo/run":
            result = run_roo_cli_task(
                task=str(body.get("task") or ""),
                provider=str(body.get("provider") or "ollama"),
                model=str(body.get("model") or ""),
                approval=str(body.get("approval") or ""),
                workspace=str(body.get("workspace") or WORKSPACE),
                output_dir=str(body.get("output_dir") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 600),
                api_key=str(body.get("api_key") or ""),
                mode=str(body.get("mode") or "code"),
            )
            result["via_bridge"] = False
            self._json(result, status=403 if result.get("status") == "blocked" else 200)
            return
        if self.path == "/roo/auth/login":
            result = roo_auth_login(
                approval=str(body.get("approval") or ""),
                timeout_seconds=int(body.get("timeout_seconds") or 10),
            )
            result["via_bridge"] = False
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
        if self.path == "/browser/open-url":
            result = open_url_via_world_agent(
                str(body.get("url") or ""),
                approval=str(body.get("approval") or ""),
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

    @staticmethod
    def _query_int(query: dict[str, list[str]], key: str, default: int, *, minimum: int, maximum: int) -> int:
        try:
            value = int((query.get(key) or [str(default)])[0])
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class FastThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server variant that avoids slow reverse DNS on 0.0.0.0 binds."""

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


if __name__ == "__main__":
    raise SystemExit(main())
