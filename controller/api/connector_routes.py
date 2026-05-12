"""FastAPI routes for cockpit connector enable/disable control."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from controller.connector_catalog import (
    get_connector,
    get_connector_agent_work_packages,
    get_connector_catalog,
    is_tool_enabled,
    set_connector_enabled,
    set_tool_enabled,
)


connector_router = APIRouter(prefix="/api/cockpit/connectors", tags=["cockpit-connectors"])


class ConnectorToggleRequest(BaseModel):
    enabled: bool = Field(default=True)
    approval: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=1000)
    updated_by: str = Field(default="cockpit", max_length=80)


def init_connector_routes(app: Any) -> None:
    app.include_router(connector_router)


@connector_router.get("")
async def list_connectors() -> dict[str, Any]:
    return get_connector_catalog()


@connector_router.get("/tools/{tool_name}")
async def connector_tool_gate(tool_name: str) -> dict[str, Any]:
    return {"status": "online", "tool": is_tool_enabled(tool_name), "fake_success": False}


@connector_router.get("/agent-work-packages")
async def connector_agent_work_packages() -> dict[str, Any]:
    packages = get_connector_agent_work_packages()
    return {"status": "online", "count": len(packages), "agent_work_packages": packages, "fake_success": False}


@connector_router.post("/tools/{tool_name}")
async def toggle_connector_tool(tool_name: str, request: ConnectorToggleRequest) -> dict[str, Any]:
    return set_tool_enabled(
        tool_name,
        enabled=bool(request.enabled),
        approval=request.approval,
        updated_by=request.updated_by,
    )


@connector_router.get("/{connector_id}")
async def connector_detail(connector_id: str) -> dict[str, Any]:
    return get_connector(connector_id)


@connector_router.post("/{connector_id}")
async def toggle_connector(connector_id: str, request: ConnectorToggleRequest) -> dict[str, Any]:
    return set_connector_enabled(
        connector_id,
        enabled=bool(request.enabled),
        approval=request.approval,
        notes=request.notes,
        updated_by=request.updated_by,
    )
