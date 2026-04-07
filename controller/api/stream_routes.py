# controller/api/stream_routes.py
# Phase 7.X — Stream of Consciousness: FastAPI Endpoints
# Wintrip AI | task_id: wintrip-soc-005
#
# Endpoints:
#   GET  /stream/status   — daemon-status en statistieken
#   GET  /stream/queue    — items in de propose-queue (wachten op Philip's goedkeuring)
#   POST /stream/approve  — Philip keurt een queued item goed (proposal artifact, geen gevaarlijke actie)
#
# Integratie in main.py (toe te voegen door Philip na commit):
#   from controller.api.stream_routes import stream_router, init_stream
#   init_stream(app, daemon=stream_daemon, storage=stream_storage)
#
# Veiligheidsmodel:
#   - /stream/approve schrijft NOOIT naar het host-systeem of voert code uit.
#     Het zet alleen metadata-velden in ChromaDB (in_queue=False, type=approved).
#   - Alle input wordt gevalideerd via Pydantic (UUID-formaat check op item_id).
#   - Rate-limit aanbeveling: voeg in productie SlowAPI toe op /stream/approve.

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from controller.stream.daemon import StreamDaemon
from controller.stream.storage import StreamStorage


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
stream_router = APIRouter(prefix="/stream", tags=["stream"])


# ---------------------------------------------------------------------------
# Pydantic modellen
# ---------------------------------------------------------------------------
class StreamStatusResponse(BaseModel):
    """Antwoord van GET /stream/status."""
    state: str
    persona: str
    poll_interval: int
    sources_count: int
    max_items_per_source: int
    stats: Dict[str, Any]


class QueueItem(BaseModel):
    """Eén item in de propose-queue."""
    id: str
    title: str
    text: str = ""
    resonance_score: float
    importance: float
    source_type: str
    source: str
    published_at: str = ""
    tags: str = ""
    in_queue: bool
    ingested_at: str = ""


class StreamQueueResponse(BaseModel):
    """Antwoord van GET /stream/queue."""
    count: int
    items: List[Dict[str, Any]]


class ApproveRequest(BaseModel):
    """Request body voor POST /stream/approve."""
    item_id: str = Field(
        ...,
        description="UUID van het goed te keuren stream-item",
        min_length=1,
        max_length=128,
    )

    @field_validator("item_id")
    @classmethod
    def item_id_is_veilig(cls, v: str) -> str:
        """
        Valideer dat item_id alleen UUID-veilige tekens bevat.
        Voorkomt path traversal of injection via het ID-veld.
        """
        # UUID5-formaat: 8-4-4-4-12 hexadecimale tekens met koppeltekens
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE,
        )
        if not uuid_pattern.match(v.strip()):
            raise ValueError(
                f"item_id moet een geldig UUID-formaat hebben. Ontvangen: {v!r}"
            )
        return v.strip().lower()


class ApproveResponse(BaseModel):
    """Antwoord van POST /stream/approve."""
    approved: bool
    item_id: str
    message: str


# ---------------------------------------------------------------------------
# Dependency helpers — halen daemon/storage op uit app.state
# ---------------------------------------------------------------------------
def _get_daemon(request: Request) -> StreamDaemon:
    daemon: Optional[StreamDaemon] = getattr(request.app.state, "stream_daemon", None)
    if daemon is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stream daemon is niet geïnitialiseerd. Roep init_stream() aan in main.py.",
        )
    return daemon


def _get_storage(request: Request) -> StreamStorage:
    storage: Optional[StreamStorage] = getattr(request.app.state, "stream_storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stream storage is niet geïnitialiseerd. Roep init_stream() aan in main.py.",
        )
    return storage


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@stream_router.get(
    "/status",
    response_model=StreamStatusResponse,
    summary="Daemon status en statistieken",
    description=(
        "Retourneert de huidige staat van de Stream of Consciousness daemon: "
        "running/stopped, statistieken over verwerkte items, poll-interval, etc."
    ),
)
async def get_stream_status(request: Request) -> StreamStatusResponse:
    """
    GET /stream/status

    Gebruikt door de Regiekamer Zone 4 (System Telemetry) om de stream-indicator
    groen/geel/rood te kleuren.
    """
    daemon = _get_daemon(request)
    s = daemon.status()
    return StreamStatusResponse(
        state=s["state"],
        persona=s["persona"],
        poll_interval=s["poll_interval"],
        sources_count=s["sources_count"],
        max_items_per_source=s["max_items_per_source"],
        stats=s["stats"],
    )


@stream_router.get(
    "/queue",
    response_model=StreamQueueResponse,
    summary="Items in de propose-queue",
    description=(
        "Retourneert stream-items die boven de propose-drempel scoorden "
        "en wachten op Philip's goedkeuring in de Regiekamer Stream Inbox."
    ),
)
async def get_stream_queue(
    request: Request,
    limit: int = 50,
) -> StreamQueueResponse:
    """
    GET /stream/queue?limit=50

    Gesorteerd op resonance_score hoog→laag.
    Maximaal 100 items per aanroep (server-side hard limit).
    """
    # Hard limit: voorkomt dat een grote queue de UI vergrendelt
    limit = max(1, min(limit, 100))
    storage = _get_storage(request)
    items = storage.get_queue(limit=limit)
    return StreamQueueResponse(count=len(items), items=items)


@stream_router.post(
    "/approve",
    response_model=ApproveResponse,
    summary="Keur een queued item goed",
    description=(
        "Philip keurt een stream-item goed vanuit de Regiekamer Stream Inbox. "
        "Dit zet in_queue=False en type='stream_item_approved' in ChromaDB. "
        "Geen gevaarlijke acties: enkel metadata-update, geen code-uitvoering, "
        "geen schrijf-acties naar het host-systeem."
    ),
    status_code=status.HTTP_200_OK,
)
async def approve_stream_item(
    body: ApproveRequest,
    request: Request,
) -> ApproveResponse:
    """
    POST /stream/approve
    Body: {"item_id": "<uuid>"}

    Veiligheidsgarantie: approve doet NOOIT iets gevaarlijks.
    Het is puur een metadata-update in ChromaDB.
    """
    storage = _get_storage(request)
    success = storage.mark_approved(body.item_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stream-item '{body.item_id}' niet gevonden of al goedgekeurd.",
        )

    return ApproveResponse(
        approved=True,
        item_id=body.item_id,
        message="Item goedgekeurd en verplaatst naar stream_item_approved.",
    )


# ---------------------------------------------------------------------------
# Initialisatie-helper voor main.py
# ---------------------------------------------------------------------------
def init_stream(
    app: Any,
    daemon: StreamDaemon,
    storage: StreamStorage,
) -> None:
    """
    Registreert de stream router en injecteert daemon + storage in app.state.

    Aanroepen in main.py na `app = FastAPI()`:

        from controller.api.stream_routes import stream_router, init_stream
        init_stream(app, daemon=stream_daemon, storage=stream_storage)

    Args:
        app     : de FastAPI applicatie-instantie.
        daemon  : geïnitialiseerde StreamDaemon.
        storage : geïnitialiseerde StreamStorage.
    """
    app.state.stream_daemon = daemon
    app.state.stream_storage = storage
    app.include_router(stream_router)
    print("[StreamRoutes] Geregistreerd: GET /stream/status, GET /stream/queue, POST /stream/approve")
