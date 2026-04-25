"""11D hippocampus memory backed by ChromaDB."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
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
            chroma_ssl=os.getenv("CHROMA_SSL", "false").strip().lower() in {"1", "true", "yes"},
            tenant=os.getenv("CHROMA_TENANT", "default_tenant"),
            database=os.getenv("CHROMA_DATABASE", "default_database"),
        )


class ChromaHippocampusMemory:
    """Persistent ChromaDB storage where every vector has exactly 11 floats."""

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig.from_env()
        self._chromadb = self._import_chromadb()
        self.client = self._create_client_with_retry()
        self.collection = self._get_or_create_collection_with_retry()

    @staticmethod
    def _import_chromadb():
        try:
            import chromadb  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is required for persistent Hippocampus memory. "
                "Use the Docker environment or install requirements.txt."
            ) from exc
        return chromadb

    def _client_settings(self):
        try:
            from chromadb.config import Settings  # type: ignore
        except ImportError:
            return None
        return Settings(
            anonymized_telemetry=False,
            allow_reset=False,
        )

    def _create_client_with_retry(self):
        last_error: Exception | None = None
        for attempt in range(1, 31):
            try:
                if self.config.chroma_host:
                    settings = self._client_settings()
                    kwargs: dict[str, Any] = {
                        "host": self.config.chroma_host,
                        "port": self.config.chroma_port,
                        "ssl": self.config.chroma_ssl,
                    }
                    if settings is not None:
                        kwargs["settings"] = settings
                    kwargs["tenant"] = self.config.tenant
                    kwargs["database"] = self.config.database
                    client = self._chromadb.HttpClient(**kwargs)
                    client.heartbeat()
                    return client

                self.config.persist_dir.mkdir(parents=True, exist_ok=True)
                settings = self._client_settings()
                if settings is None:
                    return self._chromadb.PersistentClient(path=str(self.config.persist_dir))
                return self._chromadb.PersistentClient(
                    path=str(self.config.persist_dir),
                    settings=settings,
                )
            except TypeError as exc:
                last_error = exc
                try:
                    client = self._chromadb.HttpClient(
                        host=self.config.chroma_host,
                        port=self.config.chroma_port,
                        ssl=self.config.chroma_ssl,
                    )
                    client.heartbeat()
                    return client
                except Exception as fallback_exc:
                    last_error = fallback_exc
            except Exception as exc:
                last_error = exc
            time.sleep(min(0.5 * attempt, 5.0))

        target = (
            f"http{'s' if self.config.chroma_ssl else ''}://"
            f"{self.config.chroma_host}:{self.config.chroma_port}"
            if self.config.chroma_host
            else str(self.config.persist_dir)
        )
        raise RuntimeError(f"ChromaDB client unavailable at {target}: {last_error}") from last_error

    def _get_or_create_collection_with_retry(self):
        last_error: Exception | None = None
        for _ in range(20):
            try:
                return self.client.get_or_create_collection(
                    name=self.config.collection_name,
                    metadata={"hnsw:space": "cosine", "vector_dimensions": 11},
                )
            except Exception as exc:  # Chroma HTTP service may still be booting.
                last_error = exc
                time.sleep(0.5)
        raise RuntimeError(f"ChromaDB collection unavailable: {last_error}") from last_error

    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        metadata = record.metadata()
        validate_11d_metadata(metadata)
        identifier = record_id or _record_id(document, metadata)
        self.collection.upsert(
            ids=[identifier],
            documents=[document],
            metadatas=[metadata],
            embeddings=[record.vector()],
        )
        return identifier

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        vector = _query_vector(query)
        result = self.collection.query(query_embeddings=[vector], n_results=n_results)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0] if result.get("distances") else []
        rows: list[dict[str, Any]] = []
        for index, document in enumerate(documents):
            rows.append(
                {
                    "id": ids[index] if index < len(ids) else "",
                    "document": document,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return rows

    def count(self) -> int:
        return int(self.collection.count())


class InMemoryHippocampusMemory:
    """Small stdlib memory used by tests and dry local runs without ChromaDB."""

    def __init__(self):
        self.rows: list[dict[str, Any]] = []

    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        metadata = record.metadata()
        validate_11d_metadata(metadata)
        identifier = record_id or _record_id(document, metadata)
        self.rows = [row for row in self.rows if row["id"] != identifier]
        self.rows.append(
            {
                "id": identifier,
                "document": document,
                "metadata": metadata,
                "embedding": record.vector(),
            }
        )
        return identifier

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        terms = set(query.lower().split())
        scored = []
        for row in self.rows:
            text_terms = set(row["document"].lower().split())
            score = len(terms & text_terms)
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:n_results]]

    def count(self) -> int:
        return len(self.rows)


def create_memory_from_env(fallback_in_memory: bool = False) -> HippocampusMemory:
    try:
        return ChromaHippocampusMemory()
    except RuntimeError:
        if fallback_in_memory:
            return InMemoryHippocampusMemory()
        raise


def _record_id(document: str, metadata: dict[str, Any]) -> str:
    key = f"{document}|{metadata.get('source_origin')}|{metadata.get('field_cluster_id')}"
    digest = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()
    return f"memory_{digest[:24]}"


def _query_vector(query: str) -> list[float]:
    digest = hashlib.sha256(query.encode("utf-8", errors="ignore")).digest()
    values = []
    for index in range(11):
        byte = digest[index]
        values.append(round((byte / 255.0) * 2.0 - 1.0, 6))
    return values
