# controller/api/training_routes.py
# Standalone UI endpoints for visible Ouroboros training.

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from controller.stream.browser_scrubber import (
    TEACHABLE_MACHINE_HOST,
    prepare_browser_ingest,
    prepare_teachablemachine_ingest,
)
from controller.stream.dreamcycle import DreamCycle
from controller.stream.geometry_11d import measure_geometry_11d
from controller.stream.metadata_11d import REQUIRED_11D_LAYERS, build_11d_metadata, missing_11d_layers
from controller.stream.normalize import normalize
from controller.stream.resonance import score as stream_resonance_score
from controller.stream.storage import StreamStorage, _resonance_to_importance


training_router = APIRouter(prefix="/training", tags=["training"])


class BrowserTrainingRequest(BaseModel):
    url: str = Field(default=f"https://{TEACHABLE_MACHINE_HOST}/train", max_length=2048)
    browser_text: str = Field(..., min_length=1, max_length=65536)
    title: Optional[str] = Field(default="Teachable Machine browser snapshot", max_length=256)
    approval: Optional[str] = Field(default=None, max_length=64)
    persona: Optional[str] = Field(default="philip", max_length=64)
    target_hz: Optional[float] = Field(default=None, ge=418.0, le=432.0)


def init_training(app: Any, storage: StreamStorage) -> None:
    app.state.training_storage = storage
    app.state.training_events = []
    app.include_router(training_router)


@training_router.get("/status")
async def training_status(request: Request) -> dict[str, Any]:
    return _status_payload(request)


@training_router.post("/browser/preview")
async def preview_browser_training(request_body: BrowserTrainingRequest, request: Request) -> dict[str, Any]:
    try:
        payload = _preview_payload(request_body, approval=None, request=request)
        _remember_event(request, "preview", payload)
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@training_router.post("/browser/approve")
async def approve_browser_training(request_body: BrowserTrainingRequest, request: Request) -> dict[str, Any]:
    try:
        payload = _preview_payload(request_body, approval=request_body.approval, request=request)
        if payload["approval_status"] != "approved":
            payload.update(
                {
                    "stored": False,
                    "approval_required": True,
                    "reason": "Wacht op Philip approval phrase: Akkoord",
                }
            )
            _remember_event(request, "approval_required", payload)
            return payload

        stored = _store_training_snapshot(payload)
        payload.update(
            {
                "stored": stored["stored"],
                "approval_required": False,
                "item_id": stored["item_id"],
                "reason": stored["reason"],
                "storage_target": stored["storage_target"],
                "collection_count": _safe_total_count(_get_storage(request)),
            }
        )
        _remember_event(request, "stored" if stored["stored"] else "not_stored", payload)
        if stored["stored"]:
            try:
                from controller.trainer_continuous import notify_browser_training_record

                notify_browser_training_record(item_id=stored.get("item_id"), source_url=payload.get("source_url"))
            except Exception:
                pass
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _preview_payload(
    body: BrowserTrainingRequest,
    approval: Optional[str],
    request: Request,
) -> dict[str, Any]:
    title = body.title or "Browser training snapshot"
    if TEACHABLE_MACHINE_HOST in body.url:
        scrubbed = prepare_teachablemachine_ingest(
            url=body.url,
            browser_text=body.browser_text,
            approval=approval,
            title=title,
        )
    else:
        scrubbed = prepare_browser_ingest(
            url=body.url,
            browser_text=body.browser_text,
            approval=approval,
            title=title,
        )

    raw_item = scrubbed.to_raw_item(title=title)
    item = normalize(raw_item)
    resonance = stream_resonance_score(item, persona=body.persona or "philip")
    importance = _resonance_to_importance(resonance.score)
    dream = DreamCycle.from_env().sample(f"{item.published_at}|{item.content_hash}|{item.source_hash}")
    dream_hz = float(body.target_hz) if body.target_hz is not None else float(dream.hz)
    frequency_source = "manual_ui" if body.target_hz is not None else "dreamcycle"
    metadata_11d = build_11d_metadata(
        item=item,
        resonance_score=resonance.score,
        importance=importance,
        ingested_at=scrubbed.scrubbed_at,
        dream_hz=dream_hz,
        relative_temporal_position=dream.relative_temporal_position,
    )
    geometry_11d = measure_geometry_11d(dream_hz)

    return {
        "status": "preview",
        "source_url": scrubbed.source_url,
        "source_host": scrubbed.source_host,
        "taint": scrubbed.taint,
        "approval_status": scrubbed.approval_status,
        "requires_approval": scrubbed.requires_approval,
        "approval_phrase": scrubbed.approval_phrase,
        "blocked_patterns": list(scrubbed.blocked_patterns),
        "allowed_actions": list(scrubbed.allowed_actions),
        "blocked_actions": list(scrubbed.blocked_actions),
        "diff_hash": scrubbed.diff_hash,
        "diff_view": scrubbed.diff_view,
        "scrubbed_text": scrubbed.scrubbed_text,
        "raw_item": raw_item,
        "resonance": {
            "score": resonance.score,
            "should_store": resonance.should_store,
            "should_propose": resonance.should_propose,
            "reasons": resonance.reasons,
            "matched_domains": resonance.matched_domains,
        },
        "dreamcycle": {
            **dream.metadata(),
            "dream_hz": round(dream_hz, 6),
            "frequency_source": frequency_source,
            "samples": _frequency_samples(item.content_hash, target_hz=dream_hz),
        },
        "metadata_11d": metadata_11d,
        "geometry_11d": geometry_11d,
        "missing_11d_layers": missing_11d_layers(metadata_11d),
        "collection_count": _safe_total_count(_get_storage(request)),
        "pipeline": [
            {"step": "observe", "label": "Browser snapshot", "value": f"{len(body.browser_text)} chars"},
            {
                "step": "orient",
                "label": "Scrubber",
                "value": "clean" if not scrubbed.blocked_patterns else ",".join(scrubbed.blocked_patterns),
            },
            {"step": "decide", "label": "Resonance", "value": f"{resonance.score:.3f}"},
            {"step": "act", "label": "Approval gate", "value": scrubbed.approval_status},
            {"step": "reflect", "label": "DreamCycle", "value": f"{dream_hz:.3f} Hz"},
        ],
    }


def _status_payload(request: Request) -> dict[str, Any]:
    storage = _get_storage(request)
    sample = DreamCycle.from_env().sample("standalone-ui")
    return {
        "status": "online",
        "collection_count": _safe_total_count(storage),
        "training_collection_count": _safe_training_collection_count(),
        "dreamcycle": {
            **sample.metadata(),
            "samples": _frequency_samples("standalone-ui"),
        },
        "layers": [
            {"key": layer.key, "group": layer.group, "label": layer.label}
            for layer in REQUIRED_11D_LAYERS
        ],
        "recent_events": list(getattr(request.app.state, "training_events", []))[-8:],
    }


def _frequency_samples(seed: str, target_hz: Optional[float] = None) -> list[dict[str, float]]:
    cycle = DreamCycle.from_env()
    samples = []
    for index in range(12):
        sample = cycle.sample(seed, stable_seconds=index * (cycle.cycle_seconds / 12.0))
        hz = float(sample.hz)
        if target_hz is not None:
            pulse = 0.25 + (0.5 if index in {3, 7, 11} else 0.0)
            hz = max(418.0, min(432.0, hz * (1.0 - pulse) + float(target_hz) * pulse))
        samples.append({"index": index, "hz": round(hz, 3), "phase": round(sample.phase, 4)})
    return samples


def _remember_event(request: Request, kind: str, payload: dict[str, Any]) -> None:
    events = getattr(request.app.state, "training_events", [])
    events.append(
        {
            "kind": kind,
            "source_host": payload.get("source_host"),
            "approval_status": payload.get("approval_status"),
            "stored": payload.get("stored", False),
            "dream_hz": payload.get("dreamcycle", {}).get("dream_hz"),
            "resonance_score": payload.get("resonance", {}).get("score"),
            "collection_count": payload.get("collection_count"),
        }
    )
    request.app.state.training_events = events[-20:]


def _get_storage(request: Request) -> StreamStorage:
    storage = getattr(request.app.state, "training_storage", None)
    if storage is None:
        raise RuntimeError("Training storage is niet geinitialiseerd.")
    return storage


def _safe_collection_count(storage: StreamStorage) -> int:
    try:
        return int(storage._collection.count())
    except Exception:
        return 0


def _safe_total_count(storage: StreamStorage) -> int:
    return _safe_collection_count(storage) + _safe_training_collection_count()


def _safe_training_collection_count() -> int:
    try:
        return int(_training_collection().count())
    except Exception:
        return 0


def _store_training_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    collection = _training_collection()
    raw_item = payload["raw_item"]
    item_id = raw_item.get("id") or str(uuid.uuid5(uuid.NAMESPACE_URL, payload["diff_hash"]))
    metadata = {
        **payload["metadata_11d"],
        "type": "training_snapshot_approved",
        "source": payload["source_url"],
        "source_type": "url",
        "source_host": payload["source_host"],
        "taint": payload["taint"],
        "approval_status": payload["approval_status"],
        "diff_hash": payload["diff_hash"],
        "resonance_score": float(payload["resonance"]["score"]),
        "dream_hz": float(payload["dreamcycle"]["dream_hz"]),
        "frequency_band": payload["dreamcycle"]["frequency_band"],
        "content_hash": hashlib.sha256(payload["scrubbed_text"].encode("utf-8")).hexdigest(),
    }
    geometry = payload.get("geometry_11d") or measure_geometry_11d(metadata["dream_hz"])
    metadata.update(
        {
            "geometry_11d_available": True,
            "geometry_11d_radius": float(geometry["radius"]),
            "geometry_11d_volume": float(geometry["volume"]),
            "geometry_11d_oppervlakte": float(geometry["oppervlakte"]),
            "geometry_11d_source": "controller.stream.geometry_11d.measure_geometry_11d",
        }
    )
    collection.add(
        ids=[item_id],
        documents=[payload["scrubbed_text"]],
        metadatas=[metadata],
        embeddings=[_embedding_11d(payload)],
    )
    return {
        "stored": True,
        "item_id": item_id,
        "reason": "Opgeslagen in lokale 11D ChromaDB trainingscollectie.",
        "storage_target": "wintrip_training_11d",
    }


def _training_collection():
    try:
        from controller.chroma_runtime import get_or_create_collection
    except Exception as exc:
        raise RuntimeError(f"chroma runtime is niet beschikbaar: {exc}") from exc
    collection_name = os.getenv("WINTRIP_TRAINING_COLLECTION", "wintrip_training_11d")
    return get_or_create_collection(name=collection_name, persist_dir=os.getenv("WINTRIP_DB_PATH", "wintrip_brain"))


def _embedding_11d(payload: dict[str, Any]) -> list[float]:
    seed = "|".join(
        [
            str(payload.get("diff_hash", "")),
            str(payload.get("dreamcycle", {}).get("relative_temporal_position", "")),
            str(payload.get("resonance", {}).get("score", "")),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).digest()
    values = []
    for index in range(11):
        chunk = digest[(index * 2) % len(digest):((index * 2) % len(digest)) + 2]
        if len(chunk) < 2:
            chunk += digest[: 2 - len(chunk)]
        raw = int.from_bytes(chunk, "big")
        values.append(round((raw / 65535.0) * 2.0 - 1.0, 6))
    return values
