"""11D hippocampus memory facade."""

from __future__ import annotations

import os
from typing import Any, Protocol

from .chroma_memory import ChromaHippocampusMemory, MemoryConfig
from .schema import Hippocampus11D, validate_11d_metadata


class HippocampusMemory(Protocol):
    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        ...

    def search(self, query: str, n_results: int = 8) -> list[dict[str, Any]]:
        ...

    def count(self) -> int:
        ...


class InMemoryHippocampusMemory:
    backend_name = "memory"

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def store(self, document: str, record: Hippocampus11D, record_id: str | None = None) -> str:
        metadata = record.metadata()
        validate_11d_metadata(metadata)
        identifier = record_id or f"memory_{len(self.rows) + 1}_{record.field_cluster_id}"
        row = {
            "id": identifier,
            "document": document,
            "metadata": metadata,
            "vector": record.vector(),
        }
        for index, existing in enumerate(self.rows):
            if existing.get("id") == identifier:
                self.rows[index] = row
                return identifier
        self.rows.append(row)
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
                "similarity": score / max(1, len(query_terms)) if query_terms else None,
            }
            for score, row in scored[:n_results]
        ]

    def count(self) -> int:
        return len(self.rows)

    def info(self) -> dict[str, Any]:
        return {"backend": self.backend_name, "collection": None, "persist_dir": None, "records": self.count()}


def create_memory_from_env(fallback_in_memory: bool = False) -> HippocampusMemory:
    backend = os.getenv("OUROBOROS_MEMORY_BACKEND", "").strip().lower()
    if backend in {"memory", "inmemory", "in-memory"}:
        return InMemoryHippocampusMemory()
    if backend in {"none", "off", "disabled"}:
        return InMemoryHippocampusMemory()
    try:
        return ChromaHippocampusMemory(MemoryConfig.from_env())
    except Exception:
        if fallback_in_memory:
            return InMemoryHippocampusMemory()
        raise
