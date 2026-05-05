"""Codex environment + capability discovery.

This module is the truthful health/integration surface for the local Codex
installation. It deliberately separates several concerns:

1. **Environment detection** (binary, repo root, auth files) — answers
   "is Codex installed and reachable?".
2. **Repo capability inventory** — inspects `/home/pwintri2/Codex` and reports
   which subsystems are present (cli, app-server, mcp, skills, sandboxing, ...).
   Reports honestly whether something is locally invokable, host-only,
   or merely discoverable.
3. **Aggregated status** — combines the above into one structured object that
   the cockpit, slash router, and tests can rely on.

The module never reads or echoes secret material. Auth files are only inspected
for presence/age, never for contents.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_CODEX_REPO_PATH = "/home/pwintri2/Codex"
DEFAULT_CODEX_HOME = Path.home() / ".codex"

# Subsystems we expect to see inside the Codex Rust workspace. Each is a tuple
# of (key, label, repo subdir(s) under codex-rs/, what it represents).
RUST_CAPABILITIES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("cli_exec", "CLI / exec", ("cli",), "Command-line entrypoint and `codex exec` runtime."),
    ("tui", "TUI", ("tui",), "Terminal UI surface."),
    ("app_mode", "App server", ("app-server", "app-server-client", "app-server-protocol"), "App-server protocol used by GUIs and IDE bridges."),
    ("mcp", "MCP server", ("mcp-server", "rmcp-client"), "Model Context Protocol server + client."),
    ("skills", "Skills", ("skills", "core-skills"), "Codex skills runtime and core skills."),
    ("plugins", "Plugins", ("plugin", "core-plugins"), "Plugin runtime and core plugins."),
    ("connectors", "Connectors", ("connectors",), "External service connectors."),
    ("sandboxing", "Sandboxing", ("sandboxing", "process-hardening", "windows-sandbox-rs"), "Sandbox + process hardening primitives."),
    ("memory_state", "Memory & state", ("memories", "state", "thread-store", "thread-manager-sample", "rollout", "rollout-trace"), "Conversation/state/memory subsystems."),
    ("login_auth", "Login / auth", ("login", "aws-auth", "secrets"), "Authentication subsystems (no secret material is read)."),
    ("model_providers", "Model providers", ("model-provider", "model-provider-info", "models-manager", "ollama"), "Model provider integrations and routing."),
    ("realtime", "Realtime / responses", ("realtime-webrtc", "responses-api-proxy", "response-debug-context"), "Realtime + responses-API proxy components."),
    ("execpolicy", "Exec policy", ("shell-command", "shell-escalation", "apply-patch"), "Shell command policy + patch application."),
    ("network", "Network", ("network-proxy", "stdio-to-uds", "uds"), "Network proxy and IPC primitives."),
    ("agent_graph", "Agent graph", ("agent-graph-store", "agent-identity", "collaboration-mode-templates"), "Multi-agent graph + identity runtime."),
    ("cloud_tasks", "Cloud tasks", ("cloud-tasks", "cloud-tasks-client", "cloud-tasks-mock-client", "cloud-requirements"), "Cloud task orchestration (cloud-side, often not local-callable)."),
    ("backend_client", "Backend client", ("backend-client", "codex-client", "codex-api", "codex-backend-openapi-models"), "Codex backend client/SDK glue."),
    ("chatgpt", "ChatGPT integration", ("chatgpt",), "ChatGPT-specific integration crate."),
    ("otel", "OpenTelemetry", ("otel",), "Telemetry support."),
)

# Top-level non-Rust capabilities from the repo root.
ROOT_CAPABILITIES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("cli_npm", "Codex CLI (npm)", ("codex-cli",), "Node-packaged distribution of the Codex CLI."),
    ("docs", "Docs", ("docs",), "Markdown documentation (sandbox.md, mcp.md, slash_commands.md, ...)."),
    ("sdk", "SDK", ("sdk",), "Codex SDK package(s)."),
    ("scripts", "Scripts", ("scripts",), "Repo-level helper scripts."),
    ("third_party", "Third-party", ("third_party",), "Vendored third-party assets."),
    ("patches", "Patches", ("patches",), "Source patches applied during the build."),
)


@dataclass(frozen=True)
class CapabilityRecord:
    key: str
    label: str
    description: str
    detected: bool
    paths: tuple[str, ...]
    invocation: str  # one of: "local_cli", "library_only", "cloud_only", "discoverable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "detected": self.detected,
            "paths": list(self.paths),
            "invocation": self.invocation,
        }


def codex_repo_path() -> Path:
    raw = os.getenv("WINTRIP_CODEX_PATH") or DEFAULT_CODEX_REPO_PATH
    return Path(raw).expanduser().resolve()


def codex_home_path() -> Path:
    raw = os.getenv("CODEX_HOME") or os.getenv("WINTRIP_CODEX_HOME")
    return Path(raw).expanduser().resolve() if raw else DEFAULT_CODEX_HOME


def candidate_binary_paths() -> list[Path]:
    """Return every path where `codex` could plausibly live, in priority order."""

    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            return
        key = str(resolved)
        if key in seen:
            return
        seen.add(key)
        candidates.append(resolved)

    env_override = os.getenv("WINTRIP_CODEX_BINARY") or os.getenv("CODEX_BINARY")
    if env_override:
        add(Path(env_override))

    which = shutil.which("codex")
    if which:
        add(Path(which))

    repo = codex_repo_path()
    add(repo / "codex-rs" / "target" / "release" / "codex")
    add(repo / "codex-rs" / "target" / "debug" / "codex")
    add(repo / "codex-cli" / "bin" / "codex")

    # IDE/extension distributions ship the real native binary; prefer those over
    # the codex.js shim which only forwards to a packaged binary.
    extension_bases = (
        Path.home() / ".windsurf" / "extensions",
        Path.home() / ".vscode" / "extensions",
        Path.home() / ".vscode-server" / "extensions",
        Path.home() / ".antigravity" / "extensions",
        Path.home() / ".cursor" / "extensions",
    )
    for base in extension_bases:
        try:
            for ext_dir in sorted(base.glob("openai.chatgpt-*")):
                for sub in ("bin/linux-x86_64/codex", "bin/codex", "codex"):
                    add(ext_dir / sub)
        except Exception:
            continue

    add(repo / "codex-cli" / "bin" / "codex.js")

    return candidates


def find_codex_binary() -> dict[str, Any]:
    """Locate a usable `codex` binary; never run it here."""

    for path in candidate_binary_paths():
        try:
            if path.exists() and path.is_file() and os.access(path, os.X_OK):
                return {
                    "status": "found",
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                }
        except Exception:
            continue
    return {"status": "missing", "path": None}


def codex_version() -> dict[str, Any]:
    """Run `codex --version` if a binary exists, with a strict timeout."""

    binary = find_codex_binary()
    if binary.get("status") != "found":
        return {"status": "missing", "version": None, "binary": binary}
    path = binary["path"]
    try:
        proc = subprocess.run(
            [path, "--version"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "version": None, "binary": binary}
    except Exception as exc:
        return {"status": "error", "version": None, "binary": binary, "reason": str(exc)[:500]}
    raw = (proc.stdout or proc.stderr or "").strip()
    match = re.search(r"\b\d+\.\d+\.\d+\S*", raw)
    return {
        "status": "online" if proc.returncode == 0 else "error",
        "version": match.group(0) if match else (raw.splitlines()[0] if raw else None),
        "raw": raw[:500],
        "exit_code": proc.returncode,
        "binary": binary,
    }


def codex_auth_summary() -> dict[str, Any]:
    """Inspect ~/.codex/ for auth presence without revealing tokens."""

    home = codex_home_path()
    if not home.exists():
        return {
            "status": "missing",
            "home": str(home),
            "auth_present": False,
            "config_present": False,
            "session_count": 0,
        }
    auth_path = home / "auth.json"
    config_path = home / "config.toml"
    sessions_dir = home / "sessions"
    skills_dir = home / "skills"
    plugins_dir = home / "plugins"
    memories_dir = home / "memories"

    auth_present = auth_path.is_file()
    config_present = config_path.is_file()
    auth_age_seconds: int | None = None
    auth_mode: str | None = None
    if auth_present:
        try:
            auth_age_seconds = max(0, int(time.time() - auth_path.stat().st_mtime))
        except OSError:
            auth_age_seconds = None
        # Light inspection: only structural keys, never secret values.
        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                if "OPENAI_API_KEY" in payload:
                    auth_mode = "api_key"
                elif "tokens" in payload or "access_token" in payload:
                    auth_mode = "oauth"
                else:
                    auth_mode = "unknown"
        except Exception:
            auth_mode = "unreadable"

    session_count = 0
    if sessions_dir.is_dir():
        try:
            session_count = sum(1 for _ in sessions_dir.glob("**/*.jsonl"))
        except Exception:
            session_count = 0

    status = "configured" if (auth_present or config_present) else "missing"
    if auth_present and auth_mode in {"api_key", "oauth"}:
        status = "authenticated"

    return {
        "status": status,
        "home": str(home),
        "auth_present": auth_present,
        "auth_path": str(auth_path) if auth_present else None,
        "auth_age_seconds": auth_age_seconds,
        "auth_mode": auth_mode,
        "config_present": config_present,
        "config_path": str(config_path) if config_present else None,
        "session_count": session_count,
        "sessions_dir": str(sessions_dir) if sessions_dir.exists() else None,
        "skills_dir": str(skills_dir) if skills_dir.exists() else None,
        "plugins_dir": str(plugins_dir) if plugins_dir.exists() else None,
        "memories_dir": str(memories_dir) if memories_dir.exists() else None,
    }


def discover_codex_capabilities() -> dict[str, Any]:
    """Build the Codex capability inventory from repo structure."""

    repo = codex_repo_path()
    if not repo.exists():
        return {
            "status": "missing",
            "repo_path": str(repo),
            "capabilities": [],
            "summary": {"detected": 0, "total": len(RUST_CAPABILITIES) + len(ROOT_CAPABILITIES)},
        }

    rust_root = repo / "codex-rs"
    records: list[CapabilityRecord] = []

    for key, label, subdirs, description in RUST_CAPABILITIES:
        present_paths: list[str] = []
        for subdir in subdirs:
            candidate = rust_root / subdir
            if candidate.exists():
                present_paths.append(str(candidate))
        invocation = _classify_invocation(key, present_paths)
        records.append(
            CapabilityRecord(
                key=key,
                label=label,
                description=description,
                detected=bool(present_paths),
                paths=tuple(present_paths),
                invocation=invocation,
            )
        )

    for key, label, subdirs, description in ROOT_CAPABILITIES:
        present_paths = []
        for subdir in subdirs:
            candidate = repo / subdir
            if candidate.exists():
                present_paths.append(str(candidate))
        invocation = _classify_invocation(key, present_paths)
        records.append(
            CapabilityRecord(
                key=key,
                label=label,
                description=description,
                detected=bool(present_paths),
                paths=tuple(present_paths),
                invocation=invocation,
            )
        )

    detected = sum(1 for record in records if record.detected)
    return {
        "status": "online" if detected else "empty",
        "repo_path": str(repo),
        "rust_workspace": str(rust_root) if rust_root.exists() else None,
        "capabilities": [record.to_dict() for record in records],
        "summary": {
            "detected": detected,
            "total": len(records),
            "rust_detected": sum(1 for record in records[: len(RUST_CAPABILITIES)] if record.detected),
            "root_detected": sum(1 for record in records[len(RUST_CAPABILITIES):] if record.detected),
        },
    }


def codex_repo_evidence() -> dict[str, Any]:
    """Surface concrete repo evidence (manifests, README, docs index)."""

    repo = codex_repo_path()
    if not repo.exists():
        return {"status": "missing", "repo_path": str(repo), "evidence": {}}
    evidence: dict[str, Any] = {}
    for name in ("README.md", "AGENTS.md", "CHANGELOG.md", "package.json", "pnpm-workspace.yaml", "MODULE.bazel", "flake.nix"):
        path = repo / name
        if path.is_file():
            evidence[name] = {
                "path": str(path),
                "size_bytes": path.stat().st_size,
            }
    cargo = repo / "codex-rs" / "Cargo.toml"
    if cargo.is_file():
        evidence["codex-rs/Cargo.toml"] = {
            "path": str(cargo),
            "size_bytes": cargo.stat().st_size,
        }
    docs_dir = repo / "docs"
    if docs_dir.is_dir():
        try:
            doc_files = sorted(p.name for p in docs_dir.glob("*.md"))
        except Exception:
            doc_files = []
        evidence["docs"] = {
            "path": str(docs_dir),
            "file_count": len(doc_files),
            "files": doc_files[:40],
        }
    return {"status": "online" if evidence else "empty", "repo_path": str(repo), "evidence": evidence}


def codex_runtime_jobs(limit: int = 10) -> dict[str, Any]:
    """Recent codex jobs from the agent runtime, lazily fetched."""

    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        jobs = get_orchestrator().list_jobs(agent="codex", limit=max(1, min(int(limit or 10), 50)))
        return {"status": "online", "count": len(jobs), "jobs": jobs}
    except Exception as exc:
        return {"status": "unavailable", "count": 0, "jobs": [], "reason": str(exc)[:500]}


def codex_overall_status() -> dict[str, Any]:
    """Truthful aggregated Codex status object."""

    repo = codex_repo_path()
    repo_present = repo.exists()
    binary = find_codex_binary()
    auth = codex_auth_summary()
    capabilities = discover_codex_capabilities()
    evidence = codex_repo_evidence()
    jobs = codex_runtime_jobs(limit=5)
    version = codex_version() if binary.get("status") == "found" else {"status": "skipped", "version": None, "binary": binary}

    if not repo_present and binary.get("status") != "found":
        overall = "missing"
    elif binary.get("status") != "found":
        overall = "discoverable"
    elif auth.get("status") in {"missing", "unreadable"}:
        overall = "binary_present_no_auth"
    elif auth.get("status") == "authenticated":
        overall = "online"
    else:
        overall = "configured"

    return {
        "status": overall,
        "repo_path": str(repo),
        "repo_present": repo_present,
        "binary": binary,
        "version": version,
        "auth": auth,
        "capabilities": {
            "summary": capabilities.get("summary", {}),
            "status": capabilities.get("status"),
            "rust_workspace": capabilities.get("rust_workspace"),
        },
        "evidence_summary": {key: value.get("size_bytes") for key, value in evidence.get("evidence", {}).items() if isinstance(value, dict)},
        "jobs": jobs,
        "fake_success": False,
    }


def _classify_invocation(key: str, present_paths: list[str]) -> str:
    if not present_paths:
        return "absent"
    if key in {"cli_exec", "tui", "cli_npm"}:
        return "local_cli"
    if key in {"cloud_tasks"}:
        return "cloud_only"
    if key in {"docs", "scripts", "third_party", "patches"}:
        return "discoverable"
    return "library_only"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def iter_capability_keys() -> Iterable[str]:
    for key, *_ in RUST_CAPABILITIES:
        yield key
    for key, *_ in ROOT_CAPABILITIES:
        yield key


__all__ = [
    "CapabilityRecord",
    "candidate_binary_paths",
    "codex_auth_summary",
    "codex_home_path",
    "codex_overall_status",
    "codex_repo_evidence",
    "codex_repo_path",
    "codex_runtime_jobs",
    "codex_version",
    "discover_codex_capabilities",
    "find_codex_binary",
    "iter_capability_keys",
    "RUST_CAPABILITIES",
    "ROOT_CAPABILITIES",
]
