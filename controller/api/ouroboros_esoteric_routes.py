"""FastAPI routes voor de esoterische Ouroboros integratielaag."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from controller.ouroboros_esoteric_bridge import get_esoteric_status


ouroboros_esoteric_router = APIRouter(prefix="/api/ouroboros/esoteric", tags=["ouroboros-esoteric"])


class LivingTickRequest(BaseModel):
    trigger: str = Field(default="manual", min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class QuantumFoamInitiateRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=16000)
    context: dict[str, Any] = Field(default_factory=dict)
    collapse_existing: bool = True
    max_ticks: int = Field(default=12, ge=1, le=120)


class QuantumFoamTickRequest(BaseModel):
    field_id: str | None = None
    evolve: bool = True
    trigger: str = Field(default="cockpit", min_length=1, max_length=64)


class QuantumFoamCollapseRequest(BaseModel):
    field_id: str | None = None
    reason: str = Field(default="manual", min_length=1, max_length=240)


def init_ouroboros_esoteric(app: Any) -> None:
    app.include_router(ouroboros_esoteric_router)


@ouroboros_esoteric_router.get("/status")
async def esoteric_status(force_refresh: bool = False) -> dict[str, Any]:
    return get_esoteric_status(force_refresh=force_refresh)


@ouroboros_esoteric_router.post("/rescan")
async def esoteric_rescan() -> dict[str, Any]:
    return get_esoteric_status(force_refresh=True)


@ouroboros_esoteric_router.get("/akashic/recent")
async def akashic_recent(limit: int = 50) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.akashic_network import AkashicNetwork

        events = AkashicNetwork().recent_events(limit=limit)
        return {"status": "online", "events": events, "count": len(events)}
    except Exception as exc:
        return {"status": "unavailable", "events": [], "count": 0, "reason": str(exc)}


@ouroboros_esoteric_router.get("/quantum-foam/status")
async def quantum_foam_status_route(limit: int = 5) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.quantum_foam import quantum_foam_status

        return quantum_foam_status(limit=limit)
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:500], "fake_success": False}


@ouroboros_esoteric_router.post("/quantum-foam/initiate")
async def quantum_foam_initiate(req: QuantumFoamInitiateRequest) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.quantum_foam import initiate_quantum_foam_field

        return initiate_quantum_foam_field(
            req.task,
            context=req.context,
            collapse_existing=req.collapse_existing,
            max_ticks=req.max_ticks,
        )
    except ValueError as exc:
        return {"status": "blocked", "reason": str(exc), "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc)[:500], "fake_success": False}


@ouroboros_esoteric_router.post("/quantum-foam/tick")
async def quantum_foam_tick(req: QuantumFoamTickRequest) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.quantum_foam import monitor_quantum_foam_field

        return monitor_quantum_foam_field(field_id=req.field_id, evolve=req.evolve, trigger=req.trigger)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)[:500], "fake_success": False}


@ouroboros_esoteric_router.post("/quantum-foam/collapse")
async def quantum_foam_collapse(req: QuantumFoamCollapseRequest) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.quantum_foam import collapse_quantum_foam_field

        return collapse_quantum_foam_field(field_id=req.field_id, reason=req.reason)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)[:500], "fake_success": False}


@ouroboros_esoteric_router.get("/living/status")
async def living_ouroboros_status(limit: int = 12) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import living_status

        return living_status(limit=limit)
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc), "fake_success": False}


@ouroboros_esoteric_router.post("/living/start")
async def living_ouroboros_start(interval_seconds: int = 45) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import get_living_ouroboros_loop

        return get_living_ouroboros_loop().start(interval_seconds=interval_seconds)
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


@ouroboros_esoteric_router.post("/living/stop")
async def living_ouroboros_stop() -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import get_living_ouroboros_loop

        return get_living_ouroboros_loop().stop()
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


@ouroboros_esoteric_router.post("/living/tick")
async def living_ouroboros_tick(req: LivingTickRequest) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import living_tick

        return living_tick(trigger=req.trigger, payload=req.payload)
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


@ouroboros_esoteric_router.get("/living/memory")
async def living_ouroboros_memory(limit: int = 50, kind: str | None = None) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_persistent_memory import get_persistent_memory

        memory = get_persistent_memory()
        events = memory.timeline(limit=limit, kind=kind)
        return {"status": "online", "events": events, "count": len(events), "memory": memory.status(limit=5)}
    except Exception as exc:
        return {"status": "unavailable", "events": [], "count": 0, "reason": str(exc), "fake_success": False}


@ouroboros_esoteric_router.get("/living/events")
async def living_ouroboros_events(limit: int = 50, kind: str | None = None) -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import living_events

        events = living_events(limit=limit, kind=kind)
        return {"status": "online", "events": events, "count": len(events), "fake_success": False}
    except Exception as exc:
        return {"status": "unavailable", "events": [], "count": 0, "reason": str(exc)[:500], "fake_success": False}


@ouroboros_esoteric_router.get("/living/output")
async def living_ouroboros_output() -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import living_output

        return living_output()
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:500], "fake_success": False}
