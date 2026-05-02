"""Safe, approval-gated agentic crawler for local ecosystem context.

Purpose:
    Crawl approved local folders, selected logs and settings into compact 11D
    records without treating discovered content as instructions.
Inputs:
    Explicit Akkoord, bounded paths, optional max file count and read-only
    crawler modes.
Outputs:
    File/log/settings metadata, content hashes, skipped privacy reasons and
    11D records under artifacts/crawler/.
Safety notes:
    Default file crawl stores metadata and hashes only. Secret-looking paths are
    skipped, .gitignore is respected for simple patterns, and output is bounded.
Akkoord requirements:
    All crawl functions require approval == "Akkoord".

Why this change:
    The buildplan asks for "crawl everywhere" capabilities. This module makes
    that capability explicit, narrow, auditable and reversible from the start.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, content_hash, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
MAX_FILE_BYTES_FOR_SNIPPET = 32_000
PRIVATE_PARTS = {
    ".secrets",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".config/google-chrome",
    ".config/chromium",
    ".mozilla",
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "wintrip_brain",
    "chromadb",
}
PRIVATE_NAME_MARKERS = (
    ".env",
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "private_key",
    "id_rsa",
)
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".bin"}


def agentic_crawler_state_path() -> Path:
    return (workspace_root() / ".secrets" / "agentic_crawler.json").resolve()


def agentic_crawler_output_dir() -> Path:
    return (workspace_root() / "artifacts" / "crawler").resolve()


def get_agentic_crawler_status() -> dict[str, Any]:
    state = _load_state()
    return {
        "status": state.get("status", "ready"),
        "last_crawl_at": state.get("last_crawl_at"),
        "last_mode": state.get("last_mode", ""),
        "indexed_files": state.get("indexed_files", 0),
        "skipped_private": state.get("skipped_private", 0),
        "pending_approvals": state.get("pending_approvals", []),
        "artifact_path": state.get("artifact_path", ""),
        "state_path": str(agentic_crawler_state_path()),
        "approval_required": True,
        "fake_success": False,
    }


def crawl_filesystem(
    paths: list[str] | tuple[str, ...] | None = None,
    approval: str = "",
    max_files: int = 200,
    include_content: bool = False,
) -> dict[str, Any]:
    """Crawl approved folders into metadata/hash-only 11D records."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    started = time.time()
    roots = _normalize_roots(paths)
    if not roots:
        return {"status": "error", "reason": "No approved crawl roots found.", "fake_success": False}

    max_files = max(1, min(int(max_files), 5000))
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for root in roots:
        gitignore = _load_gitignore(root)
        for current, dirnames, filenames in os.walk(root):
            current_path = Path(current)
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not _is_private_path(current_path / dirname) and not _ignored_by_patterns(root, current_path / dirname, gitignore)
            ]
            for filename in filenames:
                path = current_path / filename
                reason = _skip_reason(path, root, gitignore)
                if reason:
                    skipped.append({"path": _safe_display_path(path), "reason": reason})
                    continue
                try:
                    records.append(_file_record(path, root, include_content=include_content))
                except OSError as exc:
                    skipped.append({"path": _safe_display_path(path), "reason": f"read_error: {exc}"})
                if len(records) >= max_files:
                    break
            if len(records) >= max_files:
                break
        if len(records) >= max_files:
            break

    payload = {
        "status": "success",
        "mode": "filesystem",
        "last_crawl_at": datetime.utcnow().isoformat(),
        "duration_seconds": round(time.time() - started, 3),
        "roots": [str(root) for root in roots],
        "indexed_files": len(records),
        "skipped_private": len(skipped),
        "records": records,
        "skipped": skipped[:200],
        "include_content": include_content,
        "fake_success": False,
    }
    artifact = _write_artifact("filesystem", payload)
    payload["artifact_path"] = str(artifact)
    _save_state(
        {
            "status": "success",
            "last_mode": "filesystem",
            "last_crawl_at": payload["last_crawl_at"],
            "indexed_files": len(records),
            "skipped_private": len(skipped),
            "artifact_path": str(artifact),
            "pending_approvals": [],
            "fake_success": False,
        }
    )
    return payload


def crawl_system_logs(approval: str = "", max_lines: int = 200) -> dict[str, Any]:
    """Collect a bounded current-boot journal error sample."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    max_lines = max(1, min(int(max_lines), 1000))
    if shutil.which("journalctl") is None:
        return {"status": "missing", "reason": "journalctl not available in this runtime.", "fake_success": False}
    try:
        proc = subprocess.run(
            ["journalctl", "-b", "-p", "err", "--no-pager", "-n", str(max_lines)],
            text=True,
            capture_output=True,
            timeout=10,
        )
        text = redact_sensitive_text(f"{proc.stdout}\n{proc.stderr}", max_chars=20000)
        lines = [line for line in text.splitlines() if line.strip()]
        record = build_11d_record(
            source="agentic_crawler",
            record_type="system_log_sample",
            title="journalctl current boot errors",
            summary="\n".join(lines[:50]),
            signals={"safety_risk": min(1.0, len(lines) / 80.0), "importance": 0.8, "freshness": 1.0},
            metadata={"line_count": len(lines), "exit_code": proc.returncode},
        )
        payload = {"status": "success" if proc.returncode == 0 else "error", "line_count": len(lines), "record": record, "exit_code": proc.returncode, "fake_success": False}
        artifact = _write_artifact("system_logs", payload)
        payload["artifact_path"] = str(artifact)
        _save_state({"status": payload["status"], "last_mode": "system_logs", "last_crawl_at": datetime.utcnow().isoformat(), "artifact_path": str(artifact), "indexed_files": 0, "skipped_private": 0, "pending_approvals": [], "fake_success": False})
        return payload
    except Exception as exc:
        return {"status": "error", "reason": redact_sensitive_text(str(exc)), "fake_success": False}


def crawl_settings(approval: str = "") -> dict[str, Any]:
    """Inspect read-only desktop settings if dconf/gsettings are available."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    commands = []
    if shutil.which("gsettings"):
        commands.append(["gsettings", "list-schemas"])
    if shutil.which("dconf"):
        commands.append(["dconf", "dump", "/"])
    results: list[dict[str, Any]] = []
    for command in commands[:2]:
        try:
            proc = subprocess.run(command, text=True, capture_output=True, timeout=8)
            results.append(
                {
                    "command": command,
                    "status": "success" if proc.returncode == 0 else "error",
                    "exit_code": proc.returncode,
                    "stdout": redact_sensitive_text(proc.stdout, max_chars=12000),
                    "stderr": redact_sensitive_text(proc.stderr, max_chars=4000),
                }
            )
        except Exception as exc:
            results.append({"command": command, "status": "error", "reason": redact_sensitive_text(str(exc))})
    record = build_11d_record(
        source="agentic_crawler",
        record_type="settings_inventory",
        title="read-only settings inventory",
        summary=json.dumps([{"command": item.get("command"), "status": item.get("status")} for item in results], sort_keys=True),
        signals={"importance": 0.55, "freshness": 1.0, "safety_risk": 0.25},
        metadata={"command_count": len(results)},
    )
    payload = {"status": "success" if results else "missing", "results": results, "record": record, "fake_success": False}
    artifact = _write_artifact("settings", payload)
    payload["artifact_path"] = str(artifact)
    _save_state({"status": payload["status"], "last_mode": "settings", "last_crawl_at": datetime.utcnow().isoformat(), "artifact_path": str(artifact), "indexed_files": 0, "skipped_private": 0, "pending_approvals": [], "fake_success": False})
    return payload


def propose_cross_service_action(findings: list[dict[str, Any]], target_service: str = "sharepoint") -> dict[str, Any]:
    """Create an approval-gated action proposal from crawler findings."""
    count = len(findings or [])
    target = target_service.lower().strip() or "sharepoint"
    plan = {
        "summary": f"Review {count} local finding(s) and prepare a {target} follow-up.",
        "steps": [
            "Summarize only metadata/hash findings.",
            f"Prepare target {target} action preview.",
            "Request exact Akkoord before any upload, tag, notification or cloud write.",
        ],
        "rollback_plan": "No write occurs during proposal. If later executed, rollback depends on the selected adapter action.",
        "approval_required": True,
    }
    return {"status": "proposal", "target_service": target, "plan": plan, "fake_success": False}


def _normalize_roots(paths: list[str] | tuple[str, ...] | None) -> list[Path]:
    requested = list(paths or [str(workspace_root())])
    roots: list[Path] = []
    for raw in requested:
        path = Path(raw).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            continue
        if not _is_allowed_root(path):
            continue
        if path not in roots:
            roots.append(path)
    return roots


def _is_allowed_root(path: Path) -> bool:
    allowed = [workspace_root().resolve()]
    home = Path.home().resolve()
    for name in ("Documents", "Projects", "OneDrive", "SharePoint", "Downloads"):
        allowed.append((home / name).resolve())
    return any(path == root or root in path.parents for root in allowed)


def _load_gitignore(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns[:500]


def _skip_reason(path: Path, root: Path, gitignore: list[str]) -> str:
    if _is_private_path(path):
        return "privacy_filter"
    if _ignored_by_patterns(root, path, gitignore):
        return "gitignore"
    try:
        if not path.is_file():
            return "not_file"
        if path.stat().st_size > 10_000_000:
            return "too_large"
    except OSError as exc:
        return f"stat_error: {exc}"
    return ""


def _is_private_path(path: Path) -> bool:
    lowered = str(path).lower()
    parts = {part.lower() for part in path.parts}
    if any(private.lower() in parts or private.lower() in lowered for private in PRIVATE_PARTS):
        return True
    name = path.name.lower()
    if any(marker in name for marker in PRIVATE_NAME_MARKERS):
        return True
    return path.suffix.lower() in PRIVATE_SUFFIXES


def _ignored_by_patterns(root: Path, path: Path, patterns: list[str]) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.name
    for pattern in patterns:
        normalized = pattern.rstrip("/")
        if not normalized:
            continue
        if fnmatch.fnmatch(rel, normalized) or fnmatch.fnmatch(path.name, normalized):
            return True
        if "/" not in normalized and any(part == normalized for part in Path(rel).parts):
            return True
    return False


def _file_record(path: Path, root: Path, include_content: bool = False) -> dict[str, Any]:
    stat = path.stat()
    rel = path.relative_to(root).as_posix()
    data = path.read_bytes()
    snippet = ""
    if include_content and len(data) <= MAX_FILE_BYTES_FOR_SNIPPET:
        snippet = redact_sensitive_text(data.decode("utf-8", errors="replace"), max_chars=1500)
    metadata = {
        "path": _safe_display_path(path),
        "relative_path": rel,
        "root": str(root),
        "size_bytes": stat.st_size,
        "mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
        "suffix": path.suffix.lower(),
        "content_hash": content_hash(data),
        "snippet": snippet,
    }
    return build_11d_record(
        source="agentic_crawler",
        record_type="filesystem_file",
        title=rel,
        summary=f"{rel} ({stat.st_size} bytes)",
        signals={
            "storage_pressure": min(1.0, stat.st_size / 10_000_000.0),
            "freshness": 1.0,
            "importance": 0.65 if path.suffix.lower() in {".md", ".py", ".ts", ".tsx", ".json"} else 0.35,
            "safety_risk": 0.2,
        },
        metadata=metadata,
    )


def _safe_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _write_artifact(mode: str, payload: dict[str, Any]) -> Path:
    out_dir = agentic_crawler_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{mode}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _load_state() -> dict[str, Any]:
    path = agentic_crawler_state_path()
    if not path.exists():
        return {"status": "ready", "fake_success": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "error", "reason": "State is not an object.", "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


def _save_state(state: dict[str, Any]) -> None:
    path = agentic_crawler_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
