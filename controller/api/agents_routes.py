"""FastAPI routes for the AgentS subsystem."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.agent_runtime.adapters.agents_cli import (
    agents_cli_adapter,
    agents_status,
    discover_capabilities,
    launch_probe,
)


APPROVAL_PHRASE = "Akkoord"

agents_router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentsRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=16000)
    approval: str = Field(default="")
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    metadata: Optional[dict[str, Any]] = None


def init_agents_routes(app: Any) -> None:
    app.include_router(agents_router)


@agents_router.get("/status")
async def get_agents_status() -> dict[str, Any]:
    return agents_status()


@agents_router.get("/capabilities")
async def get_agents_capabilities() -> dict[str, Any]:
    return discover_capabilities()


@agents_router.get("/probe")
async def get_agents_probe(timeout_seconds: int = 4) -> dict[str, Any]:
    return launch_probe(timeout_seconds=max(1, min(int(timeout_seconds or 4), 30)))


@agents_router.post("/run")
async def post_agents_run(req: AgentsRunRequest) -> dict[str, Any]:
    if str(req.approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "reason": f"/api/agents/run requires the approval phrase '{APPROVAL_PHRASE}'.",
            "fake_success": False,
        }
    status = agents_status()
    if status.get("status") not in {"available", "running", "online"}:
        raise HTTPException(status_code=503, detail=f"AgentS not launchable: {status.get('status')}")
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if "agents" not in orchestrator.adapters:
            orchestrator.register_adapter("agents", agents_cli_adapter)
        metadata = dict(req.metadata or {})
        metadata.setdefault("source", "agents_routes")
        record = orchestrator.submit(
            agent="agents",
            task=req.task,
            timeout_seconds=req.timeout_seconds,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "running", "job": record.to_dict(), "agents_status": status, "fake_success": False}
