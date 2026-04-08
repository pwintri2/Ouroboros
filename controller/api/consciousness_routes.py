from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from controller.consciousness.models import (
    ConsciousnessIngestEvent,
    ConsciousnessIngestResponse,
    ConsciousnessQuery,
    ConsciousnessQueryResponse,
)
from controller.consciousness.storage import ConsciousnessMemory


consciousness_router = APIRouter(tags=["consciousness"])


def init_consciousness(app: Any, memory: ConsciousnessMemory) -> None:
    app.state.consciousness_memory = memory
    app.include_router(consciousness_router)


def _get_memory(request: Request) -> ConsciousnessMemory:
    memory: Optional[ConsciousnessMemory] = getattr(request.app.state, "consciousness_memory", None)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Consciousness memory is not initialized.",
        )
    return memory


@consciousness_router.post(
    "/stream_consciousness",
    response_model=ConsciousnessIngestResponse,
    summary="Ingest a sensory event into 11D memory",
)
async def stream_consciousness(
    payload: ConsciousnessIngestEvent,
    request: Request,
) -> ConsciousnessIngestResponse:
    memory = _get_memory(request)
    return await memory.ingest_event(payload)


@consciousness_router.post(
    "/consciousness/query",
    response_model=ConsciousnessQueryResponse,
    summary="Query the 11D memory with persona-aware reranking",
)
async def query_consciousness(
    payload: ConsciousnessQuery,
    request: Request,
) -> ConsciousnessQueryResponse:
    memory = _get_memory(request)
    return memory.query_with_persona(payload)


@consciousness_router.websocket("/stream_consciousness/ws")
async def stream_consciousness_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    memory: Optional[ConsciousnessMemory] = getattr(websocket.app.state, "consciousness_memory", None)
    if memory is None:
        await websocket.send_json({"accepted": False, "error": "Consciousness memory is not initialized."})
        await websocket.close(code=1011)
        return

    try:
        while True:
            raw_payload = await websocket.receive_json()
            try:
                payload = ConsciousnessIngestEvent.model_validate(raw_payload)
                result = await memory.ingest_event(payload)
                await websocket.send_json(result.model_dump())
            except ValidationError as exc:
                await websocket.send_json({
                    "accepted": False,
                    "error": "validation_error",
                    "details": _serialize_validation_errors(exc),
                })
            except Exception as exc:
                await websocket.send_json({"accepted": False, "error": "ingest_error", "details": str(exc)})
    except WebSocketDisconnect:
        return


def _serialize_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for error in exc.errors():
        item = dict(error)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {key: str(value) for key, value in ctx.items()}
        serialized.append(item)
    return serialized
