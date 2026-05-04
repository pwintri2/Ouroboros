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


def init_world_agent(app: Any) -> None:
    app.include_router(world_agent_router)
