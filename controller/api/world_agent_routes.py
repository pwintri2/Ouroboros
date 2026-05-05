"""FastAPI routes for the Ouroboros World Agent."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from controller.world_agent import (
    ask_grok_via_world_agent,
    recent_world_actions,
    search_world_memory,
    world_agent_status,
)


world_agent_router = APIRouter(prefix="/api/world-agent", tags=["world-agent"])


class GrokAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    approval: Optional[str] = Field(default=None, max_length=64)
    open_tab: bool = True
    submit: bool = True


class WorldMemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)


@world_agent_router.get("/status")
async def get_world_agent_status() -> dict[str, Any]:
    return await asyncio.to_thread(world_agent_status)


@world_agent_router.get("/actions/recent")
async def get_world_agent_recent_actions(limit: int = 20) -> dict[str, Any]:
    return await asyncio.to_thread(recent_world_actions, max(1, min(int(limit or 20), 100)))


@world_agent_router.post("/grok/ask")
async def post_world_agent_grok_ask(body: GrokAskRequest) -> dict[str, Any]:
    return await asyncio.to_thread(
        ask_grok_via_world_agent,
        body.question,
        approval=body.approval,
        open_tab=body.open_tab,
        submit=body.submit,
    )


@world_agent_router.post("/memory/search")
async def post_world_agent_memory_search(body: WorldMemorySearchRequest) -> dict[str, Any]:
    return await asyncio.to_thread(search_world_memory, body.query, limit=body.limit)


@world_agent_router.get("/dependencies")
async def get_world_agent_dependencies() -> dict[str, Any]:
    return await asyncio.to_thread(_world_dependencies)


@world_agent_router.get("/health")
async def get_world_agent_health() -> dict[str, Any]:
    return await asyncio.to_thread(_world_health)


def _world_dependencies() -> dict[str, Any]:
    base = world_agent_status() or {}
    deps = base.get("dependencies") if isinstance(base.get("dependencies"), dict) else {}
    memory = base.get("memory") if isinstance(base.get("memory"), dict) else {}
    return {
        "status": "online" if any(deps.values()) or memory.get("available") else "degraded",
        "memory_available": bool(memory.get("available")),
        "memory_count": memory.get("count"),
        "chromadb": bool(deps.get("chromadb")),
        "playwright": bool(deps.get("playwright")),
        "playwright_host": bool(deps.get("playwright_host")),
        "host_bridge": bool(base.get("host_bridge")),
        "via_bridge": bool(base.get("via_bridge")),
        "fake_success": False,
    }


def _world_health() -> dict[str, Any]:
    base = world_agent_status() or {}
    deps = base.get("dependencies") if isinstance(base.get("dependencies"), dict) else {}
    memory = base.get("memory") if isinstance(base.get("memory"), dict) else {}
    actions_payload = recent_world_actions(limit=5) or {}
    actions = actions_payload.get("actions") if isinstance(actions_payload, dict) else []
    last_status = ""
    if isinstance(actions, list) and actions:
        last_status = str(actions[0].get("status") or "")
    failures = [
        item for item in (actions or [])
        if isinstance(item, dict) and str(item.get("status") or "").lower() in {"error", "failed", "blocked"}
    ]
    bridge_available = bool(base.get("host_bridge")) or bool(base.get("via_bridge"))
    browser_available = bool(deps.get("playwright")) or bool(deps.get("playwright_host"))
    if base.get("status") == "online" and (memory.get("available") or browser_available or bridge_available):
        status = "online"
        reason = "Core memory/bridge/browser infrastructure reachable."
    elif base.get("status") == "online":
        status = "degraded"
        reason = "World agent reachable but memory/browser/bridge unavailable."
    else:
        status = base.get("status") or "unavailable"
        reason = base.get("reason") or "World agent status function did not report online."
    return {
        "status": status,
        "memory": {"available": bool(memory.get("available")), "count": memory.get("count")},
        "bridge": {"available": bridge_available, "host_bridge": bool(base.get("host_bridge"))},
        "browser_automation": {
            "available": browser_available,
            "reason": None if browser_available else "Playwright host adapter unreachable",
        },
        "recent_actions_count": len(actions) if isinstance(actions, list) else 0,
        "recent_failures": len(failures),
        "last_action_status": last_status or None,
        "reason": reason,
        "fake_success": False,
    }


def init_world_agent(app: Any) -> None:
    app.include_router(world_agent_router)
