from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_SYSTEMS = {"mac", "vps", "web", "docker", "unknown"}
ALLOWED_SOURCES = {"file_watch", "telemetry", "web_scrape", "manual", "api"}
ALLOWED_LANGUAGES = {
    "python", "swift", "javascript", "typescript", "html", "css", "json",
    "markdown", "bash", "yaml", "sql", "plaintext", "unknown",
}


def _utc_iso(value: Optional[datetime] = None) -> str:
    current = value or datetime.now(tz=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _normalize_choice(value: Optional[str], allowed: set[str], fallback: str) -> str:
    candidate = (value or fallback).strip().lower()
    return candidate if candidate in allowed else fallback


def _clamp_weight(value: Optional[float], fallback: float = 0.5) -> float:
    if value is None:
        return fallback
    return max(0.0, min(1.0, float(value)))


class ConsciousnessChunk(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    title: Optional[str] = Field(default=None, max_length=256)
    source_uri: Optional[str] = Field(default=None, max_length=2048)
    tags: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = Field(default=None)
    system: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    persona: Optional[str] = Field(default=None, max_length=64)
    intent: Optional[str] = Field(default=None, max_length=128)
    project_context: Optional[str] = Field(default=None, max_length=128)
    theme_resonance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    emotional_valence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    karmic_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    field_cluster: Optional[str] = Field(default=None, max_length=128)
    metadata_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def dedupe_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            tag = str(item).strip().lower()
            if tag and tag not in cleaned:
                cleaned.append(tag[:64])
        return cleaned[:20]


class ConsciousnessIngestEvent(BaseModel):
    title: str = Field(default="untitled_event", max_length=256)
    text: Optional[str] = Field(default=None, max_length=100000)
    chunks: list[ConsciousnessChunk] = Field(default_factory=list)
    source_uri: Optional[str] = Field(default=None, max_length=2048)
    tags: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = Field(default=None)
    system: str = Field(default="unknown")
    source: str = Field(default="api")
    language: str = Field(default="unknown")
    persona: str = Field(default="developer", max_length=64)
    intent: str = Field(default="observe", max_length=128)
    project_context: str = Field(default="phase_7_web_migration", max_length=128)
    theme_resonance: float = Field(default=0.5, ge=0.0, le=1.0)
    emotional_valence: float = Field(default=0.5, ge=0.0, le=1.0)
    karmic_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    field_cluster: str = Field(default="unclassified", max_length=128)
    metadata_overrides: dict[str, Any] = Field(default_factory=dict)
    chunk_size: int = Field(default=1200, ge=200, le=4000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_payload_shape(self) -> "ConsciousnessIngestEvent":
        if not (self.text and self.text.strip()) and not self.chunks:
            raise ValueError("Provide either non-empty text or at least one chunk.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self

    @field_validator("system")
    @classmethod
    def normalize_system(cls, value: str) -> str:
        return _normalize_choice(value, ALLOWED_SYSTEMS, "unknown")

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        return _normalize_choice(value, ALLOWED_SOURCES, "api")

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return _normalize_choice(value, ALLOWED_LANGUAGES, "unknown")

    @field_validator("persona")
    @classmethod
    def normalize_persona(cls, value: str) -> str:
        candidate = value.strip().lower().replace(" ", "_")
        return "talle_wintrip" if candidate in {"talle", "talle_wintrip", "talle-wintrip"} else candidate

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: Optional[str]) -> str:
        if not value:
            return _utc_iso()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _utc_iso(parsed)


class ConsciousnessIngestResponse(BaseModel):
    accepted: bool
    document_id: str
    collection: str
    chunk_count: int
    stored_chunk_ids: list[str]
    duplicate_chunk_ids: list[str]
    ingested_at: str
    metadata_summary: dict[str, Any]


class ConsciousnessQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    persona: str = Field(default="developer", max_length=64)
    n_results: int = Field(default=5, ge=1, le=25)
    system: Optional[str] = None
    source: Optional[str] = None
    project_context: Optional[str] = None
    field_cluster: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None

    @field_validator("persona")
    @classmethod
    def normalize_query_persona(cls, value: str) -> str:
        candidate = value.strip().lower().replace(" ", "_")
        return "talle_wintrip" if candidate in {"talle", "talle_wintrip", "talle-wintrip"} else candidate


class ConsciousnessQueryResult(BaseModel):
    id: str
    document: str
    metadata: dict[str, Any]
    distance: float
    semantic_score: float
    rerank_score: float
    final_score: float
    score_breakdown: dict[str, float]


class ConsciousnessQueryResponse(BaseModel):
    persona: str
    collection: str
    result_count: int
    results: list[ConsciousnessQueryResult]
