"""FastAPI routes voor de esoterische Ouroboros integratielaag."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from controller.ouroboros_esoteric_bridge import get_esoteric_status


ouroboros_esoteric_router = APIRouter(prefix="/api/ouroboros/esoteric", tags=["ouroboros-esoteric"])


def init_ouroboros_esoteric(app: Any) -> None:
    app.include_router(ouroboros_esoteric_router)


@ouroboros_esoteric_router.get("/status")
async def esoteric_status(force_refresh: bool = False) -> dict[str, Any]:
    return get_esoteric_status(force_refresh=force_refresh)


@ouroboros_esoteric_router.post("/rescan")
async def esoteric_rescan() -> dict[str, Any]:
    return get_esoteric_status(force_refresh=True)
