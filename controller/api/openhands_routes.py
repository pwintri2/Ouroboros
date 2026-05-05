"""FastAPI routes for the OpenHands subsystem."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.agent_runtime.adapters.openhands_adapter import (
    discover_capabilities,
    import_probe,
    openhands_adapter,
    openhands_status,
    server_probe,
)


APPROVAL_PHRASE = "Akkoord"

openhands_router = APIRouter(prefix="/api/openhands", tags=["openhands"])


class OpenHandsRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=16000)
    approval: str = Field(default="")
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    metadata: Optional[dict[str, Any]] = None


def init_openhands_routes(app: Any) -> None:
    app.include_router(openhands_router)


@openhands_router.get("/status")
async def get_openhands_status() -> dict[str, Any]:
    return openhands_status()


@openhands_router.get("/capabilities")
async def get_openhands_capabilities() -> dict[str, Any]:
    return discover_capabilities()


@openhands_router.get("/probes")
async def get_openhands_probes() -> dict[str, Any]:
    return {"import": import_probe(), "server": server_probe(), "fake_success": False}


@openhands_router.post("/run")
async def post_openhands_run(req: OpenHandsRunRequest) -> dict[str, Any]:
    if str(req.approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "reason": f"/api/openhands/run requires the approval phrase '{APPROVAL_PHRASE}'.",
            "fake_success": False,
        }
    status = openhands_status()
    if status.get("status") in {"missing"}:
        raise HTTPException(status_code=503, detail="OpenHands repo not present")
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if "openhands" not in orchestrator.adapters:
            orchestrator.register_adapter("openhands", openhands_adapter)
        metadata = dict(req.metadata or {})
        metadata.setdefault("source", "openhands_routes")
        record = orchestrator.submit(
            agent="openhands",
            task=req.task,
            timeout_seconds=req.timeout_seconds,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "running", "job": record.to_dict(), "openhands_status": status, "fake_success": False}
