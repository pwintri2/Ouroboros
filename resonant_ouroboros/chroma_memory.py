"""ChromaDB-backed 11D hippocampus memory for Resonant Ouroboros Fase 4."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .schema import Hippocampus11D, build_11d_record, text_cluster_id, validate_11d_metadata


@dataclass(frozen=True)
class MemoryConfig:
    """Runtime configuration for the persistent 11D ChromaDB collection."""

    persist_dir: Path = Path("/workspace/data/chromadb")
    collection_name: str = "ouroboros_11d"
    chroma_host: str | None = None
    chroma_port: int = 8000
    chroma_ssl: bool = False
    tenant: str = "default_tenant"
    database: str = "default_database"

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        return cls(
            persist_dir=Path(os.getenv("CHROMA_PERSIST_DIR", "/workspace/data/chromadb")),
            collection_name=os.getenv("CHROMA_COLLECTION", "ouroboros_11d"),
            chroma_host=os.getenv("CHROMA_HOST") or None,
            chroma_port=int(os.getenv("CHROMA_PORT", "8000")),
            chroma_ssl=os.getenv("CHROMA_SSL", "false").strip().lower() == "true",
            tenant=os.getenv("CHROMA_TENANT", "default_tenant"),
            database=os.getenv("CHROMA_DATABASE", "default_database"),
        )


def _query_record(query: str) -> Hippocampus11D:
    clean = " ".join((query or "").split())
    return build_11d_record(
        physical_structure="semantic_query_text",
        source_origin="runtime_query",
        path_or_proprioception=clean[:240] or "recent",
        relative_temporal_position="query_now",
        persona_actor="resonant_ouroboros_retriever",
        intent_marker=f"query:{clean[:160] or 'recent'}",
        user_context_marker=clean[:240] or "recent memory",
        emotional_valence=0.0,
        importance_score=0.5,
        karmic_weight=0.5,
        field_cluster_id=text_cluster_id(clean or "recent", prefix="query"),
        current_hz=425.0,
        vibration_mood="curious_scan",
    )


def _term_overlap(query: str, text: str, metadata: dict[str, Any]) -> float:
    terms = {item for item in (query or "").lower().split() if len(item) > 2}
    if not terms:
        return 0.0
    haystack = f"{text} {metadata}".lower()
    return sum(1.0 for term in terms if term in haystack) / max(1.0, float(len(terms)))


class ChromaHippocampusMemory:
    """Persistent ChromaDB storage where every record uses an exact 11D vector."""

    backend_name = "chromadb"

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig.from_env()
        self._chromadb = self._import_chromadb()
        self.client = self._create_client()
        self.collection = self.client.get_or_create_collection(name=self.config.collection_name)

    def _import_chromadb(self):
        try:
            import chromadb  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is required for persistent 11D memory. "
                "Install requirements.ouroboros.txt or run inside the Fase 4 Docker image."
            ) from exc
        return chromadb

    def _create_client(self):
        if self.config.chroma_host:
            return self._chromadb.HttpClient(
                host=self.config.chroma_host,
                port=self.config.chroma_port,
                ssl=self.config.chroma_ssl,
                tenant=self.config.tenant,
                database=self.config.database,
            )
        self.config.persist_dir.mkdir(parents=True, exist_ok=True)
        return self._chromadb.PersistentClient(
            path=str(self.config.persist_dir),
            tenant=self.config.tenant,
            database=self.config.database,
        )

    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        metadata = record.metadata()
        validate_11d_metadata(metadata)
        identifier = record_id or f"memory_{record.field_cluster_id}"
        self.collection.upsert(
            ids=[identifier],
            documents=[document],
            metadatas=[metadata],
            embeddings=[record.vector()],
        )
        return identifier

    def migrate_rows(self, rows: list[dict[str, Any]]) -> int:
        """Upsert existing 11D-shaped rows into ChromaDB."""

        migrated = 0
        for row in rows:
            metadata = row.get("metadata") or {}
            vector = row.get("vector") or row.get("embedding")
            identifier = row.get("id")
            document = row.get("document") or row.get("text") or ""
            if not identifier or not vector:
                continue
            validate_11d_metadata(metadata)
            if len(vector) != 11:
                raise ValueError("migrated ChromaDB embeddings must have exactly 11 dimensions")
            self.collection.upsert(
                ids=[str(identifier)],
                documents=[str(document)],
                metadatas=[metadata],
                embeddings=[[float(item) for item in vector]],
            )
            migrated += 1
        return migrated

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        limit = max(1, min(int(n_results or 8), 50))
        total = self.count()
        if total <= 0:
            return []
        candidate_limit = min(total, max(limit, limit * 4 if query else limit))
        try:
            result = self.collection.query(
                query_embeddings=[_query_record(query).vector()],
                n_results=candidate_limit,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            result = self.collection.get(limit=candidate_limit, include=["documents", "metadatas"])
        rows = self._rows_from_result(result)
        if query:
            rows.sort(
                key=lambda row: (
                    _term_overlap(query, str(row.get("text") or ""), row.get("metadata") or {}),
                    -(float(row.get("distance") or 0.0)),
                ),
                reverse=True,
            )
        return rows[:limit]

    def count(self) -> int:
        return int(self.collection.count())

    def info(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "collection": self.config.collection_name,
            "persist_dir": str(self.config.persist_dir),
            "host": self.config.chroma_host,
            "records": self.count(),
        }

    def _rows_from_result(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        ids = self._flatten(result.get("ids") or [])
        docs = self._flatten(result.get("documents") or [])
        metas = self._flatten(result.get("metadatas") or [])
        distances = self._flatten(result.get("distances") or [])
        rows: list[dict[str, Any]] = []
        for index, identifier in enumerate(ids):
            metadata = metas[index] if index < len(metas) and isinstance(metas[index], dict) else {}
            rows.append(
                {
                    "id": identifier,
                    "text": docs[index] if index < len(docs) else "",
                    "metadata": metadata,
                    "distance": distances[index] if index < len(distances) else None,
                    "similarity": self._similarity(distances[index] if index < len(distances) else None),
                }
            )
        return rows

    def _flatten(self, value: list[Any]) -> list[Any]:
        if value and isinstance(value[0], list):
            return value[0]
        return value

    def _similarity(self, distance: Any) -> float | None:
        if distance is None:
            return None
        try:
            return round(1.0 / (1.0 + max(0.0, float(distance))), 6)
        except Exception:
            return None
