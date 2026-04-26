"""11D hippocampus memory backed by ChromaDB when available."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Protocol

from .schema import Hippocampus11D, validate_11d_metadata


class HippocampusMemory(Protocol):
    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        ...

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        ...

    def count(self) -> int:
        ...


@dataclass(frozen=True)
class MemoryConfig:
    persist_dir: Path = Path("/workspace/data/chromadb")
    collection_name: str = "ouroboros_11d_hippocampus"
    chroma_host: str | None = None
    chroma_port: int = 8000
    chroma_ssl: bool = False
    tenant: str = "default_tenant"
    database: str = "default_database"

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        return cls(
            persist_dir=Path(os.getenv("CHROMA_PERSIST_DIR", "/workspace/data/chromadb")),
            collection_name=os.getenv("CHROMA_COLLECTION", "ouroboros_11d_hippocampus"),
            chroma_host=os.getenv("CHROMA_HOST") or None,
            chroma_port=int(os.getenv("CHROMA_PORT", "8000")),
            chroma_ssl=os.getenv("CHROMA_SSL", "false").strip().lower() == "true",
            tenant=os.getenv("CHROMA_TENANT", "default_tenant"),
            database=os.getenv("CHROMA_DATABASE", "default_database"),
        )


class InMemoryHippocampusMemory:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        metadata = record.metadata()
        validate_11d_metadata(metadata)
        identifier = record_id or f"memory_{len(self.rows) + 1}_{record.field_cluster_id}"
        self.rows.append(
            {
                "id": identifier,
                "document": document,
                "metadata": metadata,
                "vector": record.vector(),
            }
        )
        return identifier

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        query_terms = set((query or "").lower().split())
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in self.rows:
            haystack = f"{row['document']} {row['metadata']}".lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score or not query_terms:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "id": row["id"],
                "text": row["document"],
                "metadata": row["metadata"],
                "distance": 1.0 / (score + 1),
            }
            for score, row in scored[:n_results]
        ]

    def count(self) -> int:
        return len(self.rows)


class ChromaHippocampusMemory:
    """Persistent ChromaDB storage where every vector has exactly 11 floats."""

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig.from_env()
        self._chromadb = self._import_chromadb()
        self.client = self._create_client_with_retry()
        self.collection = self.client.get_or_create_collection(name=self.config.collection_name)

    def _import_chromadb(self):
        try:
            import chromadb  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is required for persistent Hippocampus memory. "
                "Use the Docker environment or install requirements.txt."
            ) from exc
        return chromadb

    def _create_client_with_retry(self):
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
        self.collection.add(
            ids=[identifier],
            documents=[document],
            metadatas=[metadata],
            embeddings=[record.vector()],
        )
        return identifier

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        try:
            result = self.collection.query(query_texts=[query], n_results=n_results)
        except Exception:
            result = self.collection.get(limit=n_results, include=["documents", "metadatas"])
        ids = (result.get("ids") or [[]])[0] if result.get("ids") and isinstance(result.get("ids")[0], list) else result.get("ids", [])
        docs = (result.get("documents") or [[]])[0] if result.get("documents") and isinstance(result.get("documents")[0], list) else result.get("documents", [])
        metas = (result.get("metadatas") or [[]])[0] if result.get("metadatas") and isinstance(result.get("metadatas")[0], list) else result.get("metadatas", [])
        distances = (result.get("distances") or [[]])[0] if result.get("distances") and isinstance(result.get("distances")[0], list) else result.get("distances", [])
        rows = []
        for index, identifier in enumerate(ids):
            rows.append(
                {
                    "id": identifier,
                    "text": docs[index] if index < len(docs) else "",
                    "metadata": metas[index] if index < len(metas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return rows

    def count(self) -> int:
        return int(self.collection.count())


def create_memory_from_env(fallback_in_memory: bool = False) -> HippocampusMemory:
    backend = os.getenv("OUROBOROS_MEMORY_BACKEND", "").strip().lower()
    if backend in {"memory", "inmemory", "in-memory"}:
        return InMemoryHippocampusMemory()
    try:
        return ChromaHippocampusMemory(MemoryConfig.from_env())
    except Exception:
        if fallback_in_memory:
            return InMemoryHippocampusMemory()
        raise
