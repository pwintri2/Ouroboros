"""Geheugenlaag voor Ouroboros met retentie en hybride recall.

Deze module vertaalt de bruikbare ideeën uit Mengram en MemoryOS naar een
kleine, dependency-vrije kern: episodisch, semantisch en procedureel geheugen,
Ebbinghaus-retentie, reinforcement bij recall en een simpele hybride ranker.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MemoryKind(str, Enum):
    """Ouroboros geheugenfamilies."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    CAPABILITY = "capability"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", text.lower()) if len(token) > 1}


@dataclass
class MemoryAtom:
    """Een compact geheugen-item met retentie en reinforcement."""

    content: str
    memory_kind: MemoryKind
    agent_id: str = "ouroboros"
    importance: float = 5.0
    tags: list[str] = field(default_factory=list)
    source: str = "direct"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=_utc_now)
    last_accessed: datetime = field(default_factory=_utc_now)
    access_count: int = 0
    stability: float = 1.0

    @property
    def retention(self) -> float:
        """Retentie volgens de Ebbinghaus-curve: R = e^(-t/S)."""

        elapsed_days = (_utc_now() - self.last_accessed).total_seconds() / 86400.0
        return math.exp(-elapsed_days / max(self.stability, 0.1))

    @property
    def forgotten(self) -> bool:
        return self.retention < 0.05

    def reinforce(self) -> None:
        """Versterk dit geheugen na succesvolle recall."""

        self.access_count += 1
        self.last_accessed = _utc_now()
        self.stability = self.stability * (1.0 + 0.3 / math.log(self.access_count + 2))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_kind"] = self.memory_kind.value
        payload["created_at"] = self.created_at.isoformat().replace("+00:00", "Z")
        payload["last_accessed"] = self.last_accessed.isoformat().replace("+00:00", "Z")
        payload["retention"] = round(self.retention, 4)
        return payload


class OuroborosMemoryLattice:
    """In-memory geheugenraster voor de esoterische runtime."""

    DEFAULT_WEIGHTS = {
        "semantic": 0.50,
        "retention": 0.20,
        "importance": 0.20,
        "recency": 0.10,
    }

    def __init__(self, agent_id: str = "ouroboros", weights: dict[str, float] | None = None):
        self.agent_id = agent_id
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self._memories: dict[str, MemoryAtom] = {}

    def remember(
        self,
        content: str,
        memory_kind: MemoryKind | str | None = None,
        *,
        importance: float = 5.0,
        tags: list[str] | None = None,
        source: str = "direct",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryAtom:
        """Sla een nieuw geheugen-item op."""

        cleaned = str(content or "").strip()
        if not cleaned:
            raise ValueError("Memory content is empty.")
        kind = self._coerce_kind(memory_kind) if memory_kind else self.classify(cleaned)
        atom = MemoryAtom(
            content=cleaned,
            memory_kind=kind,
            agent_id=self.agent_id,
            importance=max(0.0, min(10.0, float(importance))),
            tags=list(tags or []),
            source=str(source or "direct"),
            metadata=dict(metadata or {}),
        )
        self._memories[atom.id] = atom
        return atom

    def recall(
        self,
        query: str,
        *,
        top_k: int = 5,
        memory_kind: MemoryKind | str | None = None,
        min_importance: float = 0.0,
        include_forgotten: bool = False,
    ) -> list[MemoryAtom]:
        """Haal relevante geheugens op en versterk de geselecteerde items."""

        scored = self.recall_with_scores(
            query,
            top_k=top_k,
            memory_kind=memory_kind,
            min_importance=min_importance,
            include_forgotten=include_forgotten,
        )
        atoms = [atom for atom, _score in scored]
        for atom in atoms:
            atom.reinforce()
        return atoms

    def recall_with_scores(
        self,
        query: str,
        *,
        top_k: int = 5,
        memory_kind: MemoryKind | str | None = None,
        min_importance: float = 0.0,
        include_forgotten: bool = False,
    ) -> list[tuple[MemoryAtom, float]]:
        """Recall zonder side effects, handig voor inspectie en tests."""

        kind = self._coerce_kind(memory_kind) if memory_kind else None
        query_tokens = _tokenize(query)
        scored: list[tuple[MemoryAtom, float]] = []
        for atom in self._memories.values():
            if kind and atom.memory_kind != kind:
                continue
            if atom.importance < min_importance:
                continue
            if not include_forgotten and atom.forgotten:
                continue
            similarity = self._keyword_similarity(query_tokens, atom)
            score = self._composite_score(atom, similarity)
            if score > 0.0:
                scored.append((atom, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: max(1, int(top_k))]

    def stats(self) -> dict[str, Any]:
        atoms = list(self._memories.values())
        if not atoms:
            return {"total": 0, "agent_id": self.agent_id, "by_kind": {}}
        return {
            "total": len(atoms),
            "agent_id": self.agent_id,
            "by_kind": {
                kind.value: sum(1 for atom in atoms if atom.memory_kind == kind)
                for kind in MemoryKind
            },
            "avg_retention": round(sum(atom.retention for atom in atoms) / len(atoms), 4),
            "avg_importance": round(sum(atom.importance for atom in atoms) / len(atoms), 2),
            "forgotten": sum(1 for atom in atoms if atom.forgotten),
        }

    def dump(self) -> list[dict[str, Any]]:
        return [atom.to_dict() for atom in self._memories.values()]

    @staticmethod
    def classify(text: str) -> MemoryKind:
        """Heuristische Mengram-achtige classificatie."""

        lower = text.lower()
        if any(word in lower for word in ("failed", "completed", "observed", "ran ", "deployed", "job ")):
            return MemoryKind.EPISODIC
        if any(word in lower for word in ("always", "procedure", "workflow", "step ", "run tests", "before merge")):
            return MemoryKind.PROCEDURAL
        if any(word in lower for word in ("capability", "supports", "connector", "tool", "routing", "retrieval")):
            return MemoryKind.CAPABILITY
        return MemoryKind.SEMANTIC

    @staticmethod
    def _coerce_kind(value: MemoryKind | str | None) -> MemoryKind:
        if isinstance(value, MemoryKind):
            return value
        return MemoryKind(str(value))

    def _keyword_similarity(self, query_tokens: set[str], atom: MemoryAtom) -> float:
        if not query_tokens:
            return 0.0
        content_tokens = _tokenize(atom.content)
        metadata_tokens = _tokenize(" ".join(str(value) for value in atom.metadata.values()))
        tag_tokens = _tokenize(" ".join(atom.tags))
        atom_tokens = content_tokens | metadata_tokens | tag_tokens
        if not atom_tokens:
            return 0.0
        overlap = len(query_tokens & atom_tokens) / max(len(query_tokens), 1)
        coverage = len(query_tokens & atom_tokens) / max(len(atom_tokens), 1)
        return min(1.0, overlap * 0.8 + coverage * 0.2)

    def _composite_score(self, atom: MemoryAtom, similarity: float) -> float:
        hours_ago = (_utc_now() - atom.last_accessed).total_seconds() / 3600.0
        recency = math.exp(-hours_ago / 48.0)
        return (
            self.weights["semantic"] * similarity
            + self.weights["retention"] * atom.retention
            + self.weights["importance"] * (atom.importance / 10.0)
            + self.weights["recency"] * recency
        )
