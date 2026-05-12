"""FastAPI routes for the canonical Ouroboros agent architecture."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from controller.ouroboros_agent_architecture import build_critic_review, get_agent_architecture_catalog, store_critic_review_audit


agent_architecture_router = APIRouter(prefix="/api/ouroboros/agents/architecture", tags=["ouroboros-agent-architecture"])


class AgentArchitectureReviewRequest(BaseModel):
    prompt: str = Field(default="", max_length=16000)
    intent: str = Field(default="", max_length=16000)
    task: str = Field(default="", max_length=16000)
    agent_id: str = Field(default="", max_length=64)
    agent: str = Field(default="", max_length=64)
    action: str = Field(default="", max_length=512)
    tool: str = Field(default="", max_length=128)
    tool_name: str = Field(default="", max_length=128)
    args: dict[str, Any] = Field(default_factory=dict)
    data_scope: str = Field(default="", max_length=1000)
    target: str = Field(default="", max_length=512)
    platform: str = Field(default="", max_length=512)
    command: str = Field(default="", max_length=4000)
    api_call: str = Field(default="", max_length=4000)
    rollback: str = Field(default="", max_length=2000)
    requested_mode: str = Field(default="preview", max_length=32)
    mode: str = Field(default="", max_length=32)
    approval: str = Field(default="", max_length=128)


def init_agent_architecture_routes(app: Any) -> None:
    app.include_router(agent_architecture_router)


@agent_architecture_router.get("")
async def get_agent_architecture() -> dict[str, Any]:
    return get_agent_architecture_catalog()


@agent_architecture_router.post("/review")
async def post_agent_architecture_review(request: AgentArchitectureReviewRequest) -> dict[str, Any]:
    data = request.model_dump() if callable(getattr(request, "model_dump", None)) else request.dict()
    if data.get("mode") and data.get("requested_mode") in {"", "preview"}:
        data["requested_mode"] = data["mode"]
    review = build_critic_review(data, store_audit=False)
    review["audit"] = {"status": "queued", "mode": "background", "fake_success": False}
    threading.Thread(target=_store_review_audit_background, args=(review,), daemon=True).start()
    return review


def _store_review_audit_background(review: dict[str, Any]) -> None:
    try:
        store_critic_review_audit(review)
    except Exception:
        pass
