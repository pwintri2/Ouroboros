"""FastAPI routes for DeepSeek and Atlas agent integrations."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.agent_runtime.adapters.ecosystem_cli import (
    atlas_doctor,
    atlas_status,
    deepseek_doctor,
    deepseek_status,
    discover_atlas_capabilities,
    discover_deepseek_capabilities,
)
from controller.slash_agent_router import APPROVAL_PHRASE, execute_host_agent_command


deepseek_router = APIRouter(prefix="/api/deepseek", tags=["deepseek"])
atlas_router = APIRouter(prefix="/api/atlas", tags=["atlas"])


class EcosystemRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=16000)
    approval: str = Field(default="")
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=7200)


def init_ecosystem_agent_routes(app: Any) -> None:
    app.include_router(deepseek_router)
    app.include_router(atlas_router)


@deepseek_router.get("/status")
async def get_deepseek_status() -> dict[str, Any]:
    return deepseek_status()


@deepseek_router.get("/capabilities")
async def get_deepseek_capabilities() -> dict[str, Any]:
    return discover_deepseek_capabilities()


@deepseek_router.get("/doctor")
async def get_deepseek_doctor() -> dict[str, Any]:
    return deepseek_doctor()


@deepseek_router.get("/jobs")
async def list_deepseek_jobs(limit: int = 20) -> dict[str, Any]:
    return _list_jobs("deepseek", limit=limit)


@deepseek_router.post("/run")
async def run_deepseek(req: EcosystemRunRequest) -> dict[str, Any]:
    return _run_agent("deepseek", req)


@atlas_router.get("/status")
async def get_atlas_status() -> dict[str, Any]:
    return atlas_status()


@atlas_router.get("/capabilities")
async def get_atlas_capabilities() -> dict[str, Any]:
    return discover_atlas_capabilities()


@atlas_router.get("/doctor")
async def get_atlas_doctor() -> dict[str, Any]:
    return atlas_doctor()


@atlas_router.get("/jobs")
async def list_atlas_jobs(limit: int = 20) -> dict[str, Any]:
    return _list_jobs("atlas", limit=limit)


@atlas_router.post("/run")
async def run_atlas(req: EcosystemRunRequest) -> dict[str, Any]:
    return _run_agent("atlas", req)


def _run_agent(agent: str, req: EcosystemRunRequest) -> dict[str, Any]:
    if str(req.approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "reason": f"/{agent} run requires the approval phrase '{APPROVAL_PHRASE}'.",
            "fake_success": False,
        }
    return execute_host_agent_command(
        agent=agent,
        task=req.task,
        approval=req.approval,
        timeout_seconds=int(req.timeout_seconds or 1800),
        prefer_bridge=True,
    )


def _list_jobs(agent: str, *, limit: int) -> dict[str, Any]:
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        jobs = get_orchestrator().list_jobs(agent=agent, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"agent runtime unavailable: {exc}") from exc
    return {"status": "online", "agent": agent, "count": len(jobs), "jobs": jobs, "fake_success": False}
