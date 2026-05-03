"""Persistent JSON-backed job store.

The store keeps a single `jobs.json` file under the runtime root (default
`.secrets/agent_runtime/`). Writes are atomic via a temp-file rename so a
crash mid-write cannot leave half a payload behind. All access is guarded
by a re-entrant lock so adapters running in worker threads can safely call
`upsert` while the orchestrator is reading.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from controller.agent_runtime.models import JobRecord, utc_now_iso


def _default_runtime_root() -> Path:
    configured = os.getenv("WINTRIP_AGENT_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/home/pwintri2/WintripAI"
    return (Path(workspace) / ".secrets" / "agent_runtime").resolve()


def _default_artifact_root() -> Path:
    configured = os.getenv("WINTRIP_AGENT_RUNTIME_OUT")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/home/pwintri2/WintripAI"
    return (Path(workspace) / "out" / "agent_runtime").resolve()


class JobStore:
    """Thread-safe JSON store for `JobRecord`s."""

    def __init__(self, runtime_root: Path | str | None = None, artifact_root: Path | str | None = None):
        self.runtime_root = Path(runtime_root) if runtime_root else _default_runtime_root()
        self.artifact_root = Path(artifact_root) if artifact_root else _default_artifact_root()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._jobs_path = self.runtime_root / "jobs.json"
        self._lock = threading.RLock()

    @property
    def jobs_path(self) -> Path:
        return self._jobs_path

    def job_dir(self, job_id: str) -> Path:
        path = self.artifact_root / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_payload(self) -> dict[str, Any]:
        if not self._jobs_path.exists():
            return {"jobs": {}, "last_updated": None}
        try:
            payload = json.loads(self._jobs_path.read_text(encoding="utf-8"))
        except Exception:
            return {"jobs": {}, "last_updated": None}
        if not isinstance(payload, dict):
            return {"jobs": {}, "last_updated": None}
        if not isinstance(payload.get("jobs"), dict):
            payload["jobs"] = {}
        return payload

    def _save_payload(self, payload: dict[str, Any]) -> None:
        payload["last_updated"] = utc_now_iso()
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        # In-place truncate + write so the file's inode never changes. Required because
        # the wintrip-standalone-ui container mounts the workspace through Docker
        # Desktop's `fakeowner` overlay, which caches by inode — temp+rename writes
        # would invisibly orphan the container's view of jobs.json.
        with self._jobs_path.open("w", encoding="utf-8") as handle:
            handle.write(text)

    def list_jobs(self, agent: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._load_payload()
        jobs = list(payload.get("jobs", {}).values())
        if agent:
            jobs = [job for job in jobs if str(job.get("agent")) == agent]
        jobs.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return jobs[: max(1, int(limit))]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._load_payload()
        job = payload.get("jobs", {}).get(job_id)
        return dict(job) if isinstance(job, dict) else None

    def upsert(self, record: JobRecord) -> dict[str, Any]:
        record.touch()
        with self._lock:
            payload = self._load_payload()
            payload.setdefault("jobs", {})[record.job_id] = record.to_dict()
            self._save_payload(payload)
        return dict(payload["jobs"][record.job_id])

    def update(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            payload = self._load_payload()
            job = payload.get("jobs", {}).get(job_id)
            if not isinstance(job, dict):
                return None
            job.update(updates)
            job["updated_at"] = utc_now_iso()
            payload["jobs"][job_id] = job
            self._save_payload(payload)
            return dict(job)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            payload = self._load_payload()
            jobs = payload.get("jobs", {})
            if job_id not in jobs:
                return False
            del jobs[job_id]
            self._save_payload(payload)
            return True
