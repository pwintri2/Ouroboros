"""FastAPI routes for the agent runtime.

Endpoints:

    POST /api/agent-runtime/jobs          create + start a job
    GET  /api/agent-runtime/jobs          list jobs (optional ?agent= filter)
    GET  /api/agent-runtime/jobs/{job_id} job detail
    GET  /api/agent-runtime/jobs/{job_id}/events
    POST /api/agent-runtime/jobs/{job_id}/cancel
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.agent_runtime.orchestrator import AgentOrchestrator, get_orchestrator
from controller.nexus_status import nexus_recent, nexus_summary, recompute as nexus_recompute
from controller.tool_bridge import run_tool_bridge, tool_bridge_status
from ouroboros_esoteric.quantum_corruption_nexus import quantum_nexus_status


agent_runtime_router = APIRouter(prefix="/api/agent-runtime", tags=["agent-runtime"])


class CreateJobRequest(BaseModel):
    agent: str = Field(..., min_length=1, max_length=64)
    task: str = Field(..., min_length=1, max_length=16000)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    metadata: Optional[dict[str, Any]] = None


class ToolRunRequest(BaseModel):
    tool: str = Field(..., min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)


def _orchestrator() -> AgentOrchestrator:
    return get_orchestrator()


def init_agent_runtime(app: Any) -> None:
    """Mount the runtime routes onto the FastAPI app."""

    app.include_router(agent_runtime_router)


@agent_runtime_router.get("/nexus/status")
async def get_nexus_status(limit: int = 20, freshness_seconds: int = 300) -> dict[str, Any]:
    qcn = quantum_nexus_status(limit=limit)
    summary = nexus_summary(freshness_seconds=freshness_seconds)
    return {**qcn, "operational": summary}


@agent_runtime_router.get("/nexus/summary")
async def get_nexus_summary(freshness_seconds: int = 300) -> dict[str, Any]:
    return nexus_summary(freshness_seconds=freshness_seconds)


@agent_runtime_router.get("/nexus/events")
async def get_nexus_events(limit: int = 50, source: Optional[str] = None) -> dict[str, Any]:
    events = nexus_recent(limit=limit, source=source)
    return {"status": "online", "count": len(events), "events": events, "fake_success": False}


@agent_runtime_router.post("/nexus/recompute")
async def post_nexus_recompute() -> dict[str, Any]:
    return nexus_recompute()


@agent_runtime_router.get("/tools/status")
async def get_tools_status() -> dict[str, Any]:
    return tool_bridge_status()


@agent_runtime_router.post("/tools/run")
async def run_tool(req: ToolRunRequest) -> dict[str, Any]:
    return run_tool_bridge(req.tool, req.args)


@agent_runtime_router.post("/jobs")
async def create_job(req: CreateJobRequest) -> dict[str, Any]:
    try:
        record = _orchestrator().submit(
            agent=req.agent,
            task=req.task,
            timeout_seconds=req.timeout_seconds,
            metadata=req.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "running", "job": record.to_dict()}


@agent_runtime_router.get("/jobs")
async def list_jobs(agent: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
    jobs = _orchestrator().list_jobs(agent=agent, limit=limit)
    return {"status": "online", "agent": agent, "count": len(jobs), "jobs": jobs}


@agent_runtime_router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = _orchestrator().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return {"status": "online", "job": job}


@agent_runtime_router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str, after_index: int = 0, limit: int = 200) -> dict[str, Any]:
    job = _orchestrator().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    events = _orchestrator().read_events(job_id, after_index=after_index, limit=limit)
    return {"status": "online", "job_id": job_id, "after_index": after_index, "events": events}


@agent_runtime_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    job = _orchestrator().cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return {"status": "cancelled", "job": job}
