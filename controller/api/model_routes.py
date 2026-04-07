from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List

model_router = APIRouter()


class ModelSelect(BaseModel):
    model: str


@model_router.get("/api/models")
async def get_models(request: Request):
    # Return a simple supported models list; the frontend can use this
    models = [
        {"name": "gpt-4o", "provider": "openai"},
        {"name": "claude-opus-4", "provider": "anthropic"},
        {"name": "gemini-1.0", "provider": "google"},
    ]
    # attempt to include provider availability
    orch = getattr(request.app.state, 'orchestrator', None)
    active = getattr(orch, 'active_model', None) if orch else None
    return {"models": models, "active": active}


@model_router.post("/api/models/active")
async def set_active_model(request: Request, body: ModelSelect):
    orch = getattr(request.app.state, 'orchestrator', None)
    if orch:
        orch.active_model = body.model
        return {"status": "ok", "active_model": body.model}
    return {"status": "error", "message": "orchestrator not configured"}


def init_models(app):
    app.include_router(model_router)
