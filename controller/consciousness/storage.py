from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

from controller.consciousness.models import (
    ALLOWED_LANGUAGES,
    ALLOWED_SOURCES,
    ALLOWED_SYSTEMS,
    ConsciousnessChunk,
    ConsciousnessIngestEvent,
    ConsciousnessIngestResponse,
    ConsciousnessQuery,
    ConsciousnessQueryResponse,
    ConsciousnessQueryResult,
)

load_dotenv()

DEFAULT_11D_COLLECTION = "wintrip_11d_v1"
DEFAULT_11D_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "wintrip_brain"))

_DEVELOPER_TECH_LANGUAGES = {
    "python", "swift", "javascript", "typescript", "html", "css", "json", "yaml", "sql", "bash",
}

_DEVELOPER_TECH_SOURCES = {"file_watch", "telemetry", "api"}
_TALLE_FIELD_CLUSTERS = {"unclassified", "novel", "field", "resonance", "john_may"}


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _safe_text(value: Optional[str], fallback: str = "") -> str:
    if value is None:
        return fallback
    cleaned = "".join(ch for ch in str(value) if ord(ch) >= 32 or ch in ("\n", "\t"))
    return cleaned.strip()


def _normalize_choice(value: Optional[str], allowed: set[str], fallback: str) -> str:
    candidate = (value or fallback).strip().lower()
    return candidate if candidate in allowed else fallback


def _normalize_persona(value: Optional[str]) -> str:
    candidate = (value or "developer").strip().lower().replace(" ", "_")
    return "talle_wintrip" if candidate in {"talle", "talle_wintrip", "talle-wintrip"} else candidate


def _clamp_weight(value: Optional[float], fallback: float = 0.5) -> float:
    if value is None:
        return fallback
    return max(0.0, min(1.0, float(value)))


def _join_tags(tags: list[str]) -> str:
    return ",".join(tags) if tags else ""


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = _safe_text(text)
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            step = max(1, chunk_size - overlap)
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start:start + chunk_size].strip())
                start += step
            continue

        proposed = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(proposed) <= chunk_size:
            current = proposed
            continue

        if current:
            chunks.append(current.strip())
        current = paragraph

    if current:
        chunks.append(current.strip())

    return [chunk for chunk in chunks if chunk]


class ConsciousnessMemory:
    """11D ingestion and retrieval service backed by a dedicated ChromaDB collection."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
        collection: Any = None,
    ):
        self.persist_dir = persist_dir or os.getenv("WINTRIP_11D_DB_PATH", DEFAULT_11D_DIR)
        self.collection_name = collection_name or os.getenv("WINTRIP_11D_COLLECTION", DEFAULT_11D_COLLECTION)
        self.default_project_context = os.getenv("WINTRIP_DEFAULT_PROJECT_CONTEXT", "phase_7_web_migration")

        if collection is not None:
            self.collection = collection
            self.embedding_function = None
            self.client = None
            return

        os.makedirs(self.persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_dir)

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=f"{ollama_url}/api/embeddings",
            model_name=embed_model,
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )

    async def ingest_event(self, event: ConsciousnessIngestEvent) -> ConsciousnessIngestResponse:
        event = event.model_copy(update={
            "project_context": event.project_context or self.default_project_context,
        })
        document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{event.title}:{event.source_uri or ''}:{event.timestamp}"))
        chunks = self._build_chunks(event)

        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        duplicate_chunk_ids: list[str] = []

        ingested_at = _utc_now()
        for chunk_index, chunk in enumerate(chunks):
            metadata = self._build_metadata(event, chunk, document_id, chunk_index, len(chunks), ingested_at)
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, metadata["content_hash"]))
            if self._is_duplicate(metadata["content_hash"]):
                duplicate_chunk_ids.append(chunk_id)
                continue
            documents.append(chunk.text)
            metadatas.append(metadata)
            ids.append(chunk_id)

        if ids:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)

        return ConsciousnessIngestResponse(
            accepted=bool(ids or duplicate_chunk_ids),
            document_id=document_id,
            collection=self.collection_name,
            chunk_count=len(chunks),
            stored_chunk_ids=ids,
            duplicate_chunk_ids=duplicate_chunk_ids,
            ingested_at=ingested_at,
            metadata_summary={
                "system": event.system,
                "source": event.source,
                "language": event.language,
                "persona": event.persona,
                "intent": event.intent,
                "project_context": event.project_context,
                "field_cluster": event.field_cluster,
            },
        )

    def query_with_persona(self, payload: ConsciousnessQuery) -> ConsciousnessQueryResponse:
        query_filters = self._build_query_where(payload)
        fetch_k = max(payload.n_results * 4, 12)
        raw = self.collection.query(
            query_texts=[payload.query],
            n_results=fetch_k,
            where=query_filters if query_filters else None,
        )

        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        ids = raw.get("ids", [[]])[0]
        distances = raw.get("distances", [[]])[0] if raw.get("distances") else [1.0] * len(documents)

        results: list[ConsciousnessQueryResult] = []
        for item_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            metadata = metadata or {}
            if not self._passes_time_filter(metadata, payload):
                continue

            semantic_score = max(0.0, 2.0 - float(distance))
            rerank, breakdown = self._rerank(payload.persona, metadata)
            final_score = semantic_score + rerank
            results.append(
                ConsciousnessQueryResult(
                    id=item_id,
                    document=document,
                    metadata=metadata,
                    distance=float(distance),
                    semantic_score=semantic_score,
                    rerank_score=rerank,
                    final_score=final_score,
                    score_breakdown=breakdown,
                )
            )

        results.sort(key=lambda item: item.final_score, reverse=True)
        top_results = results[: payload.n_results]
        return ConsciousnessQueryResponse(
            persona=payload.persona,
            collection=self.collection_name,
            result_count=len(top_results),
            results=top_results,
        )

    def _build_chunks(self, event: ConsciousnessIngestEvent) -> list[ConsciousnessChunk]:
        if event.chunks:
            return [self._hydrate_chunk(event, chunk) for chunk in event.chunks]

        raw_chunks = _chunk_text(event.text or "", event.chunk_size, event.chunk_overlap)
        return [
            ConsciousnessChunk(
                text=raw_chunk,
                title=event.title,
                source_uri=event.source_uri,
                tags=event.tags,
                timestamp=event.timestamp,
                system=event.system,
                source=event.source,
                language=event.language,
                persona=event.persona,
                intent=event.intent,
                project_context=event.project_context,
                theme_resonance=event.theme_resonance,
                emotional_valence=event.emotional_valence,
                karmic_weight=event.karmic_weight,
                field_cluster=event.field_cluster,
                metadata_overrides=event.metadata_overrides,
            )
            for raw_chunk in raw_chunks
        ]

    def _hydrate_chunk(
        self,
        event: ConsciousnessIngestEvent,
        chunk: ConsciousnessChunk,
    ) -> ConsciousnessChunk:
        return chunk.model_copy(update={
            "title": chunk.title or event.title,
            "source_uri": chunk.source_uri or event.source_uri,
            "tags": chunk.tags or event.tags,
            "timestamp": chunk.timestamp or event.timestamp,
            "system": _normalize_choice(chunk.system or event.system, ALLOWED_SYSTEMS, "unknown"),
            "source": _normalize_choice(chunk.source or event.source, ALLOWED_SOURCES, "api"),
            "language": _normalize_choice(chunk.language or event.language, ALLOWED_LANGUAGES, "unknown"),
            "persona": _normalize_persona(chunk.persona or event.persona),
            "intent": _safe_text(chunk.intent or event.intent, "observe")[:128],
            "project_context": _safe_text(
                chunk.project_context or event.project_context or self.default_project_context,
                self.default_project_context,
            )[:128],
            "theme_resonance": _clamp_weight(chunk.theme_resonance, event.theme_resonance),
            "emotional_valence": _clamp_weight(chunk.emotional_valence, event.emotional_valence),
            "karmic_weight": _clamp_weight(chunk.karmic_weight, event.karmic_weight),
            "field_cluster": _safe_text(chunk.field_cluster or event.field_cluster, "unclassified")[:128],
            "metadata_overrides": {**event.metadata_overrides, **chunk.metadata_overrides},
        })

    def _build_metadata(
        self,
        event: ConsciousnessIngestEvent,
        chunk: ConsciousnessChunk,
        document_id: str,
        chunk_index: int,
        chunk_count: int,
        ingested_at: str,
    ) -> dict[str, Any]:
        title = _safe_text(chunk.title or event.title, "untitled_event")[:256]
        source_uri = _safe_text(chunk.source_uri or event.source_uri, "")[:2048]
        timestamp = chunk.timestamp or event.timestamp or _utc_now()
        content_hash = _sha256(f"{title}\n{chunk.text}")
        source_hash = _sha256(source_uri or document_id)
        metadata = {
            "type": "stream_consciousness",
            "document_id": document_id,
            "title": title,
            "source_uri": source_uri,
            "tags": _join_tags(chunk.tags),
            "content_hash": content_hash,
            "source_hash": source_hash,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "ingested_at": ingested_at,
            "layer_1_system": _normalize_choice(chunk.system, ALLOWED_SYSTEMS, "unknown"),
            "layer_2_source": _normalize_choice(chunk.source, ALLOWED_SOURCES, "api"),
            "layer_3_language": _normalize_choice(chunk.language, ALLOWED_LANGUAGES, "unknown"),
            "layer_4_timestamp": timestamp,
            "layer_5_persona": _normalize_persona(chunk.persona),
            "layer_6_intent": _safe_text(chunk.intent, "observe")[:128],
            "layer_7_project_context": _safe_text(chunk.project_context, self.default_project_context)[:128],
            "layer_8_theme_resonance": _clamp_weight(chunk.theme_resonance, event.theme_resonance),
            "layer_9_emotional_valence": _clamp_weight(chunk.emotional_valence, event.emotional_valence),
            "layer_10_karmic_weight": _clamp_weight(chunk.karmic_weight, event.karmic_weight),
            "layer_11_field_cluster": _safe_text(chunk.field_cluster, "unclassified")[:128],
        }
        for key, value in (chunk.metadata_overrides or {}).items():
            if isinstance(value, (str, int, float, bool)):
                metadata[key] = value
        return metadata

    def _is_duplicate(self, content_hash: str) -> bool:
        existing = self.collection.get(where={"content_hash": content_hash}, limit=1)
        return bool(existing and existing.get("ids"))

    def _build_query_where(self, payload: ConsciousnessQuery) -> Optional[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if payload.system:
            filters["layer_1_system"] = _normalize_choice(payload.system, ALLOWED_SYSTEMS, "unknown")
        if payload.source:
            filters["layer_2_source"] = _normalize_choice(payload.source, ALLOWED_SOURCES, "api")
        if payload.project_context:
            filters["layer_7_project_context"] = payload.project_context.strip()
        if payload.field_cluster:
            filters["layer_11_field_cluster"] = payload.field_cluster.strip()
        return filters or None

    def _passes_time_filter(self, metadata: dict[str, Any], payload: ConsciousnessQuery) -> bool:
        current = _parse_iso(str(metadata.get("layer_4_timestamp", "")))
        if current is None:
            return True
        start = _parse_iso(payload.start_timestamp)
        end = _parse_iso(payload.end_timestamp)
        if start and current < start:
            return False
        if end and current > end:
            return False
        return True

    def _rerank(self, persona: str, metadata: dict[str, Any]) -> tuple[float, dict[str, float]]:
        persona = _normalize_persona(persona)
        if persona == "developer":
            return self._rerank_developer(metadata)
        if persona == "talle_wintrip":
            return self._rerank_talle(metadata)
        return self._rerank_balanced(metadata)

    def _rerank_developer(self, metadata: dict[str, Any]) -> tuple[float, dict[str, float]]:
        system_score = 1.0 if metadata.get("layer_1_system") in {"mac", "vps", "docker", "web"} else 0.2
        source_score = 1.0 if metadata.get("layer_2_source") in _DEVELOPER_TECH_SOURCES else 0.35
        language_score = 1.0 if metadata.get("layer_3_language") in _DEVELOPER_TECH_LANGUAGES else 0.25
        chronology_score = 0.8 if metadata.get("layer_4_timestamp") else 0.2
        perspective_score = 0.9 if metadata.get("layer_6_intent") or metadata.get("layer_7_project_context") else 0.2
        breakdown = {
            "layer_1_system": system_score * 1.1,
            "layer_2_source": source_score * 1.0,
            "layer_3_language": language_score * 1.2,
            "layer_4_timestamp": chronology_score * 0.6,
            "layers_6_7_perspective": perspective_score * 0.8,
        }
        return sum(breakdown.values()), breakdown

    def _rerank_talle(self, metadata: dict[str, Any]) -> tuple[float, dict[str, float]]:
        theme = _clamp_weight(metadata.get("layer_8_theme_resonance")) * 1.5
        valence = _clamp_weight(metadata.get("layer_9_emotional_valence")) * 1.2
        karmic = _clamp_weight(metadata.get("layer_10_karmic_weight")) * 1.5
        field_cluster = str(metadata.get("layer_11_field_cluster", "")).strip().lower()
        field_score = 1.0 if field_cluster in _TALLE_FIELD_CLUSTERS else 0.35
        persona_score = 1.0 if metadata.get("layer_5_persona") == "talle_wintrip" else 0.4
        context_score = 0.9 if metadata.get("layer_7_project_context") else 0.25
        breakdown = {
            "layer_8_theme_resonance": theme,
            "layer_9_emotional_valence": valence,
            "layer_10_karmic_weight": karmic,
            "layer_11_field_cluster": field_score * 1.0,
            "layers_5_7_perspective": (persona_score + context_score) * 0.5,
        }
        return sum(breakdown.values()), breakdown

    def _rerank_balanced(self, metadata: dict[str, Any]) -> tuple[float, dict[str, float]]:
        technical = (
            (1.0 if metadata.get("layer_1_system") != "unknown" else 0.25) +
            (1.0 if metadata.get("layer_2_source") != "manual" else 0.5) +
            (1.0 if metadata.get("layer_3_language") in _DEVELOPER_TECH_LANGUAGES else 0.4)
        ) / 3.0
        resonance = (
            _clamp_weight(metadata.get("layer_8_theme_resonance")) +
            _clamp_weight(metadata.get("layer_9_emotional_valence")) +
            _clamp_weight(metadata.get("layer_10_karmic_weight"))
        ) / 3.0
        perspective = 1.0 if metadata.get("layer_7_project_context") else 0.4
        breakdown = {
            "technical_balance": technical * 1.0,
            "resonance_balance": resonance * 1.0,
            "perspective_balance": perspective * 0.8,
        }
        return sum(breakdown.values()), breakdown
