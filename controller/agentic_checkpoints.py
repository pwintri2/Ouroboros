"""Checkpoint metadata for the agentic loop.

This is a deliberately conservative first pass: we do **not** snapshot the
workspace into a shadow git repo. Instead we record the current `HEAD` plus a
`git status --porcelain` view before a mutating tool runs, and store the diff
of changed files after the tool runs. The cockpit can show the user exactly
which files changed and let them inspect the patch. Any *restore* requires an
explicit `Akkoord` from Philip — and is still surfaced as a diff for review,
because we never run destructive `git reset --hard` automatically.

If the workspace is not a git repo (or `git` is missing), the tracker degrades
gracefully and reports `status: unavailable` so the UI can say so honestly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterable
from typing import Any


STATUS_RECORDED = "recorded"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NO_CHANGES = "no_changes"

_GIT_TIMEOUT_SECONDS = 10


def begin_checkpoint(*, workspace_root: str | None = None, reason: str = "") -> dict[str, Any]:
    """Record HEAD + pre-state right before a mutating tool runs."""

    root = _resolve_workspace_root(workspace_root)
    if not _is_git_repo(root):
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "Workspace is geen git repo of git ontbreekt; checkpoint overgeslagen.",
            "workspace_root": root,
            "fake_success": False,
        }
    checkpoint_id = f"checkpoint_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(root, "status", "--porcelain")
    return {
        "status": STATUS_RECORDED,
        "checkpoint_id": checkpoint_id,
        "workspace_root": root,
        "head_before": (head.strip() if head else ""),
        "branch": (branch.strip() if branch else ""),
        "porcelain_before": (status or "").splitlines()[:200],
        "started_at": _ts(),
        "reason": str(reason or "")[:240],
        "fake_success": False,
    }


def finalize_checkpoint(checkpoint: dict[str, Any], *, workspace_root: str | None = None) -> dict[str, Any]:
    """Capture the diff between the recorded HEAD/state and the working tree."""

    if not isinstance(checkpoint, dict) or checkpoint.get("status") != STATUS_RECORDED:
        return dict(checkpoint or {"status": STATUS_UNAVAILABLE, "fake_success": False})
    root = _resolve_workspace_root(workspace_root or checkpoint.get("workspace_root"))
    if not _is_git_repo(root):
        checkpoint["status"] = STATUS_UNAVAILABLE
        checkpoint["reason"] = "Workspace is geen git repo bij finalize; checkpoint geannuleerd."
        return checkpoint
    status_now = _git(root, "status", "--porcelain")
    porcelain_after = (status_now or "").splitlines()[:200]
    changed_files = _porcelain_paths(porcelain_after) - _porcelain_paths(checkpoint.get("porcelain_before") or [])
    new_or_modified = sorted(changed_files)
    diff_stat = _git(root, "diff", "--stat", "HEAD") or ""
    untracked_diff = _git(root, "ls-files", "--others", "--exclude-standard") or ""
    head_after = _git(root, "rev-parse", "HEAD")
    if not new_or_modified and not untracked_diff.strip():
        checkpoint["status"] = STATUS_NO_CHANGES
        checkpoint["porcelain_after"] = porcelain_after
        checkpoint["completed_at"] = _ts()
        return checkpoint
    checkpoint.update(
        {
            "porcelain_after": porcelain_after,
            "changed_files": new_or_modified[:120],
            "changed_files_count": len(new_or_modified),
            "untracked_files": [line for line in untracked_diff.splitlines() if line.strip()][:80],
            "diff_stat": diff_stat.splitlines()[:120],
            "head_after": (head_after.strip() if head_after else ""),
            "completed_at": _ts(),
            "method": "git_diff_snapshot",
        }
    )
    return checkpoint


def diff_for_path(path: str, *, workspace_root: str | None = None, max_lines: int = 400) -> dict[str, Any]:
    """Return a redacted diff for a single path. Read-only operation."""

    root = _resolve_workspace_root(workspace_root)
    if not path or not _is_git_repo(root):
        return {"status": STATUS_UNAVAILABLE, "path": path, "fake_success": False}
    diff = _git(root, "diff", "--no-color", "--", path) or ""
    if not diff.strip():
        diff = _git(root, "diff", "--no-color", "--cached", "--", path) or ""
    lines = diff.splitlines()
    return {
        "status": "ok" if lines else STATUS_NO_CHANGES,
        "path": path,
        "diff": "\n".join(lines[: max(10, int(max_lines or 400))]),
        "truncated": len(lines) > max(10, int(max_lines or 400)),
        "fake_success": False,
    }


def _porcelain_paths(lines: Iterable[str]) -> set[str]:
    paths: set[str] = set()
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        # Porcelain format: XY <path> or XY <path> -> <new_path>
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            continue
        path = parts[1]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path.strip().strip('"'))
    return paths


def _resolve_workspace_root(workspace_root: str | None) -> str:
    base = workspace_root or os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or os.getcwd()
    return os.path.abspath(os.path.expanduser(base))


def _is_git_repo(root: str) -> bool:
    if not root or not os.path.isdir(root):
        return False
    if shutil.which("git") is None:
        return False
    return os.path.isdir(os.path.join(root, ".git")) or _git(root, "rev-parse", "--is-inside-work-tree") == "true"


def _git(root: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _ts() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
