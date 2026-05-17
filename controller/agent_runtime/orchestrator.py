"""Agent orchestrator: dispatches jobs to adapters and tracks lifecycle.

Adapters are looked up in `AGENT_DISPATCH`; host-only agents can also be
registered dynamically by routes or slash commands.

The orchestrator is intentionally stateless across processes: state lives in
`JobStore`. A module-level singleton (`get_orchestrator()`) gives the
FastAPI handlers and the slash router a shared instance, but tests can
construct their own orchestrator with custom store/adapter for isolation.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from controller.agent_runtime.events import EventLog
from controller.agent_runtime.models import JobRecord, new_job_id, utc_now_iso
from controller.agent_runtime.store import JobStore

try:
    from controller.ouroboros_esoteric_bridge import enrich_job_record, reflect_job_result
except Exception:
    enrich_job_record = None
    reflect_job_result = None

try:
    from ouroboros_esoteric.quantum_corruption_nexus import get_quantum_corruption_nexus
except Exception:
    get_quantum_corruption_nexus = None

try:
    from controller.nexus_status import ingest_event as _ingest_nexus_event
except Exception:
    _ingest_nexus_event = None

try:
    from controller.memory_event_router import record_trigger_action as _record_trigger_action_event
except Exception:
    _record_trigger_action_event = None


AdapterFn = Callable[[JobRecord, EventLog, Callable[[dict[str, Any]], None]], dict[str, Any]]


def _default_codex_adapter(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    # Lazy import to keep `adapters/__init__.py` cheap and avoid circulars.
    from controller.agent_runtime.adapters.codex_cli import run_codex_job

    return run_codex_job(job, log, on_progress=on_progress)


def _default_deepseek_adapter(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    from controller.agent_runtime.adapters.ecosystem_cli import run_deepseek_job

    return run_deepseek_job(job, log, on_progress=on_progress)


def _default_atlas_adapter(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    from controller.agent_runtime.adapters.ecosystem_cli import run_atlas_job

    return run_atlas_job(job, log, on_progress=on_progress)


def _default_roo_adapter(job: JobRecord, log: EventLog, on_progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    from controller.agent_runtime.adapters.roo_cli import run_roo_job

    return run_roo_job(job, log, on_progress=on_progress)


AGENT_DISPATCH: dict[str, AdapterFn] = {
    "codex": _default_codex_adapter,
    "deepseek": _default_deepseek_adapter,
    "atlas": _default_atlas_adapter,
    "roo": _default_roo_adapter,
}


class AgentOrchestrator:
    """Creates jobs, dispatches them to adapters, tracks state."""

    def __init__(
        self,
        store: JobStore | None = None,
        *,
        adapters: dict[str, AdapterFn] | None = None,
        thread_factory: Callable[..., threading.Thread] | None = None,
        workspace_root: Path | str | None = None,
        allowed_roots: list[str] | None = None,
        default_timeout_seconds: int = 240,
    ):
        self.store = store or JobStore()
        self.adapters = dict(adapters or AGENT_DISPATCH)
        self._thread_factory = thread_factory or (lambda **kwargs: threading.Thread(daemon=True, **kwargs))
        self.workspace_root = Path(workspace_root) if workspace_root else _default_workspace_root()
        self.allowed_roots = allowed_roots or _default_allowed_roots()
        self.default_timeout_seconds = max(1, int(default_timeout_seconds or 240))
        self._cancel_flags: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def register_adapter(self, agent: str, adapter: AdapterFn) -> None:
        self.adapters[str(agent).lower()] = adapter

    def supported_agents(self) -> list[str]:
        return sorted(self.adapters.keys())

    def create_job(
        self,
        agent: str,
        task: str,
        *,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        agent_key = str(agent or "").strip().lower()
        if agent_key not in self.adapters:
            raise ValueError(f"Unsupported agent: {agent_key!r}")
        cleaned_task = str(task or "").strip()
        if not cleaned_task:
            raise ValueError("Task is empty.")

        job_id = new_job_id(agent_key)
        job_dir = self.store.job_dir(job_id)
        record = JobRecord(
            job_id=job_id,
            agent=agent_key,
            task=cleaned_task,
            status="queued",
            workspace_root=str(self.workspace_root),
            allowed_roots=list(self.allowed_roots),
            timeout_seconds=int(timeout_seconds or self.default_timeout_seconds),
            output_dir=str(job_dir),
            stdout_file=str(job_dir / "stdout.log"),
            stderr_file=str(job_dir / "stderr.log"),
            events_file=str(job_dir / "events.jsonl"),
            result_file=str(job_dir / "result.json"),
            output_file=str(job_dir / "output.md"),
            metadata=dict(metadata or {}),
        )
        # prompt.md is helpful for humans inspecting the artifact dir.
        try:
            (job_dir / "prompt.md").write_text(self._prompt_markdown(record), encoding="utf-8")
        except Exception:
            pass

        esoteric_context: dict[str, Any] | None = None
        if enrich_job_record is not None:
            try:
                esoteric_context = enrich_job_record(record)
            except Exception as exc:
                record.metadata.setdefault("ouroboros_esoteric", {"enabled": False, "reason": str(exc)})

        nexus_created: dict[str, Any] | None = None
        if get_quantum_corruption_nexus is not None:
            try:
                nexus_created = get_quantum_corruption_nexus().analyze_job(record, {"status": "queued"}, phase="created")
                nexus_meta = dict(record.metadata.get("quantum_corruption_nexus") or {})
                nexus_meta["created_event"] = nexus_created
                record.metadata["quantum_corruption_nexus"] = nexus_meta
            except Exception:
                nexus_created = None

        self.store.upsert(record)
        log = EventLog(record.events_file)
        log.append("created", {"agent": agent_key, "task_chars": len(cleaned_task), "job_id": job_id})
        if _record_trigger_action_event is not None:
            try:
                _record_trigger_action_event(
                    trigger="agent_runtime_job_created",
                    action=f"{agent_key}.submit",
                    route="agent_runtime",
                    status="queued",
                    payload={"task": cleaned_task, "metadata": record.metadata},
                    approval_required=bool(record.metadata.get("approval_status") == "approved" or record.metadata.get("approval")),
                    approval_status=str(record.metadata.get("approval_status") or "not_required"),
                    source_trace={"job_id": job_id, "agent": agent_key, "events_file": record.events_file},
                )
            except Exception:
                pass
        if esoteric_context:
            log.append("ouroboros_esoteric_context", esoteric_context)
        if nexus_created:
            log.append("quantum_corruption_nexus", nexus_created)
        if _ingest_nexus_event is not None:
            try:
                _ingest_nexus_event(
                    "agent_runtime",
                    "job_created",
                    f"{agent_key} job {job_id[-8:]} queued",
                    job_id=job_id,
                    agent=agent_key,
                    timeout_seconds=record.timeout_seconds,
                )
            except Exception:
                pass
        return record

    def start_job(self, job: JobRecord) -> threading.Thread:
        adapter = self.adapters.get(job.agent)
        if adapter is None:
            raise ValueError(f"No adapter registered for {job.agent!r}")
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_flags[job.job_id] = cancel_event

        # Smuggle a cancel-check the adapter can poll without us leaking
        # threading internals through the public API.
        setattr(job, "_cancel_check", cancel_event.is_set)

        def runner() -> None:
            self._run(job, adapter, cancel_event)

        thread = self._thread_factory(target=runner, name=f"agent-job-{job.job_id}")
        thread.start()
        return thread

    def submit(
        self,
        agent: str,
        task: str,
        *,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        record = self.create_job(agent, task, timeout_seconds=timeout_seconds, metadata=metadata)
        self.start_job(record)
        return record

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            event = self._cancel_flags.get(job_id)
        if event is not None:
            event.set()
        updates: dict[str, Any] = {"cancel_requested": True}
        current = self.store.get(job_id)
        if current and current.get("status") in {"queued", "planning"}:
            updates["status"] = "cancelled"
            updates["finished_at"] = utc_now_iso()
        updated = self.store.update(job_id, updates)
        if updated and current and current.get("events_file"):
            EventLog(current["events_file"]).append("cancel_requested", {})
        return updated

    def list_jobs(self, agent: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self._reconcile_stale_jobs(agent=agent, limit=limit)
        return self.store.list_jobs(agent=agent, limit=limit)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get(job_id)

    def read_events(self, job_id: str, after_index: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        record = self.store.get(job_id)
        if not record or not record.get("events_file"):
            return []
        events_file = self._resolve_artifact_path(record["events_file"])
        return EventLog(events_file).read(after_index=after_index, limit=limit)

    def _resolve_artifact_path(self, recorded_path: str) -> str:
        """Map a recorded path to the local view.

        Jobs may be created on the host (e.g. via the bridge) and read inside
        the container. The host writes paths like `/home/pwintri2/WintripAI/out/...`
        while the container only sees `/workspace/out/...`. If the recorded
        path doesn't exist locally, try translating its prefix to the local
        workspace root.
        """

        if not recorded_path:
            return recorded_path
        if Path(recorded_path).exists():
            return recorded_path
        local_root = str(self.workspace_root).rstrip("/")
        # Common host roots that may appear in records when the writer was the host.
        for host_root in ("/home/pwintri2/WintripAI", "/workspace"):
            if host_root == local_root:
                continue
            if recorded_path.startswith(host_root + "/"):
                candidate = local_root + recorded_path[len(host_root):]
                if Path(candidate).exists():
                    return candidate
        return recorded_path

    def _run(self, job: JobRecord, adapter: AdapterFn, cancel_event: threading.Event) -> None:
        log = EventLog(job.events_file)
        started_at = utc_now_iso()
        self.store.update(job.job_id, {"status": "running", "started_at": started_at})
        log.append("status", {"status": "running", "started_at": started_at})

        def on_progress(payload: dict[str, Any]) -> None:
            try:
                self.store.update(job.job_id, payload)
                log.append("progress", dict(payload))
            except Exception:
                pass

        result: dict[str, Any]
        try:
            result = adapter(job, log, on_progress) or {}
        except Exception as exc:
            log.append("error", {"reason": str(exc)})
            result = {"status": "failed", "exit_code": None, "reason": str(exc)}
        finally:
            with self._lock:
                self._cancel_flags.pop(job.job_id, None)

        if cancel_event.is_set() and result.get("status") not in {"cancelled"}:
            result["status"] = "cancelled"
            result["cancelled"] = True

        finished_at = utc_now_iso()
        updates: dict[str, Any] = {
            "status": result.get("status") or "completed",
            "exit_code": result.get("exit_code"),
            "finished_at": finished_at,
            "response_preview": str(result.get("response_preview") or "")[:2000],
        }
        if "pid" in result and result["pid"] is not None:
            updates["pid"] = result["pid"]
        if result.get("reason"):
            updates["result_summary"] = str(result.get("reason"))
        metadata_update: dict[str, Any] | None = None
        reflection: dict[str, Any] | None = None
        if reflect_job_result is not None:
            try:
                reflection = reflect_job_result(job, result)
                current = self.store.get(job.job_id) or {}
                metadata = dict(current.get("metadata") or job.metadata or {})
                esoteric = dict(metadata.get("ouroboros_esoteric") or {})
                esoteric["last_reflection"] = reflection
                metadata["ouroboros_esoteric"] = esoteric
                metadata_update = metadata
            except Exception as exc:
                log.append("ouroboros_esoteric_error", {"reason": str(exc)})

        nexus_event: dict[str, Any] | None = None
        if get_quantum_corruption_nexus is not None:
            try:
                nexus_event = get_quantum_corruption_nexus().analyze_job(job, result, phase="finished")
                current = self.store.get(job.job_id) or {}
                metadata = dict((metadata_update or current.get("metadata") or job.metadata or {}))
                nexus_meta = dict(metadata.get("quantum_corruption_nexus") or {})
                nexus_meta["last_event"] = nexus_event
                nexus_meta["omega_vector"] = get_quantum_corruption_nexus().status(limit=1).get("omega_vector", {})
                metadata["quantum_corruption_nexus"] = nexus_meta
                metadata_update = metadata
            except Exception as exc:
                log.append("quantum_corruption_nexus_error", {"reason": str(exc)})

        try:
            Path(job.result_file).write_text(_safe_json(result), encoding="utf-8")
        except Exception:
            pass

        if metadata_update is not None:
            updates["metadata"] = metadata_update
        self.store.update(job.job_id, updates)
        if reflection is not None:
            log.append("ouroboros_esoteric_reflection", reflection)
        if nexus_event is not None:
            log.append("quantum_corruption_nexus", nexus_event)
            _notify_living_agent_event(
                {
                    "agent": job.agent,
                    "job_id": job.job_id,
                    "status": updates["status"],
                    "action": nexus_event.get("action"),
                    "reason": nexus_event.get("reason"),
                }
            )
        log.append("status", {"status": updates["status"], "finished_at": finished_at, "exit_code": updates.get("exit_code")})
        if _record_trigger_action_event is not None:
            try:
                _record_trigger_action_event(
                    trigger="agent_runtime_job_finished",
                    action=f"{job.agent}.finish",
                    route="agent_runtime",
                    status=str(updates["status"]),
                    payload={"task": job.task, "metadata": job.metadata},
                    result={
                        "status": updates["status"],
                        "exit_code": updates.get("exit_code"),
                        "reason": result.get("reason"),
                        "category": result.get("category"),
                        "fake_success": result.get("fake_success", False),
                    },
                    approval_required=bool(job.metadata.get("approval_status") == "approved" or job.metadata.get("approval")),
                    approval_status=str(job.metadata.get("approval_status") or "not_required"),
                    source_trace={"job_id": job.job_id, "agent": job.agent, "result_file": job.result_file},
                )
            except Exception:
                pass
        if _ingest_nexus_event is not None:
            try:
                _ingest_nexus_event(
                    "agent_runtime",
                    "job_finished",
                    f"{job.agent} job {job.job_id[-8:]} -> {updates['status']}",
                    job_id=job.job_id,
                    agent=job.agent,
                    status=updates["status"],
                    exit_code=updates.get("exit_code"),
                    nexus_action=(nexus_event or {}).get("action") if nexus_event else None,
                )
            except Exception:
                pass

    def _reconcile_stale_jobs(self, agent: str | None = None, limit: int = 50) -> None:
        """Fail old non-terminal jobs that cannot have an in-process worker anymore."""

        try:
            stale_after = max(30, int(os.getenv("WINTRIP_AGENT_RUNTIME_STALE_QUEUED_SECONDS", "120")))
        except ValueError:
            stale_after = 120
        try:
            stale_running_grace = max(30, int(os.getenv("WINTRIP_AGENT_RUNTIME_STALE_RUNNING_GRACE_SECONDS", "120")))
        except ValueError:
            stale_running_grace = 120
        jobs = self.store.list_jobs(agent=agent, limit=max(50, int(limit or 50)))
        now = time.time()
        for job in jobs:
            status = str(job.get("status") or "")
            if status not in {"queued", "planning", "running", "testing", "waiting_for_human"}:
                continue
            job_id = str(job.get("job_id") or "")
            if not job_id:
                continue
            if job_id in self._cancel_flags:
                continue
            if status == "queued" and not job.get("started_at"):
                created = _iso_to_timestamp(str(job.get("created_at") or ""))
                if created is None or now - created < stale_after:
                    continue
                reason = "stale_queued_after_runtime_restart"
                preview = "Job bleef queued na runtime restart en is fail-closed gemarkeerd."
            else:
                started = _iso_to_timestamp(str(job.get("started_at") or ""))
                updated = _iso_to_timestamp(str(job.get("updated_at") or ""))
                created = _iso_to_timestamp(str(job.get("created_at") or ""))
                reference = started or updated or created
                try:
                    timeout_seconds = max(1, int(job.get("timeout_seconds") or self.default_timeout_seconds))
                except (TypeError, ValueError):
                    timeout_seconds = self.default_timeout_seconds
                stale_running_after = timeout_seconds + stale_running_grace
                if reference is None or now - reference < stale_running_after:
                    continue
                reason = "stale_running_after_runtime_restart"
                preview = "Job leek nog running, maar er is geen levende backend-worker meer; fail-closed gemarkeerd."
            updated = self.store.update(
                job_id,
                {
                    "status": "failed",
                    "finished_at": utc_now_iso(),
                    "exit_code": None,
                    "result_summary": reason,
                    "response_preview": preview,
                },
            )
            if updated and job.get("events_file"):
                try:
                    EventLog(str(job["events_file"])).append(
                        "stale_after_restart",
                        {"status": "failed", "previous_status": status, "reason": reason},
                    )
                except Exception:
                    pass

    def _prompt_markdown(self, job: JobRecord) -> str:
        roots = "\n".join(f"- {root}" for root in job.allowed_roots) or "- (geen)"
        return (
            f"# Agent job {job.job_id}\n\n"
            f"- Agent: `{job.agent}`\n"
            f"- Created: {job.created_at}\n"
            f"- Workspace: `{job.workspace_root}`\n"
            f"- Timeout: {job.timeout_seconds}s\n\n"
            f"## Toegestane roots\n{roots}\n\n"
            f"## Opdracht\n\n{job.task}\n"
        )


def _iso_to_timestamp(value: str) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _safe_json(payload: dict[str, Any]) -> str:
    import json

    try:
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return json.dumps({"status": str(payload.get("status") or "unknown")}, indent=2)


def _default_workspace_root() -> Path:
    configured = os.getenv("WINTRIP_HOST_WORKSPACE") or os.getenv("WINTRIP_PROJECT_ROOT") or os.getenv("WINTRIP_WORKSPACE")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path.resolve()
    fallback = Path("/home/pwintri2/WintripAI")
    return fallback.resolve() if fallback.exists() else Path.cwd().resolve()


def _default_allowed_roots() -> list[str]:
    candidates = [
        os.getenv("WINTRIP_RUFLO_PATH") or "/home/pwintri2/ruflo",
        os.getenv("WINTRIP_ROO_CODE_PATH") or os.getenv("WINTRIP_ROO_PATH") or "/home/pwintri2/Roo-code",
        os.getenv("WINTRIP_CODEX_PATH") or "/home/pwintri2/Codex",
        os.getenv("WINTRIP_DEEPSEEK_PATH") or "/home/pwintri2/deepseek",
        os.getenv("WINTRIP_ATLAS_PATH") or "/home/pwintri2/atlas",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for raw in candidates:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


_SINGLETON_LOCK = threading.Lock()
_SINGLETON: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Process-wide orchestrator. The router and FastAPI handlers share it."""

    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            _SINGLETON = AgentOrchestrator()
        return _SINGLETON


def reset_orchestrator(orchestrator: AgentOrchestrator | None = None) -> AgentOrchestrator | None:
    """Replace or clear the singleton; intended for tests."""

    global _SINGLETON
    with _SINGLETON_LOCK:
        previous = _SINGLETON
        _SINGLETON = orchestrator
        return previous


def _notify_living_agent_event(event: dict[str, Any]) -> None:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import get_living_ouroboros_loop

        get_living_ouroboros_loop().observe_agent_event(event)
    except Exception:
        pass
