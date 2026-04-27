"""Append-only co-evolution event journal for Fase 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from .self_model import compact_text


EVOLUTION_SCHEMA_VERSION = "ouroboros_co_evolution_proto_1_1_fase_4"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_evolution_path() -> Path:
    if Path("/workspace").exists():
        return Path("/workspace/data/awake_keeper_evolution_events.jsonl")
    return Path("data/awake_keeper_evolution_events.jsonl")


@dataclass(frozen=True)
class EvolutionEvent:
    event_type: str
    topic: str
    input_summary: str
    output_summary: str
    hz: float | None = None
    mood: str | None = None
    record_ids: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    action_ids: list[str] = field(default_factory=list)
    status: str = "ok"
    safety: str = "safe_mode"
    model: str | None = None
    error: str | None = None
    importance: float = 0.5
    prompt_context_record_ids: list[str] = field(default_factory=list)
    score_delta: float = 0.0

    def row(self) -> dict[str, Any]:
        created_at = utc_now()
        return {
            "schema_version": EVOLUTION_SCHEMA_VERSION,
            "id": f"evo_{created_at.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}",
            "created_at": created_at,
            "type": compact_text(self.event_type, 80),
            "topic": compact_text(self.topic, 220),
            "input_summary": compact_text(self.input_summary, 700),
            "output_summary": compact_text(self.output_summary, 900),
            "hz": float(self.hz) if self.hz is not None else None,
            "mood": compact_text(self.mood, 80) if self.mood else None,
            "record_ids": [compact_text(item, 180) for item in self.record_ids[:8]],
            "source_urls": [compact_text(item, 240) for item in self.source_urls[:6]],
            "action_ids": [compact_text(item, 180) for item in self.action_ids[:6]],
            "status": compact_text(self.status, 80),
            "safety": compact_text(self.safety, 240),
            "model": compact_text(self.model, 120) if self.model else None,
            "error": compact_text(self.error, 500) if self.error else None,
            "importance": max(0.0, min(1.0, float(self.importance))),
            "prompt_context_record_ids": [
                compact_text(item, 180) for item in self.prompt_context_record_ids[:8]
            ],
            "score_delta": round(max(0.0, min(1.0, float(self.score_delta))), 4),
        }


class EvolutionEventStore:
    """Small JSONL journal used as the durable co-evolution read model."""

    def __init__(self, path: str | Path | None = None, *, max_summary_events: int = 6):
        self.path = Path(path) if path is not None else default_evolution_path()
        self.max_summary_events = max(1, int(max_summary_events))
        self._lock = threading.RLock()

    @classmethod
    def from_env(cls) -> "EvolutionEventStore":
        return cls(path=os.getenv("AWAKE_KEEPER_EVOLUTION_EVENTS_PATH") or None)

    def append(self, event: EvolutionEvent) -> dict[str, Any]:
        row = event.row()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def list_events(self, limit: int = 20, event_type: str | None = None) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit or 20), 200))
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except Exception:
                continue
            if event_type and row.get("type") != event_type:
                continue
            rows.append(row)
            if len(rows) >= bounded_limit:
                break
        return rows

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._lock:
            return sum(1 for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())

    def score(self) -> float:
        events = self.list_events(limit=200)
        return round(sum(float(event.get("score_delta") or 0.0) for event in events), 3)

    def summary(self, limit: int | None = None) -> str:
        events = self.list_events(limit=limit or self.max_summary_events)
        if not events:
            return "No co-evolution events have been recorded yet."
        parts = []
        for event in events:
            parts.append(
                f"{event.get('type')}:{compact_text(event.get('topic'), 90)} -> "
                f"{compact_text(event.get('output_summary'), 140)}"
            )
        return " | ".join(parts)
