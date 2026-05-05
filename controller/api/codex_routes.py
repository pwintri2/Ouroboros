"""FastAPI routes for the Codex integration layer.

Endpoints:

    GET  /api/codex/status              truthful Codex health + binary + auth
    GET  /api/codex/capabilities        layered capability inventory
    GET  /api/codex/discovery           raw repo capability discovery
    GET  /api/codex/version             codex --version output
    POST /api/codex/run                 submit an approval-gated codex job
    GET  /api/codex/jobs                list recent codex jobs
    GET  /api/codex/jobs/{job_id}       job detail
    GET  /api/codex/jobs/{job_id}/events streamed events for a job
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.codex_registry import get_codex_capability_inventory
from controller.codex_status import (
    codex_auth_summary,
    codex_overall_status,
    codex_repo_evidence,
    codex_runtime_jobs,
    codex_version,
    discover_codex_capabilities,
)


APPROVAL_PHRASE = "Akkoord"

codex_router = APIRouter(prefix="/api/codex", tags=["codex"])


class CodexRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=16000)
    approval: str = Field(default="")
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=7200)
    metadata: Optional[dict[str, Any]] = None


def init_codex_routes(app: Any) -> None:
    """Mount the Codex routes onto a FastAPI app."""

    app.include_router(codex_router)


@codex_router.get("/status")
async def get_codex_status() -> dict[str, Any]:
    return codex_overall_status()


@codex_router.get("/capabilities")
async def get_codex_capabilities() -> dict[str, Any]:
    return get_codex_capability_inventory()


@codex_router.get("/discovery")
async def get_codex_discovery() -> dict[str, Any]:
    return {
        "repo": discover_codex_capabilities(),
        "evidence": codex_repo_evidence(),
        "auth": codex_auth_summary(),
    }


@codex_router.get("/version")
async def get_codex_version() -> dict[str, Any]:
    return codex_version()


@codex_router.get("/jobs")
async def list_codex_jobs(limit: int = 20) -> dict[str, Any]:
    return codex_runtime_jobs(limit=limit)


@codex_router.get("/jobs/{job_id}")
async def get_codex_job(job_id: str) -> dict[str, Any]:
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        job = get_orchestrator().get_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"agent runtime unavailable: {exc}") from exc
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    if str(job.get("agent")).lower() != "codex":
        raise HTTPException(status_code=404, detail=f"job {job_id} is not a codex job")
    return {"status": "online", "job": job}


@codex_router.get("/jobs/{job_id}/events")
async def get_codex_job_events(job_id: str, after_index: int = 0, limit: int = 200) -> dict[str, Any]:
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        job = orchestrator.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
        if str(job.get("agent")).lower() != "codex":
            raise HTTPException(status_code=404, detail=f"job {job_id} is not a codex job")
        events = orchestrator.read_events(job_id, after_index=after_index, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"agent runtime unavailable: {exc}") from exc
    return {"status": "online", "job_id": job_id, "after_index": after_index, "events": events}


@codex_router.post("/run")
async def run_codex_task(req: CodexRunRequest) -> dict[str, Any]:
    if str(req.approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "reason": f"/codex run requires the approval phrase '{APPROVAL_PHRASE}'.",
            "fake_success": False,
        }
    overall = codex_overall_status()
    if overall.get("binary", {}).get("status") != "found":
        raise HTTPException(status_code=503, detail="codex binary not found")
    try:
        import os as _os

        from controller.agent_runtime.orchestrator import get_orchestrator

        metadata = dict(req.metadata or {})
        metadata.setdefault("source", "codex_routes")
        metadata.setdefault("prompt", req.task)
        env_default = int(_os.getenv("WINTRIP_CODEX_TIMEOUT_SECONDS", "1800") or 1800)
        effective_timeout = max(int(req.timeout_seconds or 0), env_default)
        record = get_orchestrator().submit(
            agent="codex",
            task=req.task,
            timeout_seconds=effective_timeout,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "status": "running",
        "job": record.to_dict(),
        "binary": overall.get("binary"),
        "version": overall.get("version"),
        "auth": overall.get("auth"),
        "fake_success": False,
    }
